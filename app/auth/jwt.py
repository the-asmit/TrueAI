"""
Supabase JWT verification for TrueAI.

Signing keys are read from the project's JWKS endpoint
(``{SUPABASE_URL}/auth/v1/.well-known/jwks.json``) and cached, so rotating
the Supabase signing key needs no code change or redeploy.

Verification guarantees
───────────────────────
1. Signature   — ES256 / RS256 against the published JWKS key for the
                 token's ``kid``.  HS256 is accepted only when
                 ``SUPABASE_JWT_SECRET`` is configured (legacy projects).
2. Algorithm   — the algorithm must match the key type; ``none`` and any
                 unexpected algorithm are rejected (no algorithm confusion).
3. Claims      — ``exp`` (with 30 s leeway), ``aud`` = authenticated,
                 ``iss`` = this project, non-empty ``sub``, and ``role`` must
                 be ``authenticated`` (anon and service_role tokens are refused).

Failures raise ``HTTPException(401)``; an unreachable JWKS endpoint raises
``HTTPException(503)`` so clients do not treat an outage as a logout.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict

import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")
_LEEWAY_SECONDS = 30


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(
        f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
        cache_jwk_set=True,
        lifespan=600,
        timeout=5,
    )


def _issuer() -> str:
    return f"{settings.SUPABASE_URL}/auth/v1"


def verify_jwt(token: str) -> Dict[str, Any]:
    """Decode and fully verify a Supabase access token; returns its claims."""
    if not token or token.count(".") != 2:
        _raise_401("Authorization token is missing or malformed.")

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        _raise_401("Authorization token is malformed.")
    algorithm = header.get("alg")

    if algorithm in _ASYMMETRIC_ALGORITHMS:
        try:
            signing_key = _jwks_client().get_signing_key_from_jwt(token).key
        except jwt.PyJWKClientConnectionError as exc:
            logger.error("JWKS endpoint unreachable: %s", exc)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is temporarily unavailable.")
        except jwt.PyJWKClientError:
            _raise_401("Token was signed with an unknown key.")
        key: Any = signing_key
    elif algorithm == "HS256" and settings.secret("SUPABASE_JWT_SECRET"):
        key = settings.secret("SUPABASE_JWT_SECRET")
    else:
        _raise_401("Token uses an unsupported signing algorithm.")

    try:
        claims: Dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            issuer=_issuer(),
            leeway=_LEEWAY_SECONDS,
            options={"require": ["exp", "sub", "iat"]},
        )
    except jwt.ExpiredSignatureError:
        _raise_401("Token has expired. Please sign in again.")
    except jwt.InvalidAudienceError:
        _raise_401("Token audience is not accepted.")
    except jwt.InvalidIssuerError:
        _raise_401("Token was not issued by this project.")
    except jwt.PyJWTError as exc:
        logger.info("JWT rejected: %s", type(exc).__name__)
        _raise_401("Token is invalid.")

    if not str(claims.get("sub") or "").strip():
        _raise_401("Token has no subject.")
    if claims.get("role") != "authenticated":
        logger.warning("Rejected JWT with role=%s used as a user credential.", claims.get("role"))
        _raise_401("Only signed-in user tokens are accepted.")
    return claims


def get_user_id_from_token(token: str) -> str:
    return str(verify_jwt(token)["sub"])


def _raise_401(detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
