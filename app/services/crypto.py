"""
Encryption for secrets stored in the database (GitHub OAuth tokens, Sentry
tokens and webhook signing secrets).

Uses ``MultiFernet`` (AES-128-CBC + HMAC-SHA256) so keys can be rotated:
``GITHUB_TOKEN_ENCRYPTION_KEY`` may hold several comma-separated keys — the
first encrypts, every key decrypts.  ``rotate`` re-encrypts a value under
the current primary key.

Legacy plaintext GitHub tokens (written before encryption existed) are still
readable so existing connections keep working; they are recognised by their
GitHub prefix and re-encrypted by the caller on first use.
"""

from __future__ import annotations

import re
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings
from app.core.errors import ConfigurationError
from app.core.logging import get_logger

logger = get_logger(__name__)

_LEGACY_GITHUB_TOKEN = re.compile(r"^(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|[0-9a-f]{40})$")


@lru_cache(maxsize=1)
def _fernet() -> MultiFernet:
    raw = settings.secret("GITHUB_TOKEN_ENCRYPTION_KEY") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise ConfigurationError("GITHUB_TOKEN_ENCRYPTION_KEY is not set.")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as exc:
        raise ConfigurationError(
            "GITHUB_TOKEN_ENCRYPTION_KEY must contain valid Fernet keys. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        ) from exc


def validate_key() -> None:
    """Fail fast at startup when the encryption key is missing or malformed."""
    _fernet()


def encrypt_secret(value: str) -> str:
    if not value:
        raise ValueError("Cannot encrypt an empty value.")
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored secret; raises ``InvalidToken`` when it cannot be decrypted."""
    return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def decrypt_github_token(stored: str) -> tuple[str, bool]:
    """
    Return ``(token, is_legacy_plaintext)``.

    Raises ``InvalidToken`` when the value is neither a valid ciphertext nor
    a recognisable legacy plaintext token (e.g. the key was rotated away).
    """
    try:
        return decrypt_secret(stored), False
    except (InvalidToken, ValueError, UnicodeError):
        if _LEGACY_GITHUB_TOKEN.match(stored or ""):
            logger.warning("Found a legacy plaintext GitHub token; it will be re-encrypted.")
            return stored, True
        raise InvalidToken("Stored GitHub token cannot be decrypted with the configured keys.")


def rotate(ciphertext: str) -> str:
    """Re-encrypt *ciphertext* under the current primary key."""
    return _fernet().rotate(ciphertext.encode("ascii")).decode("ascii")


# Backwards-compatible names used by older call sites.
encrypt_token = encrypt_secret
