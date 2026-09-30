"""
API key generation, hashing and lookup for TrueAI.

Security model
──────────────
- Raw keys are ``tai_`` + 32 random bytes (``secrets.token_urlsafe``), ~256
  bits of entropy.  The raw key is shown to the user exactly once.
- Only an HMAC-SHA256 digest keyed on ``API_KEY_SECRET`` is stored, so a
  leaked ``api_keys`` table cannot be brute-forced without the server secret.
  (Rotating ``API_KEY_SECRET`` invalidates every existing key.)
- Keys are looked up by digest, so comparison happens inside the database's
  unique index — there is no string comparison to time.
- ``last_used_at`` is updated at most once every 5 minutes per key.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

KEY_PREFIX = "tai_"
_DISPLAY_PREFIX_LENGTH = 12
_TOUCH_INTERVAL_SECONDS = 300


def generate_api_key() -> Tuple[str, str, str]:
    """Return ``(raw_key, hashed_key, display_prefix)``."""
    raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
    return raw_key, hash_api_key(raw_key), raw_key[:_DISPLAY_PREFIX_LENGTH]


def hash_api_key(raw_key: str) -> str:
    if not raw_key or not raw_key.strip():
        raise ValueError("raw_key must not be empty.")
    secret = (settings.secret("API_KEY_SECRET") or "").encode("utf-8")
    return hmac.new(secret, raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def looks_like_api_key(value: Optional[str]) -> bool:
    return bool(value) and value.startswith(KEY_PREFIX) and 20 <= len(value) <= 128  # type: ignore[union-attr]


def resolve_api_key(raw_key: str) -> Optional[str]:
    """
    Return the owning ``user_id`` for an active key, or None.

    Raises DatabaseError when the lookup itself fails so callers can answer
    503 instead of wrongly reporting the key as invalid.
    """
    if not looks_like_api_key(raw_key):
        return None
    from app.services import redis as redis_svc
    from app.services import supabase as db

    row = db.find_api_key(hash_api_key(raw_key))
    if not row or row.get("is_active") is False:
        return None
    if redis_svc.claim_once(f"apikey-touch:{row['id']}", _TOUCH_INTERVAL_SECONDS) is not False:
        try:
            db.touch_api_key(row["id"])
        except Exception as exc:  # usage tracking must never block authentication
            logger.debug("Could not update last_used_at: %s", exc)
    return str(row["user_id"])


def webhook_url_for(raw_key: str) -> str:
    return f"{settings.BASE_URL}/webhook/sentry?key={raw_key}"


def mask_key_for_logging(raw_key: str) -> str:
    return f"{raw_key[:8]}…" if raw_key else "(none)"
