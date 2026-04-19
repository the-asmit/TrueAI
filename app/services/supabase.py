"""
Supabase client initialisation and database helper functions for TrueAI.

Design notes
────────────
- The service-role key is used (not the anon key) so that all server-side
  operations bypass Row Level Security.  The API layer is responsible for
  enforcing tenant isolation before calling these helpers.
- Every database call is wrapped in try/except.  DB errors are logged at
  ERROR level with full context (table, operation, id) but are never
  re-raised as raw exceptions — callers receive a typed return value
  (None, empty list, or bool) so the pipeline can decide how to handle them.
- Successes are logged at DEBUG level to keep INFO logs clean in production.
- The Supabase Python client v2 raises ``APIError`` on non-2xx responses;
  connection errors surface as ``httpx.RequestError`` subclasses.  Both are
  caught explicitly.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from app.auth.api_keys import hash_api_key
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------ #
# Singleton                                                            #
# ------------------------------------------------------------------ #

_supabase_client: Optional[Client] = None
_supabase_lock: threading.Lock = threading.Lock()

# Table names — centralised so a rename only touches this file.
_T_INCIDENTS: str = "incidents"
_T_FIXES: str = "fixes"
_T_PULL_REQUESTS: str = "pull_requests"
_T_API_KEYS: str = "api_keys"
_T_GITHUB_TOKENS: str = "github_tokens"


def get_supabase() -> Client:
    """
    Return the shared Supabase :class:`Client` singleton.

    Constructed lazily on the first call and cached for the process lifetime.
    Thread-safe via a module-level lock.

    Raises:
        RuntimeError: If the Supabase URL or service-role key is missing.
        Exception: If the Supabase client cannot be initialised (propagated
            to crash the app at startup rather than silently serving requests
            against a broken DB connection).
    """
    global _supabase_client

    if _supabase_client is not None:
        return _supabase_client

    with _supabase_lock:
        if _supabase_client is not None:   # double-checked locking
            return _supabase_client

        logger.info("Initialising Supabase client (url=%s).", settings.SUPABASE_URL)
        try:
            _supabase_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY,
            )
            logger.info("Supabase client ready.")
        except Exception as exc:
            logger.error(
                "Failed to initialise Supabase client: %s — %s.",
                type(exc).__name__,
                exc,
            )
            raise

    return _supabase_client


# ------------------------------------------------------------------ #
# API key helpers                                                      #
# ------------------------------------------------------------------ #

def get_user_by_api_key(raw_api_key: str) -> Optional[str]:
    """
    Look up a user by a raw API key.

    The incoming key is hashed with HMAC-SHA256 before querying so the raw
    value never touches the database layer.

    Args:
        raw_api_key: The raw ``tai_...`` key string presented by the caller.

    Returns:
        The ``user_id`` string if a matching, active key is found, or
        ``None`` if the key is invalid, revoked, or a DB error occurred.
    """
    try:
        hashed = hash_api_key(raw_api_key)
    except ValueError:
        logger.warning("get_user_by_api_key: invalid (empty) API key presented.")
        return None

    try:
        client = get_supabase()
        response = (
            client.table(_T_API_KEYS)
            .select("user_id")
            .eq("api_key", hashed)
            .single()
            .execute()
        )

        row: Optional[Dict[str, Any]] = response.data
        if not row:
            logger.debug("API key lookup: no matching key found.")
            return None

        user_id: str = row["user_id"]
        logger.debug("API key lookup: resolved to user_id=%s.", user_id)
        return user_id

    except Exception as exc:
        logger.error(
            "DB error in get_user_by_api_key: %s — %s.",
            type(exc).__name__,
            exc,
        )
        return None


# ------------------------------------------------------------------ #
# Incident helpers                                                     #
# ------------------------------------------------------------------ #

def create_incident(incident_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Insert a new row into the ``incidents`` table.

    Args:
        incident_data: Column-value dict matching the incidents schema.
            The ``id`` column should be omitted — Supabase generates a UUID.

    Returns:
        The created row as a dict (including the server-assigned ``id`` and
        ``created_at``), or ``None`` on failure.
    """
    try:
        client = get_supabase()
        response = (
            client.table(_T_INCIDENTS)
            .insert(incident_data)
            .execute()
        )

        rows: List[Dict[str, Any]] = response.data or []
        if not rows:
            logger.error(
                "create_incident: insert returned empty data for payload=%s.",
                _safe_repr(incident_data),
            )
            return None

        created = rows[0]
        logger.debug(
            "create_incident: created incident id=%s for user_id=%s.",
            created.get("id"),
            created.get("user_id"),
        )
        return created

    except Exception as exc:
        logger.error(
            "DB error in create_incident: %s — %s. Payload keys: %s.",
            type(exc).__name__,
            exc,
            list(incident_data.keys()),
        )
        return None


