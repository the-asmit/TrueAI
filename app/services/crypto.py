"""
Symmetric encryption helpers for GitHub OAuth access tokens.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the ``cryptography`` package.
The encryption key is read from ``settings.GITHUB_TOKEN_ENCRYPTION_KEY`` and
must be a valid URL-safe Base64-encoded 32-byte key as produced by
``cryptography.fernet.Fernet.generate_key()``.

Module-load validation
──────────────────────
The Fernet instance is constructed once at module import time.  If the key
is missing or malformed the module raises ``RuntimeError`` immediately,
which causes the FastAPI startup to fail with a clear error message rather
than serving requests with a broken encryption layer.

Public API
──────────
    encrypt_token(token: str) -> str
        Encrypt a plaintext GitHub access token.  Returns a Fernet token
        string (URL-safe Base64).

    decrypt_token(encrypted: str) -> str
        Decrypt a Fernet token string.  Falls back to returning the raw
        string as-is when decryption fails — this allows existing rows
        written before encryption was enabled to continue working without
        a migration step (fail-open migration path).

Security notes
──────────────
- Plaintext tokens are NEVER written to any log record in this module.
- Fernet tokens are self-authenticating (HMAC) — tampered ciphertexts
  are detected and cause an ``InvalidToken`` exception which the fallback
  path handles gracefully.
"""

from __future__ import annotations

from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------ #
# Module-load key validation                                           #
# ------------------------------------------------------------------ #

try:
    _fernet = Fernet(settings.GITHUB_TOKEN_ENCRYPTION_KEY.encode())
except Exception:
    raise RuntimeError(
        "Invalid GITHUB_TOKEN_ENCRYPTION_KEY — must be a valid Fernet key. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""
    )


# ------------------------------------------------------------------ #
# Public functions                                                     #
# ------------------------------------------------------------------ #

def encrypt_token(token: str) -> str:
    """
    Encrypt *token* with Fernet and return the ciphertext as a string.

    Args:
        token: Plaintext GitHub OAuth access token.

    Returns:
        URL-safe Base64-encoded Fernet ciphertext string.

    Raises:
        ValueError: If *token* is empty.
        Exception: Propagated from ``cryptography`` on unexpected failure.
    """
    if not token:
        raise ValueError("encrypt_token: token must not be empty.")
    return _fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    """
    Decrypt a Fernet ciphertext string back to a plaintext token.

    Plaintext fallback (migration path)
    ────────────────────────────────────
    If decryption fails (e.g. the stored value is a legacy plaintext token
    written before encryption was introduced), the raw string is returned
    as-is with a WARNING log.  This allows existing DB rows to continue
    working without a bulk migration.  Once all rows have been re-encrypted,
    the fallback can be removed.

    Args:
        encrypted: Fernet ciphertext string, or a legacy plaintext token.

    Returns:
        Plaintext GitHub OAuth access token.
    """
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        logger.warning(
            "decrypt_token: token appears unencrypted — using as plaintext "
            "(migration fallback). Re-encrypt this token to suppress this warning."
        )
        return encrypted
