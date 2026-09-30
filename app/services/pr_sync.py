"""
Pull request status tracking.

Keeps ``pull_requests.status`` and the incident lifecycle in step with GitHub:

    PR merged                → pull request "merged", incident "resolved"
    PR closed without merge  → pull request "closed", incident back to "flagged"
                               (with a note, so a human picks it up)

Used by the scheduled worker task (all open PRs every 10 minutes) and by the
dashboard's on-demand refresh for a single incident.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.errors import GitHubError
from app.core.logging import get_logger
from app.services import supabase as db
from app.services.github.client import GitHubConnection, load_connection
from app.services.github.pr import get_pull_request_state

logger = get_logger(__name__)


def sync_pull_request(pr_row: Dict[str, Any], user_id: str, connection: Optional[GitHubConnection] = None) -> Optional[str]:
    """
    Refresh one PR record from GitHub and propagate the result to its
    incident.  Returns the new PR status, or None when it could not be
    checked (not connected, GitHub unavailable).
    """
    if not pr_row.get("repo_full_name") or not pr_row.get("pr_number"):
        return None
    connection = connection or load_connection(user_id)
    if connection is None:
        return None
    try:
        state = get_pull_request_state(connection.token, pr_row["repo_full_name"], int(pr_row["pr_number"]))
    except GitHubError as exc:
        logger.warning("PR sync failed for #%s on %s: %s", pr_row.get("pr_number"), pr_row.get("repo_full_name"), exc)
        if exc.status == 404:
            db.update_pull_request(pr_row["id"], {"status": "closed", "last_synced_at": db.utcnow()})
            _incident_after_close(pr_row["incident_id"], user_id, "The pull request no longer exists on GitHub.")
            return "closed"
        return None

    new_status = state["status"]
    db.update_pull_request(
        pr_row["id"],
        {
            "status": new_status,
            "merged_at": state["merged_at"],
            "closed_at": state["closed_at"],
            "last_synced_at": db.utcnow(),
        },
    )
    if new_status != pr_row.get("status"):
        if new_status == "merged":
            incident = db.get_incident(pr_row["incident_id"], user_id, columns="id,status")
            if incident and incident["status"] in ("pr_open", "flagged"):
                db.update_incident_for_user(pr_row["incident_id"], user_id, {"status": "resolved"})
        elif new_status == "closed":
            _incident_after_close(pr_row["incident_id"], user_id, "The fix pull request was closed without merging.")
        logger.info("PR #%s on %s is now %s.", pr_row["pr_number"], pr_row["repo_full_name"], new_status)
    return new_status


def _incident_after_close(incident_id: str, user_id: str, note: str) -> None:
    incident = db.get_incident(incident_id, user_id, columns="id,status")
    if incident and incident["status"] == "pr_open":
        db.update_incident_for_user(incident_id, user_id, {"status": "flagged"})
        fix = db.get_latest_fix(incident_id)
        if fix:
            db.update_fix(fix["id"], {"status": "rejected", "flag_reason": note})


def sync_all_open(limit: int = 200) -> Dict[str, int]:
    """Sync every open PR (oldest-checked first).  Returns counts per outcome."""
    counts = {"checked": 0, "merged": 0, "closed": 0, "unavailable": 0}
    connections: Dict[str, Optional[GitHubConnection]] = {}
    for row in db.list_open_pull_requests(limit=limit):
        incident = row.get("incidents") or {}
        user_id = incident.get("user_id")
        if not user_id:
            continue
        if user_id not in connections:
            connections[user_id] = load_connection(user_id)
        status = sync_pull_request(row, user_id, connections[user_id])
        counts["checked"] += 1
        if status in ("merged", "closed"):
            counts[status] += 1
        elif status is None:
            counts["unavailable"] += 1
    return counts
