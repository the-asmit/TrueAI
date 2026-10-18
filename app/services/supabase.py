"""
Supabase client and every database query TrueAI makes.

Design notes
────────────
- The service-role key is used server-side (it bypasses Row Level Security),
  so **every** query that touches tenant data filters on ``user_id`` here.
  RLS policies in ``supabase/migrations`` are a second line of defence for
  anything that reads the database with a user's own JWT (the dashboard).
- Queries never use ``.single()``: PostgREST raises when zero rows match,
  which would turn a normal "not found" into a 500.  We use ``.limit(1)``
  and inspect the result instead.
- Failures raise :class:`~app.core.errors.DatabaseError` so callers can map
  them to a 503 (API) or a retryable pipeline failure (worker).  Nothing is
  silently swallowed.
- The Supabase SDK is synchronous.  API routes that call these helpers are
  plain ``def`` functions (FastAPI runs them in a thread pool) and the async
  pipeline wraps them in ``asyncio.to_thread``.
"""

from __future__ import annotations

import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

import httpx
from supabase import Client, ClientOptions, create_client

from app.core.config import settings
from app.core.errors import DatabaseError
from app.core.logging import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------ #
# Client singleton                                                     #
# ------------------------------------------------------------------ #

_client: Optional[Client] = None
_client_lock = threading.Lock()

T_INCIDENTS = "incidents"
T_FIXES = "fixes"
T_PULL_REQUESTS = "pull_requests"
T_STEPS = "pipeline_steps"
T_API_KEYS = "api_keys"
T_GITHUB_TOKENS = "github_tokens"
T_REPO_MAPPINGS = "repo_mappings"
T_SENTRY = "sentry_integrations"
T_PROFILES = "user_profiles"

# Columns returned by incident list views (raw_payload is large and never listed).
INCIDENT_LIST_COLUMNS = (
    "id,user_id,sentry_event_id,error_type,error_message,environment,level,platform,"
    "status,issue_classification,severity,culprit,occurrence_count,last_seen_at,"
    "sentry_project,repo_full_name,branch,current_step,confidence,pipeline_error,"
    "created_at,updated_at,completed_at"
)
INCIDENT_DETAIL_COLUMNS = INCIDENT_LIST_COLUMNS + ",fingerprint,sentry_issue_id,sentry_issue_url,stack_trace"

ACTIVE_INCIDENT_STATUSES = ("queued", "processing", "pr_open", "flagged")


def get_supabase() -> Client:
    """Return the shared service-role client (created on first use, thread-safe)."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            logger.info("Initialising Supabase client (url=%s).", settings.SUPABASE_URL)
            _client = create_client(
                settings.SUPABASE_URL,
                settings.secret("SUPABASE_SERVICE_ROLE_KEY") or "",
                options=ClientOptions(httpx_client=_http_client()),
            )
    return _client


def _http_client() -> httpx.Client:
    """
    HTTP/1.1 with a connection pool.  The library's default is a single shared
    HTTP/2 connection, which fails with "Server disconnected" when several
    threads use it at once (concurrent API requests, parallel queries).
    """
    return httpx.Client(
        http2=False,
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    )


def _run(description: str, fn):
    """Execute a query builder callable, converting any failure to DatabaseError."""
    try:
        return fn()
    except DatabaseError:
        raise
    except Exception as exc:
        logger.error("Database error during %s: %s — %s", description, type(exc).__name__, exc)
        raise DatabaseError(f"Database error during {description}.") from exc


def _first(rows: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    return rows[0] if rows else None


# Every query is a network round trip, so independent ones run side by side.
_parallel = ThreadPoolExecutor(max_workers=16, thread_name_prefix="supabase")


def gather(*queries: Callable[[], Any]) -> List[Any]:
    """
    Run independent queries concurrently and return their results in order.
    The first failure (a DatabaseError) is raised once every query has finished.
    Each query runs in a copy of the caller's context, so log lines keep their request id.
    """
    futures = [_parallel.submit(contextvars.copy_context().run, query) for query in queries]
    wait(futures)
    return [future.result() for future in futures]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ping() -> bool:
    try:
        get_supabase().table(T_INCIDENTS).select("id").limit(1).execute()
        return True
    except Exception as exc:
        logger.warning("Supabase ping failed: %s", exc)
        return False


# ================================================================== #
# Incidents                                                            #
# ================================================================== #

def create_incident(data: Dict[str, Any]) -> Dict[str, Any]:
    """Insert an incident row and return it."""
    response = _run("create_incident", lambda: get_supabase().table(T_INCIDENTS).insert(data).execute())
    row = _first(response.data)
    if row is None:
        raise DatabaseError("create_incident returned no row.")
    return row


def update_incident(incident_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update an incident by id (worker-side; ownership was established at creation)."""
    if not data:
        return None
    response = _run(
        "update_incident",
        lambda: get_supabase().table(T_INCIDENTS).update(data).eq("id", incident_id).execute(),
    )
    return _first(response.data)


