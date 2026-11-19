"""Controlled, server-side staff provisioning (Super Admin foundation, 2026-11-19).

There is deliberately **no HTTP endpoint** that grants or revokes roles: staff roles, including
the initial `super_admin`, are assigned only by an operator with database access through
`scripts/admin_cli.py`, which calls these functions. A future "Admin Management" API
(`PUT /admin/users/{id}/roles`, `roles.assign`) will reuse them.

Rules:
- Idempotent: granting a role the account already holds (or revoking one it does not hold)
  changes nothing and writes no audit entry.
- Only an `active` account (email verified) can be promoted, so a stranger who registered an
  address first, without controlling its mailbox, cannot be elevated. A new account can be created
  directly by the operator (`create_staff_account`), with a password the operator supplies.
- Every change revokes the account's existing sessions: elevated (or reduced) privileges always
  start from a fresh sign-in, so a session obtained before the change can never carry them.
- Every change is audited (actor is NULL: the operator acted outside the web application).
- Plaintext passwords are hashed here and never stored, logged or returned.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit import api as audit
from app.modules.identity.models import Role, User, UserProfile, UserRole, UserStatus
from app.modules.identity.passwords import PasswordService, policy_problem
from app.modules.identity.schemas import validate_email as _validate_email
from app.modules.identity.schemas import validate_full_name as _validate_full_name
from app.modules.identity.sessions import revoke_all_sessions
from app.shared.ids import new_id

STAFF_ROLES = ("super_admin", "admin", "content_manager", "reviewer")
SUPER_ADMIN = "super_admin"
VIA = "admin_cli"


class ProvisioningError(Exception):
    """A provisioning request that cannot be carried out (message is operator-facing)."""


@dataclass(frozen=True)
class RoleChange:
    user_id: uuid.UUID
    email: str
    role: str
    changed: bool  # False: the account already was in the requested state (idempotent no-op)
    created: bool = False
    sessions_revoked: int = 0


@dataclass(frozen=True)
class StaffMember:
    user_id: uuid.UUID
    email: str
    full_name: str
    status: str
    roles: tuple[str, ...]


def validate_email(value: str) -> str:
    try:
        return _validate_email(value)
    except ValueError as exc:
        raise ProvisioningError(str(exc)) from exc


def validate_full_name(value: str) -> str:
    try:
        return _validate_full_name(value)
    except ValueError as exc:
        raise ProvisioningError(str(exc)) from exc


def _check_role(role: str) -> None:
    if role not in STAFF_ROLES:
        raise ProvisioningError(
            f"'{role}' is not a staff role. Choose one of: {', '.join(STAFF_ROLES)}."
        )


async def _role_id(db: AsyncSession, role: str) -> uuid.UUID:
    role_id = await db.scalar(select(Role.id).where(Role.code == role))
    if role_id is None:
        raise ProvisioningError(f"Role '{role}' is missing: run database migrations first.")
    return role_id


async def _locked_user(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email).with_for_update())


async def _audit(
    db: AsyncSession, action: str, user_id: uuid.UUID, changes: dict[str, str]
) -> None:
    await audit.record(
        db,
        actor_id=None,
        action=action,
        entity_type="user",
        entity_id=user_id,
        changes={**changes, "via": VIA},
    )


async def account_exists(db: AsyncSession, email: str) -> bool:
    return await db.scalar(select(User.id).where(User.email == validate_email(email))) is not None


async def grant_role(db: AsyncSession, *, email: str, role: str) -> RoleChange:
    """Give an existing, active account a staff role. Runs in the caller's transaction."""
    _check_role(role)
    email = validate_email(email)
    role_id = await _role_id(db, role)
    user = await _locked_user(db, email)
    if user is None:
        raise ProvisioningError("No account with this email address exists.")
    if user.status != UserStatus.ACTIVE.value:
        raise ProvisioningError(
            f"The account is '{user.status}'. Only an active account (email verified, not "
            "suspended or deleted) can be given a staff role."
        )
    inserted = await db.execute(
        insert(UserRole)
        .values(user_id=user.id, role_id=role_id, granted_by=None)
        .on_conflict_do_nothing()
        .returning(UserRole.role_id)
    )
    if inserted.first() is None:
        return RoleChange(user.id, user.email, role, changed=False)
    revoked = await revoke_all_sessions(db, user.id, "role_granted")
    await _audit(db, "identity.role.granted", user.id, {"role": role})
    return RoleChange(user.id, user.email, role, changed=True, sessions_revoked=revoked)


