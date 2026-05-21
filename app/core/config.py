"""Application settings loaded from environment variables via pydantic-settings."""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration for TrueAI.

    All values are read from the environment (or .env file).  Required fields
    have no default and will cause a clear ValidationError on startup if
    missing, preventing the app from booting in a misconfigured state.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",          # silently ignore unrecognised env vars
        populate_by_name=True,
    )

    # ------------------------------------------------------------------ #
    # Application                                                          #
    # ------------------------------------------------------------------ #
    BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Public base URL of this service (used in webhook callbacks).",
    )
    API_KEY_SECRET: str = Field(
        description="Secret used to sign/verify internal API keys.",
    )

    # ------------------------------------------------------------------ #
    # Groq                                                                 #
    # ------------------------------------------------------------------ #
    GROQ_API_KEY: str = Field(
        description="Groq API key for LLaMA model access.",
    )

    # ------------------------------------------------------------------ #
    # Supabase                                                             #
    # ------------------------------------------------------------------ #
    SUPABASE_URL: str = Field(
        description="Supabase project URL (https://<ref>.supabase.co).",
    )
    SUPABASE_ANON_KEY: str = Field(
        description="Supabase anon/public key for client-side access.",
    )
    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        description="Supabase service-role key for privileged server-side access.",
    )
    SUPABASE_JWT_SECRET: str = Field(
        description="JWT secret used by Supabase to sign auth tokens.",
    )

    # ------------------------------------------------------------------ #
    # Redis                                                                #
    # ------------------------------------------------------------------ #
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL.",
    )

    # ------------------------------------------------------------------ #
    # Celery                                                               #
    # ------------------------------------------------------------------ #
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Celery message broker URL.",
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/0",
        description="Celery result backend URL.",
    )

    # ------------------------------------------------------------------ #
    # GitHub OAuth App                                                     #
    # ------------------------------------------------------------------ #
    GITHUB_CLIENT_ID: str = Field(
        description="GitHub OAuth App client ID.",
    )
    GITHUB_CLIENT_SECRET: str = Field(
        description="GitHub OAuth App client secret.",
    )

    # ------------------------------------------------------------------ #
    # Webhooks & Rate Limiting                                             #
    # ------------------------------------------------------------------ #

    SENTRY_AUTH_TOKEN: Optional[str] = Field(
        default=None,
        description="Sentry API auth token for fetching full event details.",
    )
    SENTRY_ORG_SLUG: str = Field(
        default="trueai-94",
        description="Sentry organization slug.",
    )

    SENTRY_WEBHOOK_SECRET: str | None = Field(
        default=None,
        description=(
            "HMAC-SHA256 secret used to verify sentry-hook-signature headers. "
            "When absent, signature verification is skipped (fail-open)."
        ),
    )
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=20,
        description="Maximum webhook requests allowed per API key per minute.",
    )

    # ------------------------------------------------------------------ #
    # Token Encryption                                                     #
    # ------------------------------------------------------------------ #
    GITHUB_TOKEN_ENCRYPTION_KEY: str = Field(
        description=(
            "Fernet symmetric encryption key for GitHub OAuth access tokens. "
            "Generate with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ),
    )

    # ------------------------------------------------------------------ #
    # Validators                                                           #
    # ------------------------------------------------------------------ #

    @field_validator("SUPABASE_URL", "BASE_URL")
    @classmethod
    def must_be_https_or_http(cls, v: str, info) -> str:  # noqa: N805
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(
                f"{info.field_name} must start with http:// or https://, got: {v!r}"
            )
        return v.rstrip("/")  # normalise — no trailing slash

    @field_validator("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND")
    @classmethod
    def must_be_redis_url(cls, v: str, info) -> str:  # noqa: N805
        if not v.startswith("redis://") and not v.startswith("rediss://"):
            raise ValueError(
                f"{info.field_name} must start with redis:// or rediss://, got: {v!r}"
            )
        return v

    @field_validator(
        "API_KEY_SECRET",
        "GROQ_API_KEY",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
        "GITHUB_CLIENT_SECRET",
    )
    @classmethod
    def must_not_be_blank(cls, v: str, info) -> str:  # noqa: N805
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank.")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached Settings singleton.

    Using @lru_cache means the .env file is parsed only once per process.
    In tests, call get_settings.cache_clear() then monkey-patch env vars to
    force a fresh load.
    """
    return Settings()


# Module-level singleton — import this for convenience:
#   from app.core.config import settings
settings: Settings = get_settings()
