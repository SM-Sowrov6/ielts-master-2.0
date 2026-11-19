"""Identity error types (stable problem codes, docs/API_SPECIFICATION.md §1).

Messages are deliberately generic where detail would reveal whether an account exists.
"""

from app.core.errors import DomainError


class NotAuthenticatedError(DomainError):
    status_code = 401
    code = "not_authenticated"
    title = "Sign in to continue."


class InvalidCredentialsError(DomainError):
    status_code = 401
    code = "invalid_credentials"
    title = "The email or password is incorrect."


class EmailNotVerifiedError(DomainError):
    """Raised only after a correct password, so it reveals nothing to someone without it."""

    status_code = 403
    code = "email_not_verified"
    title = "Verify your email address before signing in."


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "permission_denied"
    title = "You do not have permission to do this."


class MfaRequiredError(DomainError):
    status_code = 403
    code = "mfa_required"
    title = "Two-factor authentication is required for this area."


class RegistrationClosedError(DomainError):
    status_code = 403
    code = "registration_closed"
    title = "Registration is not open yet."


class ConsentRequiredError(DomainError):
    status_code = 422
    code = "consent_required"
    title = "Please accept the required terms to continue."


class PasswordPolicyError(DomainError):
    status_code = 422
    code = "password_policy"
    title = "Choose a stronger password."


class TokenInvalidError(DomainError):
    status_code = 400
    code = "token_invalid"
    title = "This link is invalid or has expired."


class CurrentPasswordIncorrectError(DomainError):
    status_code = 400
    code = "current_password_incorrect"
    title = "Your current password is incorrect."


class RateLimitedError(DomainError):
    status_code = 429
    code = "rate_limited"
    title = "Too many attempts. Please wait and try again."


class RateLimiterUnavailableError(DomainError):
    """Auth endpoints fail closed when the rate limiter's store (Redis) is unavailable."""

    status_code = 503
    code = "rate_limiter_unavailable"
    title = "This service is temporarily unavailable. Please try again shortly."
