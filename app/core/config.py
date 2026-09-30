"""
Application settings loaded from environment variables via pydantic-settings.

Every tunable in TrueAI lives here so behaviour can be changed per
deployment without code edits.  Required values have no default, which makes
a misconfigured process fail at boot with a clear validation error instead of
misbehaving at runtime.

Per-agent model routing
───────────────────────
The pipeline is a multi-agent system.  Every agent resolves its model from
``AGENT_<NAME>_PROVIDER`` / ``AGENT_<NAME>_MODEL`` / ``AGENT_<NAME>_TEMPERATURE``
/ ``AGENT_<NAME>_MAX_TOKENS`` and falls back to the global ``LLM_*`` values
when an override is not set.  Agent names: TRIAGE, INVESTIGATOR,
FIX_ENGINEER, REVIEWER, REMEDIATION.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing_extensions import Annotated

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

LLMProvider = Literal["groq", "openai", "anthropic"]

AGENT_NAMES: tuple[str, ...] = (
    "triage",
    "investigator",
    "fix_engineer",
    "reviewer",
    "remediation",
)


class Settings(BaseSettings):
    """Central, validated configuration for every TrueAI process."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Application                                                          #
    # ------------------------------------------------------------------ #
    ENV: Literal["development", "staging", "production", "test"] = "development"
    BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Public base URL of this API (used in webhook URLs and OAuth callbacks).",
    )
    FRONTEND_URL: str = Field(
        default="http://localhost:3000",
        description="Public URL of the dashboard (OAuth hand-off and PR back-links).",
    )
    CORS_ORIGINS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        description="Comma-separated list of browser origins allowed to call the API.",
    )
    ALLOWED_HOSTS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        description="Comma-separated Host header allow-list ('*' disables the check).",
    )
    TRUST_PROXY_HEADERS: bool = Field(
        default=False,
        description="Trust X-Forwarded-For for client IPs (enable only behind a trusted proxy).",
    )
    API_KEY_SECRET: SecretStr = Field(
        description="Server secret used to HMAC API keys and sign OAuth state.",
    )

    # ------------------------------------------------------------------ #
    # LLM — global defaults                                                #
    # ------------------------------------------------------------------ #
    LLM_PROVIDER: LLMProvider = "groq"
    LLM_MODEL: str = "openai/gpt-oss-120b"
    LLM_TEMPERATURE: float = Field(default=0.1, ge=0.0, le=2.0)
    # Reasoning models spend output tokens thinking before they answer, so the
    # budget must leave room for both.
    LLM_MAX_TOKENS: int = Field(default=8192, ge=256, le=65536)
    LLM_REASONING_EFFORT: Optional[Literal["low", "medium", "high"]] = Field(
        default=None,
        description="Reasoning effort for models that support it (Groq gpt-oss, OpenAI o-series).",
    )
    LLM_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0)
    LLM_MAX_ATTEMPTS: int = Field(default=4, ge=1, le=8)
    LLM_FALLBACK_PROVIDER: Optional[LLMProvider] = None
    LLM_FALLBACK_MODEL: Optional[str] = Field(
        default="qwen/qwen3.8-27b",
        description="Model tried once when the primary is unavailable (empty string disables).",
    )

    GROQ_API_KEY: Optional[SecretStr] = None
    OPENAI_API_KEY: Optional[SecretStr] = None
    OPENAI_BASE_URL: Optional[str] = Field(
        default=None,
        description="Optional OpenAI-compatible endpoint (Azure, OpenRouter, vLLM, Ollama).",
    )
    ANTHROPIC_API_KEY: Optional[SecretStr] = None

    # ------------------------------------------------------------------ #
    # LLM — per-agent overrides                                            #
    # ------------------------------------------------------------------ #
    AGENT_TRIAGE_PROVIDER: Optional[LLMProvider] = None
    AGENT_TRIAGE_MODEL: Optional[str] = None
    AGENT_TRIAGE_TEMPERATURE: Optional[float] = None
    AGENT_TRIAGE_MAX_TOKENS: Optional[int] = None

    AGENT_INVESTIGATOR_PROVIDER: Optional[LLMProvider] = None
    AGENT_INVESTIGATOR_MODEL: Optional[str] = None
    AGENT_INVESTIGATOR_TEMPERATURE: Optional[float] = None
    AGENT_INVESTIGATOR_MAX_TOKENS: Optional[int] = None

    AGENT_FIX_ENGINEER_PROVIDER: Optional[LLMProvider] = None
    AGENT_FIX_ENGINEER_MODEL: Optional[str] = None
    AGENT_FIX_ENGINEER_TEMPERATURE: Optional[float] = None
    AGENT_FIX_ENGINEER_MAX_TOKENS: Optional[int] = None

    AGENT_REVIEWER_PROVIDER: Optional[LLMProvider] = None
    AGENT_REVIEWER_MODEL: Optional[str] = None
    AGENT_REVIEWER_TEMPERATURE: Optional[float] = None
    AGENT_REVIEWER_MAX_TOKENS: Optional[int] = None

    AGENT_REMEDIATION_PROVIDER: Optional[LLMProvider] = None
    AGENT_REMEDIATION_MODEL: Optional[str] = None
    AGENT_REMEDIATION_TEMPERATURE: Optional[float] = None
    AGENT_REMEDIATION_MAX_TOKENS: Optional[int] = None

    # ------------------------------------------------------------------ #
    # Pipeline tuning                                                      #
    # ------------------------------------------------------------------ #
    CONFIDENCE_AUTO_PR_THRESHOLD: float = Field(default=0.75, ge=0.0, le=1.0)
    CONFIDENCE_MIN_FIX_THRESHOLD: float = Field(default=0.40, ge=0.0, le=1.0)
    MAX_INVESTIGATION_ROUNDS: int = Field(default=2, ge=1, le=4)
    MAX_FIX_ATTEMPTS: int = Field(default=3, ge=1, le=5)
    MAX_CONTEXT_FILES: int = Field(default=6, ge=1, le=15)
    CONTEXT_WINDOW_LINES: int = Field(default=40, ge=5, le=200)
    MAX_SOURCE_FILE_BYTES: int = Field(default=300_000, ge=10_000)
    MAX_PATCH_FILES: int = Field(default=5, ge=1, le=20)
    MAX_PATCH_CHANGED_LINES: int = Field(default=200, ge=5, le=2000)
    PIPELINE_TIMEOUT_SECONDS: int = Field(default=540, ge=60)
    INCIDENT_GROUPING_WINDOW_HOURS: int = Field(default=24, ge=0, le=24 * 30)
    PR_AS_DRAFT: bool = False
    PR_LABEL: str = "trueai"

    # ------------------------------------------------------------------ #
    # Supabase                                                             #
    # ------------------------------------------------------------------ #
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: SecretStr
    SUPABASE_ANON_KEY: Optional[SecretStr] = None
    SUPABASE_JWT_SECRET: Optional[SecretStr] = Field(
        default=None,
        description="Only needed for legacy projects that still sign user JWTs with HS256.",
    )
    SUPABASE_JWT_AUDIENCE: str = "authenticated"

    # ------------------------------------------------------------------ #
    # Redis / Celery                                                       #
    # ------------------------------------------------------------------ #
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ------------------------------------------------------------------ #
    # GitHub OAuth App                                                     #
    # ------------------------------------------------------------------ #
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: SecretStr
    GITHUB_OAUTH_SCOPES: str = "repo,read:user"
    GITHUB_TOKEN_ENCRYPTION_KEY: SecretStr = Field(
        description=(
            "Fernet key(s) used to encrypt every stored secret. Comma-separate "
            "several keys to rotate: the first encrypts, all of them decrypt."
        ),
    )

    # ------------------------------------------------------------------ #
    # Sentry (global fallbacks — per-user settings take precedence)        #
    # ------------------------------------------------------------------ #
    SENTRY_WEBHOOK_SECRET: Optional[SecretStr] = None
    SENTRY_AUTH_TOKEN: Optional[SecretStr] = None
    SENTRY_ORG_SLUG: Optional[str] = None
    SENTRY_API_BASE_URL: str = "https://sentry.io"
    SENTRY_ALLOWED_HOSTS: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["sentry.io", "*.sentry.io"],
        description="Hosts a user-supplied Sentry base URL may point at (SSRF guard).",
    )

    # ------------------------------------------------------------------ #
    # Abuse protection                                                     #
    # ------------------------------------------------------------------ #
    RATE_LIMIT_PER_MINUTE: int = Field(default=60, ge=1, description="Webhook requests per API key per minute.")
    API_RATE_LIMIT_PER_MINUTE: int = Field(default=300, ge=10, description="Dashboard API requests per user per minute.")
    REANALYZE_LIMIT_PER_HOUR: int = Field(default=20, ge=1)
    WEBHOOK_MAX_BODY_BYTES: int = Field(default=2 * 1024 * 1024, ge=16_384)
    MAX_ACTIVE_API_KEYS: int = Field(default=10, ge=1, le=100)

    # ------------------------------------------------------------------ #
    # Logging                                                              #
    # ------------------------------------------------------------------ #
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["text", "json"] = "text"
    LOG_DIR: Optional[str] = Field(
        default="logs",
        description="Directory for rotating log files; empty string logs to stdout only.",
    )

    # ------------------------------------------------------------------ #
    # Validators                                                           #
    # ------------------------------------------------------------------ #

    @field_validator("CORS_ORIGINS", "ALLOWED_HOSTS", "SENTRY_ALLOWED_HOSTS", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip().rstrip("/") for item in v.split(",") if item.strip()]
        return v

    @field_validator("SUPABASE_URL", "BASE_URL", "FRONTEND_URL", "SENTRY_API_BASE_URL")
    @classmethod
    def _http_url(cls, v: str, info) -> str:  # noqa: ANN001
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"{info.field_name} must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND")
    @classmethod
    def _redis_url(cls, v: str, info) -> str:  # noqa: ANN001
        if not v.startswith(("redis://", "rediss://")):
            raise ValueError(f"{info.field_name} must start with redis:// or rediss://")
        return v

    @field_validator("API_KEY_SECRET")
    @classmethod
    def _strong_secret(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value().strip()) < 32:
            raise ValueError(
                "API_KEY_SECRET must be at least 32 characters. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return v

    @field_validator("PR_LABEL")
    @classmethod
    def _label(cls, v: str) -> str:
        return v.strip()[:50]

    @model_validator(mode="after")
    def _cross_field_checks(self) -> "Settings":
        if self.CONFIDENCE_MIN_FIX_THRESHOLD > self.CONFIDENCE_AUTO_PR_THRESHOLD:
            raise ValueError(
                "CONFIDENCE_MIN_FIX_THRESHOLD must not exceed CONFIDENCE_AUTO_PR_THRESHOLD"
            )
        if self.is_production:
            insecure = [u for u in (self.BASE_URL, self.FRONTEND_URL) if u.startswith("http://")]
            if insecure:
                raise ValueError(f"Production URLs must use https: {insecure}")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("CORS_ORIGINS must not contain '*' in production")
        return self

    # ------------------------------------------------------------------ #
    # Convenience accessors                                                #
    # ------------------------------------------------------------------ #

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def log_dir_path(self) -> Optional[Path]:
        if not self.LOG_DIR:
            return None
        path = Path(self.LOG_DIR)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def secret(self, name: str) -> Optional[str]:
        """Return the plain value of a SecretStr setting, or None when unset."""
        value = getattr(self, name, None)
        if value is None:
            return None
        if isinstance(value, SecretStr):
            raw = value.get_secret_value()
            return raw or None
        return str(value) or None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton (call ``cache_clear()`` in tests)."""
    return Settings()  # type: ignore[call-arg]


settings: Settings = get_settings()
