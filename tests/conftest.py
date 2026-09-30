"""
Shared test configuration.

Unit tests need no services.  Integration tests (marked ``integration``)
run the real Supabase client against the real migration on Postgres via
PostgREST (see tests/integration/docker-compose.yml) and a real Redis; they
are skipped automatically when those services are not reachable.

Settings are forced to test values here BEFORE any app module is imported,
so a developer's .env can never leak into (or be modified by) the tests.
"""

from __future__ import annotations

import os
import uuid

import jwt as pyjwt
import pytest
from cryptography.fernet import Fernet

INTEGRATION_URL = os.environ.get("TRUEAI_TEST_SUPABASE_URL", "http://127.0.0.1:54321")
INTEGRATION_JWT_SECRET = "trueai-integration-tests-jwt-secret-0123456789"
SERVICE_ROLE_KEY = pyjwt.encode({"role": "service_role", "iss": "supabase"}, INTEGRATION_JWT_SECRET, algorithm="HS256")

os.environ.update(
    {
        "ENV": "test",
        "BASE_URL": "http://testserver",
        "FRONTEND_URL": "http://localhost:3000",
        "CORS_ORIGINS": "http://localhost:3000",
        "API_KEY_SECRET": "test-api-key-secret-0123456789-abcdefghijklmnop",
        "LLM_PROVIDER": "groq",
        "LLM_MODEL": "openai/gpt-oss-120b",
        "LLM_FALLBACK_MODEL": "",
        "GROQ_API_KEY": "gsk_test_000000000000000000000000",
        "LLM_MAX_ATTEMPTS": "2",
        "SUPABASE_URL": INTEGRATION_URL,
        "SUPABASE_SERVICE_ROLE_KEY": SERVICE_ROLE_KEY,
        "SUPABASE_JWT_SECRET": INTEGRATION_JWT_SECRET,
        "REDIS_URL": os.environ.get("TRUEAI_TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
        "CELERY_BROKER_URL": os.environ.get("TRUEAI_TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
        "CELERY_RESULT_BACKEND": os.environ.get("TRUEAI_TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
        "GITHUB_CLIENT_ID": "test-client-id",
        "GITHUB_CLIENT_SECRET": "test-client-secret",
        "GITHUB_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "LOG_DIR": "",
        "LOG_LEVEL": "WARNING",
        "SENTRY_WEBHOOK_SECRET": "",
        "SENTRY_AUTH_TOKEN": "",
        "SENTRY_ORG_SLUG": "",
    }
)

from app.core.logging import configure_logging  # noqa: E402

configure_logging("test", force=True)


# ------------------------------------------------------------------ #
# Service availability                                                 #
# ------------------------------------------------------------------ #

def _postgrest_up() -> bool:
    import httpx

    try:
        return httpx.get(f"{INTEGRATION_URL}/rest/v1/", timeout=2).status_code < 500
    except httpx.HTTPError:
        return False


def _redis_up() -> bool:
    import redis

    try:
        return bool(redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=1).ping())
    except Exception:
        return False


SERVICES_UP = _postgrest_up() and _redis_up()


def pytest_collection_modifyitems(config, items):  # noqa: ANN001
    if SERVICES_UP:
        return
    skip = pytest.mark.skip(reason="integration services (PostgREST + Redis) are not running")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


def pytest_configure(config):  # noqa: ANN001
    config.addinivalue_line("markers", "integration: needs the PostgREST + Redis test stack")


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture()
def redis_clean():
    """Empty the dedicated test Redis database before a test."""
    from app.services import redis as redis_svc

    redis_svc.reset_redis()
    redis_svc.get_redis().flushdb()
    yield redis_svc
    redis_svc.get_redis().flushdb()


@pytest.fixture()
def db():
    from app.services import supabase

    return supabase


@pytest.fixture()
def make_user(db):
    """Create a real auth.users row through the test-only ``test_create_user`` RPC."""
    import httpx

    created: list[str] = []

    def _make(email: str | None = None) -> str:
        user_id = str(uuid.uuid4())
        response = httpx.post(
            f"{INTEGRATION_URL}/rest/v1/rpc/test_create_user",
            json={"p_id": user_id, "p_email": email or f"{user_id[:8]}@example.com"},
            headers={"Authorization": f"Bearer {SERVICE_ROLE_KEY}", "apikey": SERVICE_ROLE_KEY},
            timeout=5,
        )
        response.raise_for_status()
        created.append(user_id)
        return user_id

    yield _make


def user_jwt(user_id: str, *, role: str = "authenticated", expires_in: int = 3600) -> str:
    """A Supabase-style HS256 access token for *user_id* (legacy signing mode)."""
    import time

    from app.core.config import settings

    now = int(time.time())
    return pyjwt.encode(
        {
            "sub": user_id,
            "role": role,
            "aud": "authenticated",
            "iss": f"{settings.SUPABASE_URL}/auth/v1",
            "iat": now,
            "exp": now + expires_in,
        },
        INTEGRATION_JWT_SECRET,
        algorithm="HS256",
    )
