"""Staff provisioning CLI: the only way to grant or revoke staff roles (no HTTP endpoint does).

    uv run --env-file .env python scripts/admin_cli.py <command> [...]

Commands
  create-staff EMAIL --full-name NAME [--role super_admin] [--password-env VAR]
        Create an active staff account, or give an existing active account the role.
        An existing account's password is never changed.
  grant-role EMAIL --role ROLE        give an existing, active account a staff role
  revoke-role EMAIL --role ROLE [--allow-no-super-admin]
  list-staff                          staff accounts and their roles

Roles: super_admin, admin, content_manager, reviewer.

Passwords are never accepted as command-line arguments (they would land in shell history and
process listings). The password is read from the environment variable named by --password-env
(for scripted deployments: inject it from the secret store, then unset it), or prompted for
interactively without echo. It is hashed with Argon2id and never printed or logged.

Every command is idempotent and audited, and every role change revokes the account's existing
sessions (the person signs in again). Run it where the deployment's DATABASE_URL, REDIS_URL and
AUTH_SECRET_KEY are configured: the full application settings are validated first.

Note: staff sign-in is refused wherever STAFF_MFA_REQUIRED is in effect (always in production)
until staff two-factor authentication is implemented; provisioning itself works everywhere.
"""

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import create_engine, create_session_factory
from app.modules.identity.passwords import PasswordService
from app.modules.identity.provisioning import (
    STAFF_ROLES,
    SUPER_ADMIN,
    ProvisioningError,
    RoleChange,
    account_exists,
    create_staff_account,
    grant_role,
    list_staff,
    revoke_role,
)


def read_password(env_var: str | None, *, interactive: bool | None = None) -> str:
    """Password from a named environment variable, or an interactive no-echo prompt."""
    if env_var:
        value = os.environ.get(env_var)
        if not value:
            raise ProvisioningError("The environment variable named by --password-env is empty.")
        return value
    if interactive is None:
        interactive = sys.stdin.isatty()
    if not interactive:
        raise ProvisioningError(
            "No terminal for a password prompt: pass --password-env VAR with the password in VAR."
        )
    first = getpass.getpass("Password for the new account: ")
    if first != getpass.getpass("Repeat the password: "):
        raise ProvisioningError("The passwords do not match.")
    return first


def describe(change: RoleChange, verb: str) -> str:
    if not change.changed:
        state = "already has" if verb == "granted" else "does not have"
        return f"No change: {change.email} {state} the '{change.role}' role."
    parts = [f"Role '{change.role}' {verb} for {change.email} (user {change.user_id})."]
    if change.created:
        parts.insert(0, f"Created active account {change.email}.")
    if change.sessions_revoked:
        parts.append(f"{change.sessions_revoked} existing session(s) revoked: sign in again.")
    return " ".join(parts)


async def _run(settings: Settings, action: Callable[[AsyncSession], Awaitable[str]]) -> str:
    engine = create_engine(settings)
    try:
        async with create_session_factory(engine)() as session, session.begin():
            return await action(session)
    finally:
        await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    # allow_abbrev=False: otherwise `--password SECRET` would be accepted as `--password-env`.
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-staff", allow_abbrev=False)
    create.add_argument("email")
    create.add_argument("--full-name", required=True)
    create.add_argument("--role", choices=STAFF_ROLES, default=SUPER_ADMIN)
    create.add_argument("--password-env", metavar="VAR")
    grant = sub.add_parser("grant-role", allow_abbrev=False)
    grant.add_argument("email")
    grant.add_argument("--role", choices=STAFF_ROLES, required=True)
    revoke = sub.add_parser("revoke-role", allow_abbrev=False)
    revoke.add_argument("email")
    revoke.add_argument("--role", choices=STAFF_ROLES, required=True)
    revoke.add_argument("--allow-no-super-admin", action="store_true")
    sub.add_parser("list-staff")
    return parser


async def execute(args: argparse.Namespace, settings: Settings) -> str:
    if args.command == "create-staff":
        passwords = PasswordService(
            memory_kib=settings.password_hash_memory_kib,
            iterations=settings.password_hash_iterations,
            concurrency=1,
        )

        async def create(db: AsyncSession) -> str:
            # Ask for a password only when an account will actually be created.
            exists = await account_exists(db, args.email)
            password = "" if exists else read_password(args.password_env)
            change = await create_staff_account(
                db,
                passwords,
                email=args.email,
                full_name=args.full_name,
                password=password,
                role=args.role,
            )
            return describe(change, "granted")

        return await _run(settings, create)
    if args.command == "grant-role":

        async def grant(db: AsyncSession) -> str:
            return describe(await grant_role(db, email=args.email, role=args.role), "granted")

        return await _run(settings, grant)
    if args.command == "revoke-role":

        async def revoke(db: AsyncSession) -> str:
            change = await revoke_role(
                db,
                email=args.email,
                role=args.role,
                allow_no_super_admin=args.allow_no_super_admin,
            )
            return describe(change, "revoked")

        return await _run(settings, revoke)

    async def show(db: AsyncSession) -> str:
        members = await list_staff(db)
        if not members:
            return "No staff accounts."
        return "\n".join(
            f"{m.email:40} {m.status:10} {', '.join(m.roles):30} {m.full_name}" for m in members
        )

    return await _run(settings, show)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings()
        print(asyncio.run(execute(args, settings)))
    except ProvisioningError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
