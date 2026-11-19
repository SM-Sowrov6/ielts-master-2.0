"""Typed, validated runtime configuration (twelve-factor: environment variables only)."""

from enum import StrEnum
from functools import lru_cache
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    CI = "ci"
    STAGING = "staging"
    PRODUCTION = "production"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Marker for development-only legal/policy placeholders. Never accepted outside local/ci.
DEV_PLACEHOLDER = "dev-placeholder"

_SETTINGS_CONFIG = SettingsConfigDict(
    env_file=None,
    case_sensitive=False,
    extra="ignore",
    frozen=True,
    # An empty variable (e.g. `STAFF_MFA_REQUIRED=` from a Compose default) means "not set".
    env_ignore_empty=True,
)


class DatabaseSettings(BaseSettings):
    """Database connection settings. Used on its own by Alembic, which needs no Redis/app config."""

    model_config = _SETTINGS_CONFIG

    database_url: PostgresDsn
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60, le=86400)
    db_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    db_echo: bool = False


class Settings(DatabaseSettings):
    """Application settings, validated at startup. The process refuses to boot on invalid config.

    No `.env` file is read implicitly; locally use `uv run --env-file .env ...` or Docker Compose.
    Authentication settings: docs/SECURITY_GUIDELINES.md §2-3. Values left as `None` resolve to
    environment-dependent defaults (see the `*_effective` properties); production rules are
    enforced in `_enforce_environment_rules`.
    """

    model_config = _SETTINGS_CONFIG

    app_env: Environment = Environment.LOCAL
    log_level: LogLevel = "INFO"
    redis_url: RedisDsn
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    # --- Authentication ------------------------------------------------------------------------
    # Public origin of the web app: used for email links and the CSRF Origin check (never the
    # request Host header).
    public_app_url: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")
    # Extra origins accepted by the CSRF Origin check (e.g. http://127.0.0.1:3000 in development).
    csrf_trusted_origins: tuple[str, ...] = ()
    # >= 32 characters of randomness. Keys for CSRF signatures and one-time-token derivation are
    # derived from it. Required outside local/ci; local/ci without it get a per-process random
    # key (fine for tests; the outbox worker always requires an explicit key).
    auth_secret_key: SecretStr | None = None
    session_cookie_secure: bool | None = None  # default: True outside local/ci
    session_idle_ttl_seconds: int = Field(default=7 * 86400, ge=300, le=90 * 86400)
    session_absolute_ttl_seconds: int = Field(default=30 * 86400, ge=3600, le=365 * 86400)
    # Argon2id cost (OWASP minimum is 19 MiB / t=2; production enforces it).
    password_hash_memory_kib: int = Field(default=65536, ge=1024, le=1048576)
    password_hash_iterations: int = Field(default=3, ge=1, le=10)
    password_hash_concurrency: int = Field(default=4, ge=1, le=64)

    # --- Registration policy (D-13 / D-17 are unresolved: no age or legal text is assumed) -----
    registration_enabled: bool | None = None  # default: True in local/ci, False elsewhere
    registration_minimum_age: int | None = Field(default=None, ge=13, le=99)
    legal_terms_version: str | None = Field(default=None, min_length=1, max_length=50)
    legal_privacy_version: str | None = Field(default=None, min_length=1, max_length=50)

    # --- Staff two-factor authentication ------------------------------------------------------
    staff_mfa_required: bool | None = None  # default: True outside local/ci

    # --- Email (provider-neutral SMTP; Mailpit in development) --------------------------------
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    email_from: str | None = Field(default=None, max_length=254)
    outbox_poll_interval_seconds: float = Field(default=2.0, gt=0, le=60)

    # --- Media storage (S3 API; MinIO locally) ------------------------------------------------
    # Unset endpoint = storage not configured: upload endpoints answer 503, nothing is faked.
    s3_endpoint_url: AnyHttpUrl | None = None
    # Origin browsers use for presigned URLs (defaults to s3_endpoint_url).
    s3_public_endpoint_url: AnyHttpUrl | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_bucket: str = Field(default="ielts-media", min_length=3, max_length=63)
    s3_region: str = "us-east-1"
    # Content uploads (Listening audio, images) are staff-only (`media.upload` + staff 2FA) and
    # verified server-side (size, SHA-256, strict file signature). Malware scanning and transcoding
    # (Phase 5b worker) do not exist yet, so outside local/ci they stay off unless explicitly
    # enabled (decision 2026-11-20: staff-only uploads with strict checks are acceptable).
    media_uploads_enabled: bool | None = None
    media_max_audio_bytes: int = Field(default=200 * 1024 * 1024, ge=1024, le=2 * 1024**3)
    media_max_image_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    # Shared secret the voice engine sends as X-Internal-Token when posting Speaking Room
    # transcript events. Unset = the internal endpoint is disabled (no live voice provider yet).
    speaking_events_token: SecretStr | None = None
    # AI evaluation provider (Google AI Studio key). Unset = evaluations end "unavailable".
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash"
    # LiveKit (AI Speaking Room voice). All three are needed; server-side only.
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: SecretStr | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env is Environment.PRODUCTION

    @property
    def is_dev_like(self) -> bool:
        """Local development and CI: the only environments allowed to use placeholders."""
        return self.app_env in (Environment.LOCAL, Environment.CI)

    @property
    def docs_enabled(self) -> bool:
        """Interactive OpenAPI docs are disabled in production (staff-only access comes later)."""
        return not self.is_production

    @property
    def cookie_secure_effective(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return not self.is_dev_like

    @property
    def registration_open(self) -> bool:
        if self.registration_enabled is not None:
            return self.registration_enabled
        return self.is_dev_like

    @property
    def staff_mfa_required_effective(self) -> bool:
        if self.staff_mfa_required is not None:
            return self.staff_mfa_required
        return not self.is_dev_like

    @property
    def media_storage_configured(self) -> bool:
        return bool(self.s3_endpoint_url and self.s3_access_key_id and self.s3_secret_access_key)

    @property
    def media_uploads_open(self) -> bool:
        enabled = self.media_uploads_enabled
        if enabled is None:
            enabled = self.is_dev_like
        return enabled and self.media_storage_configured

    @property
    def terms_version_effective(self) -> str:
        return self.legal_terms_version or DEV_PLACEHOLDER

    @property
    def privacy_version_effective(self) -> str:
        return self.legal_privacy_version or DEV_PLACEHOLDER

    @property
    def uses_policy_placeholders(self) -> bool:
        return (
            self.registration_minimum_age is None
            or self.legal_terms_version is None
            or self.legal_privacy_version is None
        )

    @property
    def app_origin(self) -> str:
        url = self.public_app_url
        port = f":{url.port}" if url.port and url.port not in (80, 443) else ""
        return f"{url.scheme}://{url.host}{port}"

    @model_validator(mode="after")
    def _enforce_environment_rules(self) -> Self:
        if self.is_production and self.log_level == "DEBUG":
            raise ValueError("LOG_LEVEL=DEBUG is not allowed when APP_ENV=production")
        if self.session_absolute_ttl_seconds < self.session_idle_ttl_seconds:
            raise ValueError("SESSION_ABSOLUTE_TTL_SECONDS must be >= SESSION_IDLE_TTL_SECONDS")
        key = self.auth_secret_key.get_secret_value() if self.auth_secret_key else None
        if key is not None and len(key) < 32:
            raise ValueError("AUTH_SECRET_KEY must be at least 32 characters")
        if self.is_dev_like:
            return self
        # --- staging and production ---
        if key is None:
            raise ValueError(f"AUTH_SECRET_KEY is required when APP_ENV={self.app_env}")
        for value in (self.legal_terms_version, self.legal_privacy_version):
            if value is not None and DEV_PLACEHOLDER in value.lower():
                raise ValueError("Development legal placeholders are not allowed outside local/ci")
        if self.registration_open and self.uses_policy_placeholders:
            raise ValueError(
                "Registration requires an approved age policy and legal versions outside local/ci:"
                " set REGISTRATION_MINIMUM_AGE, LEGAL_TERMS_VERSION and LEGAL_PRIVACY_VERSION"
                " (decisions D-13 / D-17), or keep REGISTRATION_ENABLED=false"
            )
        if self.is_production:
            if not self.cookie_secure_effective:
                raise ValueError("SESSION_COOKIE_SECURE must be true in production")
            if not self.staff_mfa_required_effective:
                raise ValueError("STAFF_MFA_REQUIRED must be true in production")
            if self.public_app_url.scheme != "https":
                raise ValueError("PUBLIC_APP_URL must use https in production")
            if self.smtp_security == "none":
                raise ValueError("SMTP_SECURITY=none is not allowed in production")
            if self.password_hash_memory_kib < 19456 or self.password_hash_iterations < 2:
                raise ValueError("Argon2id cost below the OWASP minimum is not allowed here")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # pydantic-settings populates required fields from the environment at runtime.
    return Settings()
