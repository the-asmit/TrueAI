"""
API key generation, hashing, and verification for TrueAI.

Security model
──────────────
Raw keys are generated with ``secrets.token_urlsafe(32)`` which yields
~43 characters of URL-safe Base64, providing ~192 bits of entropy.

Keys are hashed with HMAC-SHA256 keyed on ``API_KEY_SECRET`` before storage.
Using HMAC rather than plain SHA256 means that even if the ``api_keys`` table
is leaked, an attacker cannot brute-force the raw keys offline — they would
also need to know the server secret.

The raw key is returned to the caller exactly once (at generation time) and
is never stored, logged, or retained anywhere in the system.  All subsequent
operations work exclusively with the HMAC-SHA256 digest.

Comparison is always performed with ``hmac.compare_digest`` to prevent
timing-based side-channel attacks.
"""

import hashlib
import hmac
import secrets
from typing import Tuple

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Encoding used consistently for all encode/decode operations.
_ENCODING: str = "utf-8"

# Prefix embedded in every raw key so support teams can identify TrueAI keys
# in credential scanners without needing to call the API.
_KEY_PREFIX: str = "tai_"


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def generate_api_key() -> Tuple[str, str]:
    """
    Generate a new API key and return it as a ``(raw_key, hashed_key)`` tuple.

    The raw key must be shown to the user **immediately and exactly once**.
    Only the hashed key should be persisted to the database.

    Returns:
        A 2-tuple of ``(raw_key, hashed_key)`` where:

        - ``raw_key``    — the human-visible key string (``tai_<43 chars>``).
          Never store or log this value.
        - ``hashed_key`` — the HMAC-SHA256 hex digest safe to store in DB.

    Example::

        raw_key, hashed_key = generate_api_key()
        # Show raw_key to user once, save hashed_key to DB.
    """
    raw_key = _KEY_PREFIX + secrets.token_urlsafe(32)
    hashed_key = hash_api_key(raw_key)

    # Log only that a key was generated — NEVER the key itself.
    logger.debug("New API key generated (hash prefix: %s...).", hashed_key[:8])

    return raw_key, hashed_key


def hash_api_key(raw_key: str) -> str:
    """
    Return the HMAC-SHA256 hex digest of *raw_key* keyed on ``API_KEY_SECRET``.

    Deterministic: the same raw key always produces the same digest, so the
    result can be used as a lookup key in the database.

    Args:
        raw_key: The raw API key string exactly as issued to the user.

    Returns:
        A 64-character lowercase hex string.

    Raises:
        ValueError: If *raw_key* is empty or whitespace-only.
    """
    if not raw_key or not raw_key.strip():
        raise ValueError("raw_key must not be empty.")

    secret = settings.API_KEY_SECRET.encode(_ENCODING)
    message = raw_key.encode(_ENCODING)

    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """
    Verify that *raw_key* corresponds to *stored_hash* in constant time.

    Uses ``hmac.compare_digest`` to prevent timing-based side-channel attacks.
    The function re-derives the HMAC of *raw_key* and compares it against
    *stored_hash* — both strings must be equal in length and content for
    ``True`` to be returned.

    Args:
        raw_key:     The raw API key presented by the caller.
        stored_hash: The HMAC-SHA256 hex digest retrieved from the database.

    Returns:
        ``True`` if the key is valid, ``False`` otherwise.

    Note:
        This function **never raises** on bad input — it returns ``False``
        and logs a warning.  Raising would allow callers to distinguish
        between "wrong key" and "malformed key", which is information leakage.
    """
    if not raw_key or not stored_hash:
        logger.warning("verify_api_key called with empty raw_key or stored_hash.")
        return False

    try:
        computed_hash = hash_api_key(raw_key)
    except ValueError:
        logger.warning("verify_api_key: hash_api_key raised ValueError (empty key).")
        return False

    # hmac.compare_digest requires both arguments to be the same type.
    # hash_api_key always returns str (hex digits), so stored_hash must also
    # be str.  Guard against bytes leaking in from the DB layer.
    if isinstance(stored_hash, bytes):
        stored_hash = stored_hash.decode(_ENCODING)

    return hmac.compare_digest(computed_hash, stored_hash)


def mask_key_for_logging(raw_key: str) -> str:
    """
    Return a safely truncated representation of *raw_key* for log messages.

    Shows only the prefix (``tai_``) and the first 4 characters of the random
    portion, then masks the rest.  Provides just enough context to correlate
    log lines with a specific key without exposing the secret.

    Example: ``"tai_AbCd...****************"``
    """
    if len(raw_key) <= len(_KEY_PREFIX) + 4:
        return f"{_KEY_PREFIX}****"
    visible = raw_key[: len(_KEY_PREFIX) + 4]
    masked_len = len(raw_key) - len(visible)
    return f"{visible}{'*' * masked_len}"
