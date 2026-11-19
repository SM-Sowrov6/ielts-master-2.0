"""Outbox dispatcher process: `python -m app.workers.outbox` (docker-compose service `worker`).

Crash-safety (see app/core/outbox.py for the full semantics):
- Claim: one short transaction marks up to BATCH due rows with a lease and increments `attempts`
  (`FOR UPDATE SKIP LOCKED`), so concurrent workers never take the same row.
- Work happens outside any transaction. Completion is fenced on (id, attempts): if this worker's
  lease expired and another worker re-claimed the row, the stale completion changes nothing.
- Worker crash after claiming: the lease expires and the row is retried.
- SMTP failure: exponential backoff (30 s doubling, max 1 h), `dead` after MAX_ATTEMPTS.
- Database failure after SMTP accepted the email: the row stays claimed, the lease expires and the
  same (still valid) email is sent again with the same Message-ID: at-least-once delivery.
- `last_error` stores only the exception class name (never addresses or message bodies).
"""

import asyncio
import contextlib
import signal
import time
from dataclasses import dataclass, field
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import create_engine, create_session_factory
from app.core.email import EmailSender, SmtpEmailSender
from app.core.logging import configure_logging
from app.core.outbox import OutboxContext, OutboxHandler
from app.modules.exams import api as exams
from app.modules.identity import api as identity
from app.modules.speaking import api as speaking
from app.modules.writing import api as writing

log = structlog.get_logger("app.workers.outbox")

BATCH = 20
LEASE_SECONDS = 300
MAX_ATTEMPTS = 8
CLEANUP_INTERVAL_SECONDS = 3600
SWEEP_INTERVAL_SECONDS = 30  # exam deadlines (design §4.1: sweeper every 30 s)

_CLAIM = text(
    """
    UPDATE outbox_messages
       SET locked_until = now() + make_interval(secs => :lease),
           attempts = attempts + 1,
           updated_at = now()
     WHERE id IN (
           SELECT id FROM outbox_messages
            WHERE status = 'pending'
              AND next_attempt_at <= now()
              AND (locked_until IS NULL OR locked_until < now())
            ORDER BY next_attempt_at
            LIMIT :batch
            FOR UPDATE SKIP LOCKED)
    RETURNING id, topic, payload, attempts
    """
)
_COMPLETE = text(
    """
    UPDATE outbox_messages
       SET status = :status, payload = '{}'::jsonb, locked_until = NULL, last_error = NULL,
           sent_at = CASE WHEN :sent THEN now() ELSE sent_at END, updated_at = now()
     WHERE id = :id AND attempts = :attempts AND status = 'pending'
    """
)
_FAIL = text(
    """
    UPDATE outbox_messages
       SET status = CASE WHEN attempts >= :max_attempts THEN 'dead' ELSE 'pending' END,
           payload = CASE WHEN attempts >= :max_attempts THEN '{}'::jsonb ELSE payload END,
           next_attempt_at = now() + make_interval(secs => :backoff),
           locked_until = NULL, last_error = :error, updated_at = now()
     WHERE id = :id AND attempts = :attempts AND status = 'pending'
    """
)
_CLEANUP = text(
    """
    DELETE FROM outbox_messages
     WHERE (status IN ('sent', 'skipped') AND updated_at < now() - interval '7 days')
        OR (status = 'dead' AND updated_at < now() - interval '30 days')
    """
)


def backoff_seconds(attempts: int) -> int:
    return int(min(30 * 2 ** max(attempts - 1, 0), 3600))


@dataclass
class Dispatcher:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    sender: EmailSender
    handlers: dict[str, OutboxHandler] = field(
        default_factory=lambda: {
            **identity.OUTBOX_HANDLERS,
            **writing.OUTBOX_HANDLERS,
            **speaking.OUTBOX_HANDLERS,
        }
    )

    async def process_batch(self) -> int:
        async with self.session_factory() as db, db.begin():
            claimed = (await db.execute(_CLAIM, {"lease": LEASE_SECONDS, "batch": BATCH})).all()
        for message_id, topic, payload, attempts in claimed:
            await self._process(message_id, topic, payload, attempts)
        return len(claimed)

    async def _process(
        self, message_id: Any, topic: str, payload: dict[str, Any], attempts: int
    ) -> None:
        handler = self.handlers.get(topic)
        try:
            if handler is None:
                raise LookupError(f"no handler for topic {topic}")
            context = OutboxContext(
                settings=self.settings,
                session_factory=self.session_factory,
                sender=self.sender,
                message_id=message_id,
            )
            result = await handler(context, payload)
        except Exception as exc:
            log.warning(
                "outbox.failed",
                id=str(message_id),
                topic=topic,
                attempts=attempts,
                error=type(exc).__name__,
            )
            await self._write(
                _FAIL,
                {
                    "id": message_id,
                    "attempts": attempts,
                    "max_attempts": MAX_ATTEMPTS,
                    "backoff": backoff_seconds(attempts),
                    "error": type(exc).__name__,
                },
            )
            return
        log.info("outbox.done", id=str(message_id), topic=topic, result=result)
        await self._write(
            _COMPLETE,
            {"id": message_id, "attempts": attempts, "status": result, "sent": result == "sent"},
        )

    async def _write(self, statement: Any, params: dict[str, Any]) -> None:
        try:
            async with self.session_factory() as db, db.begin():
                await db.execute(statement, params)
        except Exception as exc:
            log.error("outbox.write_failed", error=type(exc).__name__)

    async def sweep_attempts(self) -> int:
        """Auto-submit exam attempts past deadline + grace (EXAMINATION_ENGINE_DESIGN.md §4.1)."""
        async with self.session_factory() as db, db.begin():
            swept = await exams.sweep_expired(db)
        if swept:
            log.info("exams.sweep", auto_submitted=swept)
        return swept

    async def cleanup(self) -> None:
        async with self.session_factory() as db, db.begin():
            result = cast(CursorResult[Any], await db.execute(_CLEANUP))
            outbox = result.rowcount
            identity_counts = await identity.cleanup(db)
        log.info("outbox.cleanup", outbox_messages=outbox, **identity_counts)


async def run(settings: Settings) -> None:
    if settings.auth_secret_key is None:
        raise SystemExit(
            "AUTH_SECRET_KEY is required by the outbox worker (it derives email links)"
        )
    engine = create_engine(settings, application_name="ielts-worker")
    dispatcher = Dispatcher(settings, create_session_factory(engine), SmtpEmailSender(settings))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows development shells
            loop.add_signal_handler(sig, stop.set)
    log.info("outbox.started", poll_seconds=settings.outbox_poll_interval_seconds)
    last_cleanup = 0.0
    last_sweep = 0.0
    try:
        while not stop.is_set():
            try:
                processed = await dispatcher.process_batch()
                if time.monotonic() - last_sweep > SWEEP_INTERVAL_SECONDS:
                    await dispatcher.sweep_attempts()
                    last_sweep = time.monotonic()
                if time.monotonic() - last_cleanup > CLEANUP_INTERVAL_SECONDS:
                    await dispatcher.cleanup()
                    last_cleanup = time.monotonic()
            except Exception as exc:
                log.error("outbox.loop_error", error=type(exc).__name__)
                processed = 0
            if processed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        stop.wait(), timeout=settings.outbox_poll_interval_seconds
                    )
    finally:
        await engine.dispose()
        log.info("outbox.stopped")


def main() -> None:
    settings = Settings()  # populated from the environment
    configure_logging(settings)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
