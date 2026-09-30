"""
Sentry REST API client.

Used when a webhook does not carry a full stack trace (for example the
integration "issue" webhook) — the pipeline then fetches the complete event.

Credentials are per user (stored encrypted in ``sentry_integrations``) with
the global ``SENTRY_*`` settings as a fallback for single-tenant installs.
The base URL is validated against ``SENTRY_ALLOWED_HOSTS`` on every use and
redirects are never followed, so a user-supplied URL cannot be used to reach
internal services (SSRF).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from app.core.config import settings
from app.core.errors import SentryAPIError
from app.core.logging import get_logger
from app.core.security import validate_external_https_url

logger = get_logger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass(frozen=True)
class SentryCredentials:
    base_url: str
    org_slug: str
    auth_token: str


def resolve_credentials(user_id: str) -> Optional[SentryCredentials]:
    """Return usable API credentials for *user_id*, or None when not configured."""
    from app.services import supabase as db
    from app.services.crypto import decrypt_secret

    row = db.get_sentry_integration(user_id)
    token: Optional[str] = None
    org = None
    base = settings.SENTRY_API_BASE_URL
    if row:
        org = row.get("org_slug")
        base = row.get("base_url") or base
        if row.get("auth_token_enc"):
            try:
                token = decrypt_secret(row["auth_token_enc"])
            except Exception:
                logger.error("Stored Sentry token for user_id=%s cannot be decrypted.", user_id)
    token = token or settings.secret("SENTRY_AUTH_TOKEN")
    org = org or settings.SENTRY_ORG_SLUG
    if not token or not org:
        return None
    try:
        base = validate_external_https_url(base, settings.SENTRY_ALLOWED_HOSTS)
    except ValueError as exc:
        logger.error("Rejected Sentry base URL for user_id=%s: %s", user_id, exc)
        return None
    return SentryCredentials(base_url=base, org_slug=org, auth_token=token)


def resolve_webhook_secret(user_id: str) -> Optional[str]:
    """Per-user webhook signing secret, falling back to the global setting."""
    from app.services import supabase as db
    from app.services.crypto import decrypt_secret

    row = db.get_sentry_integration(user_id)
    if row and row.get("webhook_secret_enc"):
        try:
            return decrypt_secret(row["webhook_secret_enc"])
        except Exception:
            logger.error("Stored Sentry webhook secret for user_id=%s cannot be decrypted.", user_id)
            raise SentryAPIError("Webhook signing secret is unreadable; re-save it in Integrations.")
    return settings.secret("SENTRY_WEBHOOK_SECRET")


async def fetch_event(creds: SentryCredentials, project_slug: str, event_id: str) -> Optional[Dict[str, Any]]:
    path = f"/api/0/projects/{_seg(creds.org_slug)}/{_seg(project_slug)}/events/{_seg(event_id)}/"
    return await _get(creds, path)


async def fetch_latest_issue_event(creds: SentryCredentials, issue_id: str) -> Optional[Dict[str, Any]]:
    event = await _get(creds, f"/api/0/organizations/{_seg(creds.org_slug)}/issues/{_seg(issue_id)}/events/latest/")
    if event is None:
        event = await _get(creds, f"/api/0/issues/{_seg(issue_id)}/events/latest/")
    return event


def verify_credentials(base_url: str, org_slug: str, auth_token: str) -> None:
    """Synchronously check that a token can read the organisation (used when saving settings)."""
    url = f"{base_url}/api/0/organizations/{_seg(org_slug)}/"
    try:
        response = httpx.get(url, headers=_headers(auth_token), timeout=_TIMEOUT, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise SentryAPIError(f"Could not reach Sentry: {type(exc).__name__}") from exc
    if response.status_code in (401, 403):
        raise SentryAPIError("Sentry rejected the token (check it has org:read and event:read scopes).")
    if response.status_code == 404:
        raise SentryAPIError(f"Sentry organisation '{org_slug}' was not found for this token.")
    if response.status_code >= 400:
        raise SentryAPIError(f"Sentry returned HTTP {response.status_code}.")


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

async def _get(creds: SentryCredentials, path: str) -> Optional[Dict[str, Any]]:
    url = f"{creds.base_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await client.get(url, headers=_headers(creds.auth_token))
    except httpx.HTTPError as exc:
        logger.warning("Sentry API request failed (%s): %s", path, type(exc).__name__)
        return None
    if response.status_code == 200:
        data = response.json()
        return data if isinstance(data, dict) else None
    logger.warning("Sentry API returned HTTP %d for %s", response.status_code, path)
    return None


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _seg(value: str) -> str:
    """URL-encode a single path segment."""
    return quote(str(value), safe="")