def update_incident_for_user(incident_id: str, user_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    response = _run(
        "update_incident_for_user",
        lambda: get_supabase()
        .table(T_INCIDENTS)
        .update(data)
        .eq("id", incident_id)
        .eq("user_id", user_id)
        .execute(),
    )
    return _first(response.data)


def get_incident(incident_id: str, user_id: str, columns: str = INCIDENT_DETAIL_COLUMNS) -> Optional[Dict[str, Any]]:
    response = _run(
        "get_incident",
        lambda: get_supabase()
        .table(T_INCIDENTS)
        .select(columns)
        .eq("id", incident_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def get_incident_for_worker(incident_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the full incident row including raw_payload (worker only)."""
    response = _run(
        "get_incident_for_worker",
        lambda: get_supabase().table(T_INCIDENTS).select("*").eq("id", incident_id).limit(1).execute(),
    )
    return _first(response.data)


def list_incidents(
    user_id: str,
    *,
    page: int,
    page_size: int,
    status: Optional[str] = None,
    classification: Optional[str] = None,
    search: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], int]:
    offset = (page - 1) * page_size

    def _query():
        query = (
            get_supabase()
            .table(T_INCIDENTS)
            .select(INCIDENT_LIST_COLUMNS, count="exact")
            .eq("user_id", user_id)
        )
        if status:
            query = query.eq("status", status)
        if classification:
            query = query.eq("issue_classification", classification)
        if search:
            pattern = f"*{search}*"
            query = query.or_(f"error_type.ilike.{pattern},error_message.ilike.{pattern},culprit.ilike.{pattern}")
        return query.order("last_seen_at", desc=True, nullsfirst=False).order("created_at", desc=True).range(
            offset, offset + page_size - 1
        ).execute()

    response = _run("list_incidents", _query)
    return response.data or [], response.count or 0


def incident_status_counts(user_id: str) -> Dict[str, int]:
    """Return ``{status: count}`` for the user (one grouped query via RPC)."""
    response = _run(
        "incident_status_counts",
        lambda: get_supabase().rpc("incident_status_counts", {"p_user_id": user_id}).execute(),
    )
    return {row["status"]: int(row["count"]) for row in (response.data or [])}


def find_active_incident_by_fingerprint(user_id: str, fingerprint: str, window_hours: int) -> Optional[Dict[str, Any]]:
    """Return the most recent still-active incident with this fingerprint inside the grouping window."""
    if window_hours <= 0:
        return None
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    response = _run(
        "find_active_incident_by_fingerprint",
        lambda: get_supabase()
        .table(T_INCIDENTS)
        .select("id,status,occurrence_count")
        .eq("user_id", user_id)
        .eq("fingerprint", fingerprint)
        .in_("status", list(ACTIVE_INCIDENT_STATUSES))
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def record_occurrence(incident_id: str, user_id: str, seen_at: str) -> int:
    """Atomically increment ``occurrence_count`` (RPC) and return the new value."""
    response = _run(
        "record_occurrence",
        lambda: get_supabase()
        .rpc(
            "increment_incident_occurrence",
            {"p_incident_id": incident_id, "p_user_id": user_id, "p_seen_at": seen_at},
        )
        .execute(),
    )
    data = response.data
    if isinstance(data, list):
        data = data[0] if data else 0
    return int(data or 0)


def delete_incident(incident_id: str, user_id: str) -> bool:
    response = _run(
        "delete_incident",
        lambda: get_supabase().table(T_INCIDENTS).delete().eq("id", incident_id).eq("user_id", user_id).execute(),
    )
    return bool(response.data)


def list_stale_incidents(status: str, older_than_minutes: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Incidents stuck in *status* since before the cut-off (worker maintenance)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)).isoformat()
    response = _run(
        "list_stale_incidents",
        lambda: get_supabase()
        .table(T_INCIDENTS)
        .select("id,user_id,status,attempts,updated_at")
        .eq("status", status)
        .lt("updated_at", cutoff)
        .order("updated_at")
        .limit(limit)
        .execute(),
    )
    return response.data or []


# ================================================================== #
# Analyses / fixes                                                     #
# ================================================================== #

def get_latest_fix(incident_id: str) -> Optional[Dict[str, Any]]:
    response = _run(
        "get_latest_fix",
        lambda: get_supabase()
        .table(T_FIXES)
        .select("*")
        .eq("incident_id", incident_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def save_fix(incident_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store the analysis result for an incident.  One row per incident: the
    latest row is updated when it exists (re-analysis), otherwise inserted.
    """
    existing = get_latest_fix(incident_id)
    payload = {**data, "incident_id": incident_id}
    if existing:
        response = _run(
            "save_fix(update)",
            lambda: get_supabase().table(T_FIXES).update(payload).eq("id", existing["id"]).execute(),
        )
    else:
        response = _run("save_fix(insert)", lambda: get_supabase().table(T_FIXES).insert(payload).execute())
    row = _first(response.data)
    if row is None:
        raise DatabaseError("save_fix returned no row.")
    return row


def update_fix(fix_id: str, data: Dict[str, Any]) -> None:
    _run("update_fix", lambda: get_supabase().table(T_FIXES).update(data).eq("id", fix_id).execute())


def delete_fixes_for_incident(incident_id: str) -> None:
    _run("delete_fixes", lambda: get_supabase().table(T_FIXES).delete().eq("incident_id", incident_id).execute())


# ================================================================== #
# Pull requests                                                        #
# ================================================================== #

def create_pull_request_record(data: Dict[str, Any]) -> Dict[str, Any]:
    response = _run("create_pull_request_record", lambda: get_supabase().table(T_PULL_REQUESTS).insert(data).execute())
    row = _first(response.data)
    if row is None:
        raise DatabaseError("create_pull_request_record returned no row.")
    return row


def get_pull_request_for_incident(incident_id: str) -> Optional[Dict[str, Any]]:
    response = _run(
        "get_pull_request_for_incident",
        lambda: get_supabase()
        .table(T_PULL_REQUESTS)
        .select("*")
        .eq("incident_id", incident_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def link_pull_request_to_fix(incident_id: str, fix_id: str) -> None:
    """Attach the incident's PR record(s) to its analysis row."""
    _run(
        "link_pull_request_to_fix",
        lambda: get_supabase()
        .table(T_PULL_REQUESTS)
        .update({"fix_id": fix_id})
        .eq("incident_id", incident_id)
        .is_("fix_id", "null")
        .execute(),
    )


def update_pull_request(pr_id: str, data: Dict[str, Any]) -> None:
    _run("update_pull_request", lambda: get_supabase().table(T_PULL_REQUESTS).update(data).eq("id", pr_id).execute())


def list_open_pull_requests(limit: int = 200) -> List[Dict[str, Any]]:
    """Open PRs joined with their incident owner, oldest-synced first."""
    response = _run(
        "list_open_pull_requests",
        lambda: get_supabase()
        .table(T_PULL_REQUESTS)
        .select("id,incident_id,pr_number,repo_full_name,status,last_synced_at,incidents!inner(user_id,status)")
        .eq("status", "open")
        .order("last_synced_at", desc=False, nullsfirst=True)
        .limit(limit)
        .execute(),
    )
    return response.data or []


# ================================================================== #
# Pipeline steps (agent timeline)                                      #
# ================================================================== #

def add_step(data: Dict[str, Any]) -> None:
    _run("add_step", lambda: get_supabase().table(T_STEPS).insert(data).execute())


def list_steps(incident_id: str, run: Optional[int] = None) -> List[Dict[str, Any]]:
    def _query():
        query = (
            get_supabase()
            .table(T_STEPS)
            .select("id,run,step,kind,status,summary,detail,provider,model,duration_ms,input_tokens,output_tokens,created_at")
            .eq("incident_id", incident_id)
        )
        if run is not None:
            query = query.eq("run", run)
        return query.order("created_at").limit(200).execute()

    return _run("list_steps", _query).data or []


def delete_steps(incident_id: str) -> None:
    _run("delete_steps", lambda: get_supabase().table(T_STEPS).delete().eq("incident_id", incident_id).execute())


# ================================================================== #
# API keys                                                             #
# ================================================================== #

def insert_api_key(user_id: str, hashed_key: str, key_prefix: str, name: str) -> Dict[str, Any]:
    response = _run(
        "insert_api_key",
        lambda: get_supabase()
        .table(T_API_KEYS)
        .insert({"user_id": user_id, "api_key": hashed_key, "key_prefix": key_prefix, "name": name})
        .execute(),
    )
    row = _first(response.data)
    if row is None:
        raise DatabaseError("insert_api_key returned no row.")
    return row


def list_api_keys(user_id: str) -> List[Dict[str, Any]]:
    response = _run(
        "list_api_keys",
        lambda: get_supabase()
        .table(T_API_KEYS)
        .select("id,name,key_prefix,is_active,created_at,last_used_at,revoked_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute(),
    )
    return response.data or []


def count_active_api_keys(user_id: str) -> int:
    response = _run(
        "count_active_api_keys",
        lambda: get_supabase()
        .table(T_API_KEYS)
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .execute(),
    )
    return response.count or 0


def revoke_api_key(user_id: str, key_id: str) -> bool:
    response = _run(
        "revoke_api_key",
        lambda: get_supabase()
        .table(T_API_KEYS)
        .update({"is_active": False, "revoked_at": utcnow()})
        .eq("id", key_id)
        .eq("user_id", user_id)
        .execute(),
    )
    return bool(response.data)


def find_api_key(hashed_key: str) -> Optional[Dict[str, Any]]:
    response = _run(
        "find_api_key",
        lambda: get_supabase()
        .table(T_API_KEYS)
        .select("id,user_id,is_active")
        .eq("api_key", hashed_key)
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def touch_api_key(key_id: str) -> None:
    _run("touch_api_key", lambda: get_supabase().table(T_API_KEYS).update({"last_used_at": utcnow()}).eq("id", key_id).execute())


# ================================================================== #
# GitHub connection                                                    #
# ================================================================== #

def get_github_row(user_id: str) -> Optional[Dict[str, Any]]:
    response = _run(
        "get_github_row",
        lambda: get_supabase()
        .table(T_GITHUB_TOKENS)
        .select("user_id,access_token,github_username,github_user_id,scopes,repo_name,branch_name,created_at,updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def upsert_github_row(data: Dict[str, Any]) -> None:
    _run("upsert_github_row", lambda: get_supabase().table(T_GITHUB_TOKENS).upsert(data, on_conflict="user_id").execute())


def update_github_row(user_id: str, data: Dict[str, Any]) -> None:
    _run("update_github_row", lambda: get_supabase().table(T_GITHUB_TOKENS).update(data).eq("user_id", user_id).execute())


def delete_github_row(user_id: str) -> None:
    _run("delete_github_row", lambda: get_supabase().table(T_GITHUB_TOKENS).delete().eq("user_id", user_id).execute())


# ================================================================== #
# Repository mappings (Sentry project → GitHub repo)                   #
# ================================================================== #

def list_repo_mappings(user_id: str) -> List[Dict[str, Any]]:
    response = _run(
        "list_repo_mappings",
        lambda: get_supabase()
        .table(T_REPO_MAPPINGS)
        .select("id,sentry_project,repo_full_name,branch,created_at,updated_at")
        .eq("user_id", user_id)
        .order("created_at")
        .execute(),
    )
    return response.data or []


def get_default_mapping(user_id: str) -> Optional[Dict[str, Any]]:
    response = _run(
        "get_default_mapping",
        lambda: get_supabase()
        .table(T_REPO_MAPPINGS)
        .select("id,sentry_project,repo_full_name,branch")
        .eq("user_id", user_id)
        .is_("sentry_project", "null")
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def get_mapping_for_project(user_id: str, sentry_project: str) -> Optional[Dict[str, Any]]:
    response = _run(
        "get_mapping_for_project",
        lambda: get_supabase()
        .table(T_REPO_MAPPINGS)
        .select("id,sentry_project,repo_full_name,branch")
        .eq("user_id", user_id)
        .eq("sentry_project", sentry_project)
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def resolve_repo_mapping(user_id: str, sentry_project: Optional[str]) -> Optional[Dict[str, Any]]:
    """Project-specific mapping first, then the user's default repository."""
    if sentry_project:
        mapping = get_mapping_for_project(user_id, sentry_project)
        if mapping:
            return mapping
    return get_default_mapping(user_id)


def save_repo_mapping(user_id: str, sentry_project: Optional[str], repo_full_name: str, branch: Optional[str]) -> Dict[str, Any]:
    """Create or update the mapping for (user, sentry_project)."""
    existing = get_mapping_for_project(user_id, sentry_project) if sentry_project else get_default_mapping(user_id)
    payload = {"repo_full_name": repo_full_name, "branch": branch}
    if existing:
        response = _run(
            "save_repo_mapping(update)",
            lambda: get_supabase().table(T_REPO_MAPPINGS).update(payload).eq("id", existing["id"]).execute(),
        )
    else:
        response = _run(
            "save_repo_mapping(insert)",
            lambda: get_supabase()
            .table(T_REPO_MAPPINGS)
            .insert({**payload, "user_id": user_id, "sentry_project": sentry_project})
            .execute(),
        )
    row = _first(response.data)
    if row is None:
        raise DatabaseError("save_repo_mapping returned no row.")
    return row


def delete_repo_mapping(user_id: str, mapping_id: str) -> bool:
    response = _run(
        "delete_repo_mapping",
        lambda: get_supabase().table(T_REPO_MAPPINGS).delete().eq("id", mapping_id).eq("user_id", user_id).execute(),
    )
    return bool(response.data)


# ================================================================== #
# Sentry integration                                                   #
# ================================================================== #

def get_sentry_integration(user_id: str) -> Optional[Dict[str, Any]]:
    response = _run(
        "get_sentry_integration",
        lambda: get_supabase()
        .table(T_SENTRY)
        .select("user_id,org_slug,base_url,auth_token_enc,webhook_secret_enc,updated_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute(),
    )
    return _first(response.data)


def upsert_sentry_integration(data: Dict[str, Any]) -> None:
    _run("upsert_sentry_integration", lambda: get_supabase().table(T_SENTRY).upsert(data, on_conflict="user_id").execute())


def delete_sentry_integration(user_id: str) -> None:
    _run("delete_sentry_integration", lambda: get_supabase().table(T_SENTRY).delete().eq("user_id", user_id).execute())


# ================================================================== #
# Profiles & account                                                   #
# ================================================================== #

def get_profile(user_id: str) -> Optional[Dict[str, Any]]:
    response = _run(
        "get_profile",
        lambda: get_supabase().table(T_PROFILES).select("user_id,full_name").eq("user_id", user_id).limit(1).execute(),
    )
    return _first(response.data)


def upsert_profile(user_id: str, full_name: str) -> None:
    _run(
        "upsert_profile",
        lambda: get_supabase().table(T_PROFILES).upsert({"user_id": user_id, "full_name": full_name}, on_conflict="user_id").execute(),
    )


def delete_user_data(user_id: str) -> None:
    """
    Delete every row owned by *user_id*.  Child rows (fixes, pull requests,
    pipeline steps) cascade from incidents; tables keyed directly by user
    are cleared explicitly so deletion does not depend on FK configuration.
    """
    client = get_supabase()
    incident_ids = [
        row["id"]
        for row in (_run("delete_user_data(select)", lambda: client.table(T_INCIDENTS).select("id").eq("user_id", user_id).execute()).data or [])
    ]
    for chunk in _chunks(incident_ids, 200):
        _run("delete_user_data(pull_requests)", lambda c=chunk: client.table(T_PULL_REQUESTS).delete().in_("incident_id", c).execute())
        _run("delete_user_data(fixes)", lambda c=chunk: client.table(T_FIXES).delete().in_("incident_id", c).execute())
        _run("delete_user_data(steps)", lambda c=chunk: client.table(T_STEPS).delete().in_("incident_id", c).execute())
    for table in (T_INCIDENTS, T_API_KEYS, T_REPO_MAPPINGS, T_SENTRY, T_GITHUB_TOKENS, T_PROFILES):
        _run(f"delete_user_data({table})", lambda t=table: client.table(t).delete().eq("user_id", user_id).execute())


def delete_auth_user(user_id: str) -> None:
    _run("delete_auth_user", lambda: get_supabase().auth.admin.delete_user(user_id))


def _chunks(items: List[str], size: int) -> Iterable[List[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]