def update_incident(
    incident_id: str,
    update_data: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Update an existing incident row by its UUID primary key.

    Args:
        incident_id: UUID string of the incident to update.
        update_data: Column-value dict of fields to change.

    Returns:
        The updated row as a dict, or ``None`` on failure.
    """
    if not update_data:
        logger.warning(
            "update_incident called with empty update_data for id=%s — no-op.",
            incident_id,
        )
        return None

    try:
        client = get_supabase()
        response = (
            client.table(_T_INCIDENTS)
            .update(update_data)
            .eq("id", incident_id)
            .execute()
        )

        rows: List[Dict[str, Any]] = response.data or []
        if not rows:
            logger.error(
                "update_incident: update returned empty data for id=%s.",
                incident_id,
            )
            return None

        updated = rows[0]
        logger.debug(
            "update_incident: updated incident id=%s, fields=%s.",
            incident_id,
            list(update_data.keys()),
        )
        return updated

    except Exception as exc:
        logger.error(
            "DB error in update_incident (id=%s): %s — %s.",
            incident_id,
            type(exc).__name__,
            exc,
        )
        return None


# ------------------------------------------------------------------ #
# Fix helpers                                                          #
# ------------------------------------------------------------------ #

def create_fix(fix_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Insert a new row into the ``fixes`` table.

    Args:
        fix_data: Column-value dict matching the fixes schema.

    Returns:
        The created row as a dict, or ``None`` on failure.
    """
    try:
        client = get_supabase()
        response = (
            client.table(_T_FIXES)
            .insert(fix_data)
            .execute()
        )

        rows: List[Dict[str, Any]] = response.data or []
        if not rows:
            logger.error(
                "create_fix: insert returned empty data. incident_id=%s.",
                fix_data.get("incident_id"),
            )
            return None

        created = rows[0]
        logger.debug(
            "create_fix: created fix id=%s for incident_id=%s.",
            created.get("id"),
            created.get("incident_id"),
        )
        return created

    except Exception as exc:
        logger.error(
            "DB error in create_fix: %s — %s. incident_id=%s.",
            type(exc).__name__,
            exc,
            fix_data.get("incident_id"),
        )
        return None


# ------------------------------------------------------------------ #
# Pull request helpers                                                 #
# ------------------------------------------------------------------ #

def create_pull_request(pr_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Insert a new row into the ``pull_requests`` table.

    Args:
        pr_data: Column-value dict matching the pull_requests schema.

    Returns:
        The created row as a dict, or ``None`` on failure.
    """
    try:
        client = get_supabase()
        response = (
            client.table(_T_PULL_REQUESTS)
            .insert(pr_data)
            .execute()
        )

        rows: List[Dict[str, Any]] = response.data or []
        if not rows:
            logger.error(
                "create_pull_request: insert returned empty data. fix_id=%s.",
                pr_data.get("fix_id"),
            )
            return None

        created = rows[0]
        logger.debug(
            "create_pull_request: created PR record id=%s, pr_number=%s.",
            created.get("id"),
            created.get("pr_number"),
        )
        return created

    except Exception as exc:
        logger.error(
            "DB error in create_pull_request: %s — %s. fix_id=%s.",
            type(exc).__name__,
            exc,
            pr_data.get("fix_id"),
        )
        return None


# ------------------------------------------------------------------ #
# GitHub token helpers                                                 #
# ------------------------------------------------------------------ #

def get_github_token(user_id: str) -> Optional[str]:
    """
    Retrieve the stored GitHub OAuth access token for *user_id*.

    Args:
        user_id: TrueAI workspace user identifier.

    Returns:
        The raw access token string if found and active, or ``None``.

    Security note:
        The returned token is a credential.  Callers must not log it.
        This function deliberately logs only a masked representation.
    """
    try:
        client = get_supabase()
        response = (
            client.table(_T_GITHUB_TOKENS)
            .select("access_token")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        rows: List[Dict[str, Any]] = response.data or []
        if not rows:
            logger.debug(
                "get_github_token: no token found for user_id=%s.", user_id
            )
            return None

        row = rows[0]
        token: str = row["access_token"]
        logger.debug(
            "get_github_token: token retrieved for user_id=%s (prefix=%s...).",
            user_id,
            token[:4] if len(token) >= 4 else "****",
        )
        return token

    except Exception as exc:
        logger.error(
            "DB error in get_github_token (user_id=%s): %s — %s.",
            user_id,
            type(exc).__name__,
            exc,
        )
        return None


def store_github_token(token_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Upsert a GitHub OAuth token for a user.

    Uses ``on_conflict="user_id"`` so that re-authorising overwrites the
    existing token rather than creating a duplicate row.

    Args:
        token_data: Column-value dict matching the github_tokens schema.
            Must include ``user_id``.  The ``access_token`` value must be
            the raw string (not SecretStr) — the schema layer is responsible
            for calling ``.get_secret_value()`` before calling this function.

    Returns:
        The upserted row as a dict, or ``None`` on failure.
    """
    user_id = token_data.get("user_id", "<unknown>")

    try:
        client = get_supabase()
        response = (
            client.table(_T_GITHUB_TOKENS)
            .upsert(token_data, on_conflict="user_id")
            .execute()
        )

        rows: List[Dict[str, Any]] = response.data or []
        if not rows:
            logger.error(
                "store_github_token: upsert returned empty data for user_id=%s.",
                user_id,
            )
            return None

        upserted = rows[0]
        logger.debug(
            "store_github_token: token upserted for user_id=%s, github_username=%s.",
            user_id,
            upserted.get("github_username"),
        )
        return upserted

    except Exception as exc:
        logger.error(
            "DB error in store_github_token (user_id=%s): %s — %s.",
            user_id,
            type(exc).__name__,
            exc,
        )
        return None


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _safe_repr(data: Dict[str, Any]) -> str:
    """Return a log-safe summary of *data* (keys only, no values)."""
    return f"{{keys: {list(data.keys())}}}"