async def create_staff_account(
    db: AsyncSession,
    passwords: PasswordService,
    *,
    email: str,
    full_name: str,
    password: str,
    role: str,
) -> RoleChange:
    """Create an active staff account with a role, or, if the email already has an account,
    behave exactly like `grant_role` (the existing password is never changed)."""
    _check_role(role)
    email = validate_email(email)
    if await account_exists(db, email):
        return await grant_role(db, email=email, role=role)
    full_name = validate_full_name(full_name)
    problem = policy_problem(password, email=email)
    if problem is not None:
        raise ProvisioningError(f"Password rejected: {problem}")
    role_id = await _role_id(db, role)
    password_hash = await passwords.hash(password)
    user_id = new_id()
    # The operator vouches for the address; the account is usable immediately.
    db.add(
        User(
            id=user_id,
            email=email,
            password_hash=password_hash,
            status=UserStatus.ACTIVE.value,
            email_verified_at=func.now(),
        )
    )
    db.add(UserProfile(user_id=user_id, full_name=full_name))
    await db.flush()
    db.add(UserRole(user_id=user_id, role_id=role_id, granted_by=None))
    await _audit(db, "identity.user.provisioned", user_id, {})
    await _audit(db, "identity.role.granted", user_id, {"role": role})
    return RoleChange(user_id, email, role, changed=True, created=True)


async def revoke_role(
    db: AsyncSession, *, email: str, role: str, allow_no_super_admin: bool = False
) -> RoleChange:
    """Remove a staff role. Refuses to remove the last active super admin unless explicitly
    allowed, so the platform cannot be locked out of its own administration by accident."""
    _check_role(role)
    email = validate_email(email)
    role_id = await _role_id(db, role)
    user = await _locked_user(db, email)
    if user is None:
        raise ProvisioningError("No account with this email address exists.")
    held = await db.scalar(
        select(UserRole.role_id).where(UserRole.user_id == user.id, UserRole.role_id == role_id)
    )
    if held is None:
        return RoleChange(user.id, user.email, role, changed=False)
    if role == SUPER_ADMIN and not allow_no_super_admin:
        others = await db.scalar(
            select(func.count())
            .select_from(UserRole)
            .join(User, User.id == UserRole.user_id)
            .where(
                UserRole.role_id == role_id,
                UserRole.user_id != user.id,
                User.status == UserStatus.ACTIVE.value,
            )
        )
        if not others:
            raise ProvisioningError(
                "This is the last active super admin. Provision another one first, or pass "
                "--allow-no-super-admin to remove it anyway."
            )
    await db.execute(
        delete(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_id)
    )
    revoked = await revoke_all_sessions(db, user.id, "role_revoked")
    await _audit(db, "identity.role.revoked", user.id, {"role": role})
    return RoleChange(user.id, user.email, role, changed=True, sessions_revoked=revoked)


async def list_staff(db: AsyncSession) -> list[StaffMember]:
    rows = (
        await db.execute(
            select(User.id, User.email, UserProfile.full_name, User.status, Role.code)
            .join(UserProfile, UserProfile.user_id == User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.code.in_(STAFF_ROLES))
            .order_by(User.email, Role.code)
        )
    ).all()
    members: dict[uuid.UUID, StaffMember] = {}
    for user_id, email, full_name, status, code in rows:
        current = members.get(user_id)
        roles = (*current.roles, code) if current else (code,)
        members[user_id] = StaffMember(user_id, email, full_name, status, roles)
    return list(members.values())
