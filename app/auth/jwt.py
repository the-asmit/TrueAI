"""
Supabase JWT verification for TrueAI.

Supabase signs all JWTs with HS256 using the project's ``JWT_SECRET``.
This module verifies those tokens server-side without making any network
calls — all validation is purely cryptographic.

Verification guarantees
───────────────────────
1. Signature   — rejects tokens signed with a different secret.
2. Expiry      — rejects tokens whose ``exp`` claim is in the past.
3. Subject     — rejects tokens with a missing or empty ``sub`` claim
                 (Supabase populates ``sub`` with the user's UUID).
4. Algorithm   — only HS256 is accepted; RS256/none/other are rejected
                 to prevent algorithm-confusion attacks.

All failure modes raise ``HTTPException(401)`` with a descriptive
(but non-leaking) ``detail`` message so the API layer can return a
well-formed 401 response without extra error handling at the route level.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JWTClaimsError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Supabase exclusively uses HS256; accepting other algorithms opens the
# door to algorithm-confusion attacks (e.g. RS256 with a public key as
# the secret, or the "alg: none" bypass).
_ALGORITHM: str = "ES256"

# Supabase audience claim expected value.  Supabase sets aud="authenticated"
# for all logged-in user tokens.  We verify this to ensure TrueAI does not
# accept service-role tokens or anon tokens as user credentials.
_EXPECTED_AUDIENCE: str = "authenticated"


# Supabase ECC P-256 public key (JWK format)
_SUPABASE_PUBLIC_JWK = {
    "x": "_Y8PYL_C351JwEnSjVpPqY2fF1_kvdlXq8WVfUqVABA",
    "y": "30iVSGkefQp7D6Q3fOmGP74LDIU-4zQqcsnIMj0ijBE",
    "alg": "ES256",
    "crv": "P-256",
    "kty": "EC",
    "kid": "9dbe1a07-1305-434f-9c13-41ab62a7ee66",
}


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def verify_jwt(token: str) -> Dict[str, Any]:
    """
    Decode and fully verify a Supabase-issued JWT.

    Performs:
    - ECDSA-SHA256 (ES256) signature verification using Supabase public JWK
    - Expiry (``exp``) validation
    - Audience (``aud``) validation — must be ``"authenticated"``
    - Presence and non-emptiness of the ``sub`` claim

    Args:
        token: Raw JWT string (the ``Bearer <token>`` value from the
               ``Authorization`` header, with the ``Bearer `` prefix
               already stripped by the dependency layer).

    Returns:
        The decoded claims payload as a plain dict.

    Raises:
        :class:`fastapi.HTTPException` (401) for any verification failure
        with a descriptive ``detail`` message.
    """
    if not token or not token.strip():
        _raise_401("Authorization token is missing.")

    try:
        payload: Dict[str, Any] = jwt.decode(
            token,
            _SUPABASE_PUBLIC_JWK,  # ES256 public JWK — not a shared secret
            algorithms=[_ALGORITHM],
            audience=_EXPECTED_AUDIENCE,
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iat": True,
                "require_exp": True,
                "require_sub": False,  # we validate sub manually below
            },
        )
    except ExpiredSignatureError:
        logger.info("JWT verification failed: token has expired.")
        _raise_401("Token has expired. Please re-authenticate.")

    except JWTClaimsError as exc:
        # Covers audience mismatch and other claim errors.
        logger.info("JWT verification failed: invalid claims — %s.", exc)
        _raise_401(f"Token has invalid claims: {exc}")

    except JWTError as exc:
        # Covers bad signature, malformed header, unsupported algorithm, etc.
        logger.info("JWT verification failed: %s.", type(exc).__name__)
        _raise_401("Token is invalid or has been tampered with.")

    except Exception as exc:
        # Catch-all for unexpected errors from the jose library so we never
        # return a 500 for a bad token.
        logger.error(
            "Unexpected error during JWT verification: %s — %s.",
            type(exc).__name__,
            exc,
        )
        _raise_401("Token could not be verified due to an internal error.")

    # ---- Post-decode claim validation --------------------------------- #

    sub = payload.get("sub")
    if not sub or not str(sub).strip():
        logger.info("JWT verification failed: 'sub' claim is absent or empty.")
        _raise_401("Token is missing the required 'sub' (subject) claim.")

    # Supabase sets role="authenticated" for user tokens.  Reject service-role
    # JWTs that may have slipped through audience validation on older jose
    # versions.
    role = payload.get("role", "")
    if role == "service_role":
        logger.warning(
            "Rejected service_role JWT used as a user credential "
            "(sub=%s).", _mask_sub(sub)
        )
        _raise_401("Service-role tokens are not accepted as user credentials.")

    logger.debug("JWT verified successfully (sub=%s).", _mask_sub(sub))
    return payload


def get_user_id_from_token(token: str) -> str:
    """
    Verify *token* and return the ``sub`` claim (Supabase user UUID).

    This is the primary function used by FastAPI dependencies to extract
    the authenticated user ID from a request.

    Args:
        token: Raw JWT string.

    Returns:
        The ``sub`` claim value — always a non-empty string when this
        function returns without raising.

    Raises:
        :class:`fastapi.HTTPException` (401) on any verification failure.
    """
    payload = verify_jwt(token)
    return str(payload["sub"])


def get_token_claims(token: str) -> Dict[str, Any]:
    """
    Verify *token* and return all decoded claims.

    Useful when routes need more than just the user ID — e.g. the Supabase
    ``email``, ``app_metadata``, or custom claims.

    Args:
        token: Raw JWT string.

    Returns:
        Full decoded claims payload.

    Raises:
        :class:`fastapi.HTTPException` (401) on any verification failure.
    """
    return verify_jwt(token)


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _raise_401(detail: str) -> None:
    """Raise ``HTTPException(401)`` with the given detail message."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _mask_sub(sub: str) -> str:
    """
    Return a partially masked subject for safe log output.

    Supabase UUIDs look like ``550e8400-e29b-41d4-a716-446655440000``.
    We show the first 8 characters so log lines are correlatable without
    exposing the full UUID.
    """
    return f"{sub[:8]}..." if len(sub) > 8 else "****"
