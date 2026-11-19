"""Identity HTTP API under /api/v1 (docs/API_SPECIFICATION.md §2).

Every unsafe method here is CSRF-protected by `CsrfMiddleware` (including login/register).
Responses are `Cache-Control: no-store`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.modules.identity import service
from app.modules.identity.csrf import issue_token, set_csrf_cookie
from app.modules.identity.deps import (
    auth_runtime,
    client_meta,
    current_user,
    optional_current_user,
    require_staff,
    session_token,
)
from app.modules.identity.schemas import (
    AcceptedResponse,
    ChangePasswordRequest,
    CsrfResponse,
    EmailRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    RegistrationPolicyResponse,
    ResetPasswordRequest,
    TokenRequest,
)
from app.modules.identity.service import AuthRuntime, ClientMeta
from app.modules.identity.sessions import (
    CurrentUser,
    clear_session_cookie,
    set_session_cookie,
)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1", tags=["auth"], dependencies=[Depends(_no_store)])

Db = Annotated[AsyncSession, Depends(get_db_session)]
Runtime = Annotated[AuthRuntime, Depends(auth_runtime)]
Meta = Annotated[ClientMeta, Depends(client_meta)]
User = Annotated[CurrentUser, Depends(current_user)]
OptionalUser = Annotated[CurrentUser | None, Depends(optional_current_user)]


def _problem(*descriptions: tuple[int, str]) -> dict[int | str, dict[str, object]]:
    return {
        code: {"description": text, "content": {PROBLEM_MEDIA_TYPE: {}}}
        for code, text in descriptions
    }


ACCEPTED_DETAIL = "If the details are valid, we've sent an email with the next step."


def _me(user: CurrentUser) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        email_verified=user.email_verified,
        roles=sorted(user.roles),
        permissions=sorted(user.permissions),
    )


def _start_session(response: Response, rt: AuthRuntime, token: str) -> None:
    set_session_cookie(response, rt.settings, token)
    set_csrf_cookie(response, rt.settings, issue_token(rt.keys, token))


def _end_session(response: Response, rt: AuthRuntime) -> None:
    clear_session_cookie(response, rt.settings)
    set_csrf_cookie(response, rt.settings, issue_token(rt.keys, None))


@router.get("/auth/csrf", response_model=CsrfResponse, summary="Issue a CSRF token")
async def get_csrf(request: Request, response: Response, rt: Runtime) -> CsrfResponse:
    token = issue_token(rt.keys, session_token(request))
    set_csrf_cookie(response, rt.settings, token)
    return CsrfResponse(csrf_token=token)


@router.get(
    "/auth/registration-policy",
    response_model=RegistrationPolicyResponse,
    summary="What the registration form must display",
)
async def registration_policy(rt: Runtime) -> RegistrationPolicyResponse:
    s = rt.settings
    return RegistrationPolicyResponse(
        open=s.registration_open,
        minimum_age=s.registration_minimum_age,
        terms_version=s.terms_version_effective,
        privacy_version=s.privacy_version_effective,
        development_placeholders=s.is_dev_like and s.uses_policy_placeholders,
    )


@router.post(
    "/auth/register",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedResponse,
    responses=_problem(
        (403, "Registration closed"),
        (422, "Invalid input or password policy"),
        (429, "Rate limited"),
    ),
)
async def register(body: RegisterRequest, db: Db, rt: Runtime, meta: Meta) -> AcceptedResponse:
    await service.register(db, rt, meta, body)
    return AcceptedResponse(detail=ACCEPTED_DETAIL)


@router.post(
    "/auth/verify-email",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_problem((400, "Invalid or expired link"), (429, "Rate limited")),
)
async def verify_email(body: TokenRequest, db: Db, rt: Runtime, meta: Meta) -> None:
    await service.verify_email(db, rt, meta, body.token)


@router.post(
    "/auth/verify-email/resend",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedResponse,
    responses=_problem((429, "Rate limited")),
)
async def resend_verification(
    body: EmailRequest, db: Db, rt: Runtime, meta: Meta
) -> AcceptedResponse:
    await service.resend_verification(db, rt, meta, body.email)
    return AcceptedResponse(detail=ACCEPTED_DETAIL)


@router.post(
    "/auth/login",
    response_model=MeResponse,
    responses=_problem(
        (401, "Invalid credentials"), (403, "Email not verified"), (429, "Rate limited")
    ),
)
async def login(
    body: LoginRequest, request: Request, response: Response, db: Db, rt: Runtime, meta: Meta
) -> MeResponse:
    token, user = await service.login(
        db,
        rt,
        meta,
        email=body.email,
        password=body.password,
        previous_token=session_token(request),
    )
    _start_session(response, rt, token)
    return _me(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, db: Db, rt: Runtime, meta: Meta, user: OptionalUser
) -> None:
    await service.logout(db, meta, user=user, token=session_token(request))
    _end_session(response, rt)


@router.post(
    "/auth/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_problem((401, "Not signed in")),
)
async def logout_all(response: Response, db: Db, rt: Runtime, meta: Meta, user: User) -> None:
    await service.logout_all(db, meta, user)
    _end_session(response, rt)


@router.post(
    "/auth/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedResponse,
    responses=_problem((429, "Rate limited")),
)
async def forgot_password(body: EmailRequest, db: Db, rt: Runtime, meta: Meta) -> AcceptedResponse:
    await service.forgot_password(db, rt, meta, body.email)
    return AcceptedResponse(detail=ACCEPTED_DETAIL)


@router.post(
    "/auth/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_problem(
        (400, "Invalid or expired link"), (422, "Password policy"), (429, "Rate limited")
    ),
)
async def reset_password(
    body: ResetPasswordRequest, response: Response, db: Db, rt: Runtime, meta: Meta
) -> None:
    await service.reset_password(db, rt, meta, raw=body.token, new_password=body.new_password)
    _end_session(response, rt)  # every session was revoked; this browser signs in again


@router.get("/me", response_model=MeResponse, responses=_problem((401, "Not signed in")))
async def me(user: User) -> MeResponse:
    return _me(user)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_problem(
        (400, "Current password incorrect"), (401, "Not signed in"), (422, "Password policy")
    ),
)
async def change_password(
    body: ChangePasswordRequest, response: Response, db: Db, rt: Runtime, meta: Meta, user: User
) -> None:
    token = await service.change_password(
        db, rt, meta, user, current_password=body.current_password, new_password=body.new_password
    )
    _start_session(response, rt, token)


@router.get(
    "/admin/session",
    response_model=MeResponse,
    summary="Verify a staff session (server-side gate for the admin area)",
    responses=_problem((401, "Not signed in"), (403, "Not staff, or two-factor required")),
)
async def admin_session(
    user: Annotated[CurrentUser, Depends(require_staff)],
) -> MeResponse:
    return _me(user)
