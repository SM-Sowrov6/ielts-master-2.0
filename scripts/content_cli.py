"""Content operations CLI (Phase 5a). The admin HTTP API arrives in Phase 5c, after RBAC (3b).

    uv run --env-file .env python scripts/content_cli.py <command> [...]

Commands
  export-schema                       write docs/schemas/test-version-import.schema.json
  licence-create --source-type ... --licensor ... [--valid-until YYYY-MM-DD]
  import FILE --licence ID --actor ID dry-run: validate, record a job, print issues
  import-commit JOB_ID --actor ID     create a draft version from a validated job
  new-draft TEST_ID --actor ID        deep-copy the current version into a new draft
  submit VERSION_ID --actor ID        validate (publish rules) and move draft -> in_review
  review VERSION_ID --actor ID --decision approved|changes_requested [--comment ...]
  publish VERSION_ID --actor ID       in_review -> published (archives the previous version)

`--actor` is a plain UUID until user accounts exist (Phase 3b). Refuses to run when
APP_ENV=production: real third-party content must not be loaded before D-04 is resolved.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DatabaseSettings
from app.core.database import create_engine, create_session_factory
from app.modules.content import importer, service
from app.modules.content.enums import LicenceSource, ReviewDecision
from app.modules.content.errors import ContentValidationError
from app.modules.content.models import ContentLicence
from app.modules.content.question_types.base import ValidationIssue

SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "schemas" / "test-version-import.schema.json"
)


def _print_issues(issues: list[ValidationIssue]) -> None:
    for issue in issues:
        level = issue.severity.value.upper()
        print(f"  [{level:7}] {issue.code:32} {issue.location}: {issue.message}")
    errors = sum(1 for i in issues if i.is_error)
    print(f"  -> {errors} error(s), {len(issues) - errors} warning(s)")


async def _run(action: Callable[[AsyncSession], Awaitable[None]]) -> None:
    engine = create_engine(DatabaseSettings())
    try:
        async with create_session_factory(engine)() as session, session.begin():
            await action(session)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("export-schema")
    lic = sub.add_parser("licence-create")
    lic.add_argument("--source-type", required=True, choices=[s.value for s in LicenceSource])
    lic.add_argument("--licensor", required=True)
    lic.add_argument("--reference")
    lic.add_argument("--valid-from", type=date.fromisoformat)
    lic.add_argument("--valid-until", type=date.fromisoformat)
    imp = sub.add_parser("import")
    imp.add_argument("file", type=Path)
    imp.add_argument("--licence", type=uuid.UUID, required=True)
    imp.add_argument("--actor", type=uuid.UUID, required=True)
    com = sub.add_parser("import-commit")
    com.add_argument("job_id", type=uuid.UUID)
    com.add_argument("--actor", type=uuid.UUID, required=True)
    for name in ("new-draft", "submit", "publish"):
        cmd = sub.add_parser(name)
        cmd.add_argument("target_id", type=uuid.UUID)
        cmd.add_argument("--actor", type=uuid.UUID, required=True)
    rev = sub.add_parser("review")
    rev.add_argument("target_id", type=uuid.UUID)
    rev.add_argument("--actor", type=uuid.UUID, required=True)
    rev.add_argument("--decision", required=True, choices=[d.value for d in ReviewDecision])
    rev.add_argument("--comment")
    args = parser.parse_args(argv)

    if args.command == "export-schema":
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_text(
            json.dumps(importer.import_json_schema(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {SCHEMA_PATH}")
        return 0
    if os.environ.get("APP_ENV", "local") == "production":
        print("Refusing to run content commands with APP_ENV=production (D-04 unresolved).")
        return 2

    async def licence_create(session: AsyncSession) -> None:
        licence = ContentLicence(
            source_type=args.source_type,
            licensor=args.licensor,
            licence_reference=args.reference,
            valid_from=args.valid_from,
            valid_until=args.valid_until,
        )
        session.add(licence)
        await session.flush()
        print(f"licence {licence.id}")

    async def do_import(session: AsyncSession) -> None:
        result = await importer.dry_run(
            session,
            args.file.read_bytes(),
            file_name=args.file.name,
            license_id=args.licence,
            actor_id=args.actor,
        )
        print(f"import job {result.job.id}: {result.job.status}")
        _print_issues(result.issues)

    async def do_commit(session: AsyncSession) -> None:
        version = await importer.commit(session, args.job_id, actor_id=args.actor)
        print(f"draft test_version {version.id} (version_no {version.version_no})")

    async def new_draft(session: AsyncSession) -> None:
        version = await service.create_next_draft(session, args.target_id, actor_id=args.actor)
        print(f"draft test_version {version.id} (version_no {version.version_no})")

    async def submit(session: AsyncSession) -> None:
        warnings = await service.submit_for_review(session, args.target_id, actor_id=args.actor)
        print("submitted for review")
        _print_issues(warnings)

    async def review(session: AsyncSession) -> None:
        await service.review_version(
            session,
            args.target_id,
            reviewer_id=args.actor,
            decision=ReviewDecision(args.decision),
            comment=args.comment,
        )
        print(f"review recorded: {args.decision}")

    async def publish(session: AsyncSession) -> None:
        version = await service.publish_version(session, args.target_id, actor_id=args.actor)
        print(f"published test_version {version.id}")

    actions: dict[str, Callable[[AsyncSession], Awaitable[None]]] = {
        "licence-create": licence_create,
        "import": do_import,
        "import-commit": do_commit,
        "new-draft": new_draft,
        "submit": submit,
        "review": review,
        "publish": publish,
    }
    try:
        asyncio.run(_run(actions[args.command]))
    except ContentValidationError as exc:
        print(f"{exc.title}:")
        _print_issues(exc.issues)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
