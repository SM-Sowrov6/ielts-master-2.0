"""Identity emails: outbox topics, payloads, templates and delivery handlers.

Token lifecycle (verify email 24 h, reset password 30 min):
1. Request transaction: older unconsumed tokens of the same purpose are superseded; the new
   token's SHA-256 hash is inserted; an outbox message carries {token_id, salt}. Commit is atomic,
   so either both exist or neither does.
2. Worker: claims the message, re-checks that the token is still current (not consumed,
   superseded or expired, account still eligible) and otherwise SKIPS it; re-derives the raw token
   from the salt with AUTH_SECRET_KEY, confirms it matches the stored hash and sends the link.
3. Retries after SMTP or database failures re-send the same still-valid link (same Message-ID).
4. Terminal messages have their payload cleared; old rows are deleted by `cleanup`.
Links carry the token in the URL fragment (`#token=`), which browsers never send to servers or
in Referer headers.
"""

import base64
import html
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import OutgoingEmail
from app.core.outbox import HandlerResult, OutboxContext, OutboxHandler
from app.modules.identity.models import (
    AuthSession,
    OneTimeToken,
    TokenPurpose,
    User,
    UserProfile,
    UserStatus,
)
from app.modules.identity.tokens import AuthKeys, b64_decode, derive_one_time_token, hash_token

log = structlog.get_logger("app.identity.emails")

TOPIC_VERIFY_EMAIL = "identity.verify_email"
TOPIC_RESET_PASSWORD = "identity.reset_password"  # noqa: S105 — topic name
TOPIC_ACCOUNT_EXISTS = "identity.account_exists"
TOPIC_PASSWORD_CHANGED = "identity.password_changed"  # noqa: S105 — topic name

BRAND = "IELTS MASTER"
PRIMARY = "#2563EB"


def token_payload(token_id: uuid.UUID, salt: bytes) -> dict[str, Any]:
    return {"token_id": str(token_id), "salt": base64.urlsafe_b64encode(salt).decode("ascii")}


def user_payload(user_id: uuid.UUID) -> dict[str, Any]:
    return {"user_id": str(user_id)}


# --- Templates ----------------------------------------------------------------------------------
def _render(
    *, greeting_name: str, paragraphs: list[str], action: tuple[str, str] | None, footer: str
) -> tuple[str, str]:
    text_parts = [f"Hi {greeting_name},", *paragraphs]
    if action:
        text_parts.append(f"{action[0]}: {action[1]}")
    text_parts.append(footer)
    text = "\n\n".join(text_parts) + f"\n\n— {BRAND}\n"

    esc = html.escape
    button = ""
    if action:
        button = (
            f'<p style="margin:24px 0"><a href="{esc(action[1], quote=True)}" '
            f'style="background:{PRIMARY};color:#ffffff;padding:12px 20px;border-radius:8px;'
            f'text-decoration:none;font-weight:600;display:inline-block">{esc(action[0])}</a></p>'
            f'<p style="color:#475569;font-size:13px">If the button does not work, copy this link '
            f'into your browser:<br><span style="word-break:break-all">{esc(action[1])}</span></p>'
        )
    body = "".join(f'<p style="margin:0 0 16px">{esc(p)}</p>' for p in paragraphs)
    page = (
        '<!doctype html><html lang="en"><body style="margin:0;background:#f8fafc;'
        'font-family:Geist,Inter,Segoe UI,Arial,sans-serif;color:#0f172a">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td align="center" style="padding:32px 16px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:560px;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px">'
        f'<tr><td style="padding:28px 32px"><p style="margin:0 0 24px;font-weight:700;'
        f'font-size:18px">IELTS <span style="color:{PRIMARY}">MASTER</span></p>'
        f'<p style="margin:0 0 16px">Hi {esc(greeting_name)},</p>{body}{button}'
        f'<p style="margin:24px 0 0;color:#475569;font-size:13px">{esc(footer)}</p>'
        "</td></tr></table></td></tr></table></body></html>"
    )
    return text, page


def _message_id(ctx: OutboxContext) -> str:
    domain = (ctx.settings.email_from or "ielts-master.invalid").rpartition("@")[2].strip("> ")
    return f"<outbox-{ctx.message_id}@{domain or 'ielts-master.invalid'}>"


def _first_name(full_name: str) -> str:
    return full_name.split(" ", 1)[0] or "there"


# --- Handlers -------------------------------------------------------------------------------------
async def _load_user(ctx: OutboxContext, user_id: uuid.UUID) -> tuple[User, str] | None:
    async with ctx.session_factory() as db:
        row = (
            await db.execute(
                select(User, UserProfile.full_name)
                .join(UserProfile, UserProfile.user_id == User.id)
                .where(User.id == user_id)
            )
        ).one_or_none()
    return (row[0], row[1]) if row else None


