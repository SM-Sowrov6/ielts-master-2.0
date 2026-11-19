"""Request/response schemas for the identity API. Requests forbid unknown fields (mass-assignment
protection, SECURITY_GUIDELINES.md §4.3). Validation errors never echo submitted values
(app/core/errors.py), so passwords cannot leak through 422 responses.
"""

import re
import unicodedata
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
_DOMAIN = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9-]{2,63}$")


def _validate_email(value: str) -> str:
    value = value.strip()
    local, sep, domain = value.rpartition("@")
    if not sep or not local or len(local) > 64 or not _LOCAL.match(local):
        raise ValueError("Enter a valid email address.")
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Enter a valid email address.") from exc
    if len(ascii_domain) > 253 or not _DOMAIN.match(ascii_domain):
        raise ValueError("Enter a valid email address.")
    return f"{local}@{ascii_domain.lower()}"


def _validate_full_name(value: str) -> str:
    value = " ".join(unicodedata.normalize("NFC", value).split())
    if not value:
        raise ValueError("Enter your name.")
    if len(value) > 100:
        raise ValueError("Use at most 100 characters.")
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        raise ValueError("Remove unsupported characters from your name.")
    return value


# Public aliases for non-HTTP callers (staff provisioning CLI): the same rules as the API.
validate_email = _validate_email
validate_full_name = _validate_full_name

Email = Annotated[str, Field(max_length=254), AfterValidator(_validate_email)]
LoginEmail = Annotated[str, Field(min_length=1, max_length=254), AfterValidator(str.strip)]
# Policy (10..128 code points) is enforced by the service with a clear message; the schema cap
# only bounds request size.
Password = Annotated[str, Field(min_length=1, max_length=1024)]
Token = Annotated[str, Field(min_length=1, max_length=100)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(_Request):
    full_name: Annotated[str, Field(max_length=300), AfterValidator(_validate_full_name)]
    email: Email
    password: Password
    accept_terms: bool
    age_confirmation: bool


class LoginRequest(_Request):
    email: LoginEmail
    password: Password


class EmailRequest(_Request):
    email: Email


class TokenRequest(_Request):
    token: Token


class ResetPasswordRequest(_Request):
    token: Token
    new_password: Password


class ChangePasswordRequest(_Request):
    current_password: Password
    new_password: Password


class AcceptedResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    detail: str


class CsrfResponse(BaseModel):
    csrf_token: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    email_verified: bool
    roles: list[str]
    permissions: list[str]


class RegistrationPolicyResponse(BaseModel):
    """What the registration form must show. No age or legal policy is invented: when the
    decisions are pending (D-13/D-17), only local/ci serve development placeholders."""

    open: bool
    minimum_age: int | None
    terms_version: str
    privacy_version: str
    development_placeholders: bool


class MfaStatusResponse(BaseModel):
    enrolled: bool  # a confirmed authenticator exists
    verified: bool  # this session passed the second factor
    required: bool  # the staff area demands it for this account
    recovery_codes_left: int


class MfaSetupResponse(BaseModel):
    secret: str  # base32, for manual entry
    otpauth_uri: str  # for the QR code


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class MfaEnrolledResponse(BaseModel):
    recovery_codes: list[str]  # shown once; store them safely
