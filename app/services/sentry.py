"""
Sentry API client for fetching full event details.
"""
from __future__ import annotations

import httpx
from typing import Any, Dict, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def fetch_sentry_event(
    project_slug: str,
    event_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Fetch the full event payload from Sentry API using event_id.
    
    Returns the full event dict, or None on failure.
    """
    if not settings.SENTRY_AUTH_TOKEN:
        logger.warning("fetch_sentry_event: SENTRY_AUTH_TOKEN not configured.")
        return None

    url = (
        f"https://sentry.io/api/0/projects/"
        f"{settings.SENTRY_ORG_SLUG}/{project_slug}/events/{event_id}/"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {settings.SENTRY_AUTH_TOKEN}"},
            )
            if response.status_code == 200:
                logger.debug(
                    "fetch_sentry_event: fetched event_id=%s from project=%s",
                    event_id, project_slug,
                )
                return response.json()
            else:
                logger.warning(
                    "fetch_sentry_event: HTTP %d for event_id=%s | body=%s",
                    response.status_code, event_id, response.text[:200],
                )
                return None

    except Exception as exc:
        logger.error(
            "fetch_sentry_event: error fetching event_id=%s | %s: %s",
            event_id, type(exc).__name__, exc,
        )
        return None