async def _send_token_email(ctx: OutboxContext, payload: dict[str, Any]) -> HandlerResult:
    token_id = uuid.UUID(str(payload["token_id"]))
    salt = b64_decode(str(payload["salt"]))
    async with ctx.session_factory() as db:
        row = (
            await db.execute(
                select(OneTimeToken, User, UserProfile.full_name)
                .join(User, User.id == OneTimeToken.user_id)
                .join(UserProfile, UserProfile.user_id == User.id)
                .where(OneTimeToken.id == token_id)
            )
        ).one_or_none()
    if row is None:
        return "skipped"
    token, user, full_name = row
    if token.consumed_at is not None or token.expires_at <= datetime.now(UTC):
        return "skipped"  # superseded, used or expired: never send a dead link
    eligible = {
        TokenPurpose.VERIFY_EMAIL.value: {UserStatus.PENDING.value},
        TokenPurpose.RESET_PASSWORD.value: {UserStatus.PENDING.value, UserStatus.ACTIVE.value},
    }[token.purpose]
    if user.status not in eligible:
        return "skipped"
    raw = derive_one_time_token(
        AuthKeys.from_settings(ctx.settings).one_time_token, token.purpose, salt
    )
    if hash_token(raw) != token.token_hash:
        log.error("outbox.token_mismatch", token_id=str(token_id))  # e.g. AUTH_SECRET_KEY changed
        return "skipped"
    base = str(ctx.settings.public_app_url).rstrip("/")
    if token.purpose == TokenPurpose.VERIFY_EMAIL.value:
        subject = f"Verify your email for {BRAND}"
        link = f"{base}/verify-email#token={raw}"
        text, page = _render(
            greeting_name=_first_name(full_name),
            paragraphs=[
                f"Confirm your email address to finish creating your {BRAND} account.",
                "This link expires in 24 hours and can be used once.",
            ],
            action=("Verify email address", link),
            footer="If you didn't create an account, you can ignore this email.",
        )
    else:
        subject = f"Reset your {BRAND} password"
        link = f"{base}/reset-password#token={raw}"
        text, page = _render(
            greeting_name=_first_name(full_name),
            paragraphs=[
                "We received a request to reset your password.",
                "This link expires in 30 minutes and can be used once.",
            ],
            action=("Choose a new password", link),
            footer="If you didn't ask for this, ignore this email. Your password won't change.",
        )
    await ctx.sender.send(
        OutgoingEmail(
            to=user.email, subject=subject, text=text, html=page, message_id=_message_id(ctx)
        )
    )
    return "sent"


async def _send_account_exists(ctx: OutboxContext, payload: dict[str, Any]) -> HandlerResult:
    loaded = await _load_user(ctx, uuid.UUID(str(payload["user_id"])))
    if loaded is None or loaded[0].status != UserStatus.ACTIVE.value:
        return "skipped"
    user, full_name = loaded
    base = str(ctx.settings.public_app_url).rstrip("/")
    text, page = _render(
        greeting_name=_first_name(full_name),
        paragraphs=[
            "Someone tried to create an account with this email address. You already have one.",
            f"Forgot your password? You can reset it at {base}/forgot-password",
        ],
        action=("Sign in", f"{base}/sign-in"),
        footer="If this wasn't you, you can ignore this email. Your account has not changed.",
    )
    await ctx.sender.send(
        OutgoingEmail(
            to=user.email,
            subject=f"You already have a {BRAND} account",
            text=text,
            html=page,
            message_id=_message_id(ctx),
        )
    )
    return "sent"


async def _send_password_changed(ctx: OutboxContext, payload: dict[str, Any]) -> HandlerResult:
    loaded = await _load_user(ctx, uuid.UUID(str(payload["user_id"])))
    if loaded is None or loaded[0].status not in (
        UserStatus.ACTIVE.value,
        UserStatus.PENDING.value,
    ):
        return "skipped"
    user, full_name = loaded
    base = str(ctx.settings.public_app_url).rstrip("/")
    text, page = _render(
        greeting_name=_first_name(full_name),
        paragraphs=[
            f"The password for your {BRAND} account was just changed, and every other signed-in"
            " session was signed out.",
            "If you made this change, there's nothing else to do.",
        ],
        action=("Reset your password", f"{base}/forgot-password"),
        footer="If you didn't change your password, reset it now to secure your account.",
    )
    await ctx.sender.send(
        OutgoingEmail(
            to=user.email,
            subject=f"Your {BRAND} password was changed",
            text=text,
            html=page,
            message_id=_message_id(ctx),
        )
    )
    return "sent"


OUTBOX_HANDLERS: dict[str, OutboxHandler] = {
    TOPIC_VERIFY_EMAIL: _send_token_email,
    TOPIC_RESET_PASSWORD: _send_token_email,
    TOPIC_ACCOUNT_EXISTS: _send_account_exists,
    TOPIC_PASSWORD_CHANGED: _send_password_changed,
}


# --- Cleanup (run periodically by the worker) ----------------------------------------------------
TOKEN_RETENTION = timedelta(days=7)
SESSION_RETENTION = timedelta(days=30)


async def cleanup(db: AsyncSession) -> dict[str, int]:
    """Delete spent tokens and dead sessions after their retention window. Caller commits."""
    now = datetime.now(UTC)
    tokens = await db.execute(
        delete(OneTimeToken)
        .where(
            or_(
                OneTimeToken.consumed_at < now - TOKEN_RETENTION,
                OneTimeToken.expires_at < now - TOKEN_RETENTION,
            )
        )
        .returning(OneTimeToken.id)
    )
    sessions = await db.execute(
        delete(AuthSession)
        .where(
            or_(
                AuthSession.revoked_at < now - SESSION_RETENTION,
                AuthSession.idle_expires_at < now - SESSION_RETENTION,
                AuthSession.absolute_expires_at < now - SESSION_RETENTION,
            )
        )
        .returning(AuthSession.id)
    )
    return {"one_time_tokens": len(tokens.all()), "auth_sessions": len(sessions.all())}
