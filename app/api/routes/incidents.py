"""
Incident routes.

Endpoints
─────────
GET    /incidents                    paginated list (status / classification / search filters)
GET    /incidents/stats              counts per status for the dashboard tabs
GET    /incidents/{id}               full detail: incident + analysis + PR + agent timeline
PATCH  /incidents/{id}               user triage: resolved | ignored | flagged (reopen)
POST   /incidents/{id}/reanalyze     run the agent pipeline again
POST   /incidents/{id}/sync-pr       refresh the fix PR's status from GitHub now
DELETE /incidents/{id}               delete the incident and its analysis
GET    /incidents/{id}/fix           analysis only   (kept for API compatibility)
GET    /incidents/{id}/pr            PR record only  (kept for API compatibility)

Every query is scoped to the caller's user_id; an incident owned by
someone else is indistinguishable from one that does not exist (404).
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import require_current_user
from app.core.config import settings
from app.core.errors import DatabaseError
from app.core.logging import get_logger
from app.core.rate_limit import user_rate_limit
from app.schemas.incident import (
    Analysis,
    IncidentDetail,
    IncidentListResponse,
    IncidentStats,
    IncidentStatus,
    IncidentSummary,
    IncidentUpdate,
    IssueClassification,
    PipelineStep,
    PullRequestInfo,
)
from app.services import redis as redis_svc
from app.services import supabase as db

logger = get_logger(__name__)

router = APIRouter()

_SEARCH_ALLOWED = re.compile(r"[^A-Za-z0-9 _.:/\-]")


def _db_unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The database is temporarily unavailable. Please try again.")


def _load_incident(incident_id: UUID, user_id: str, columns: str = db.INCIDENT_DETAIL_COLUMNS) -> Dict[str, Any]:
    try:
        row = db.get_incident(str(incident_id), user_id, columns=columns)
    except DatabaseError:
        raise _db_unavailable()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found.")
    return row


# ================================================================== #
# Collection                                                           #
# ================================================================== #

@router.get("", response_model=IncidentListResponse, summary="List incidents")
def list_incidents(
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=25, ge=1, le=100),
    status_filter: Optional[IncidentStatus] = Query(default=None, alias="status"),
    classification: Optional[IssueClassification] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=100, description="Search error type, message or culprit."),
    user_id: str = Depends(require_current_user),
) -> IncidentListResponse:
    search = _SEARCH_ALLOWED.sub("", q or "").strip() or None
    try:
        rows, total = db.list_incidents(
            user_id,
            page=page,
            page_size=page_size,
            status=status_filter.value if status_filter else None,
            classification=classification.value if classification else None,
            search=search,
        )
    except DatabaseError:
        raise _db_unavailable()
    return IncidentListResponse(
        items=[IncidentSummary.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/stats", response_model=IncidentStats, summary="Incident counts per status")
def incident_stats(user_id: str = Depends(require_current_user)) -> IncidentStats:
    try:
        counts = db.incident_status_counts(user_id)
    except DatabaseError:
        raise _db_unavailable()
    return IncidentStats(total=sum(counts.values()), by_status=counts)


# ================================================================== #
# Single incident                                                      #
# ================================================================== #

@router.get("/{incident_id}", response_model=IncidentDetail, summary="Incident detail")
def get_incident(incident_id: UUID, user_id: str = Depends(require_current_user)) -> IncidentDetail:
    row = _load_incident(incident_id, user_id)
    try:
        fix = db.get_latest_fix(str(incident_id))
        pr = db.get_pull_request_for_incident(str(incident_id))
        steps = db.list_steps(str(incident_id))
    except DatabaseError:
        raise _db_unavailable()
    detail = IncidentDetail.model_validate(row)
    detail.analysis = Analysis.model_validate(fix) if fix else None
    detail.pull_request = PullRequestInfo.model_validate(pr) if pr and _is_github_url(pr.get("pr_url")) else None
    detail.steps = [PipelineStep.model_validate(step) for step in steps]
    return detail


@router.patch("/{incident_id}", response_model=IncidentSummary, summary="Resolve, ignore or reopen an incident")
def update_incident(incident_id: UUID, body: IncidentUpdate, user_id: str = Depends(require_current_user)) -> IncidentSummary:
    row = _load_incident(incident_id, user_id, columns="id,status")
    if row["status"] in ("queued", "processing"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This incident is still being analysed.")
    try:
        updated = db.update_incident_for_user(str(incident_id), user_id, {"status": body.status})
    except DatabaseError:
        raise _db_unavailable()
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found.")
    logger.info("update_incident | user_id=%s | incident_id=%s | status=%s", user_id, incident_id, body.status)
    return IncidentSummary.model_validate(_load_incident(incident_id, user_id, columns=db.INCIDENT_LIST_COLUMNS))


@router.post("/{incident_id}/reanalyze", summary="Run the agent pipeline again")
def reanalyze_incident(
    incident_id: UUID,
    user_id: str = Depends(require_current_user),
    _limit: None = Depends(user_rate_limit("reanalyze", settings.REANALYZE_LIMIT_PER_HOUR, 3600)),
) -> Dict[str, Any]:
    row = _load_incident(incident_id, user_id, columns="id,status,analysis_run")
    if row["status"] in ("queued", "processing"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This incident is already being analysed.")

    try:
        db.delete_steps(str(incident_id))
        db.delete_fixes_for_incident(str(incident_id))
        db.update_incident_for_user(
            str(incident_id),
            user_id,
            {
                "status": "queued",
                "analysis_run": int(row.get("analysis_run") or 1) + 1,
                "attempts": 0,
                "pipeline_error": None,
                "current_step": "Queued for re-analysis",
                "completed_at": None,
            },
        )
    except DatabaseError:
        raise _db_unavailable()

    from app.workers.tasks import process_incident

    try:
        process_incident.delay(str(incident_id))
    except Exception as exc:
        logger.error("reanalyze: enqueue failed | incident_id=%s | error=%s", incident_id, exc)
        db.update_incident_for_user(
            str(incident_id), user_id, {"status": "failed", "pipeline_error": "Could not queue the analysis.", "current_step": None}
        )
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The job queue is unavailable. Please try again shortly.")
    return {"status": "queued"}


@router.post("/{incident_id}/sync-pr", summary="Refresh the fix pull request's status")
def sync_incident_pr(incident_id: UUID, user_id: str = Depends(require_current_user)) -> Dict[str, Any]:
    from app.services.pr_sync import sync_pull_request

    _load_incident(incident_id, user_id, columns="id")
    try:
        pr = db.get_pull_request_for_incident(str(incident_id))
    except DatabaseError:
        raise _db_unavailable()
    if not pr:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This incident has no pull request.")
    # At most one GitHub check per PR per minute, however often the page is refreshed.
    if pr.get("status") != "open" or redis_svc.claim_once(f"pr-sync:{pr['id']}", 60) is False:
        return {"status": pr.get("status"), "synced": False}
    new_status = sync_pull_request(pr, user_id)
    return {"status": new_status or pr.get("status"), "synced": new_status is not None}


@router.delete("/{incident_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an incident")
def delete_incident(incident_id: UUID, user_id: str = Depends(require_current_user)) -> None:
    row = _load_incident(incident_id, user_id, columns="id,status")
    if row["status"] == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for the analysis to finish before deleting.")
    try:
        db.delete_incident(str(incident_id), user_id)
    except DatabaseError:
        raise _db_unavailable()


@router.get("/{incident_id}/fix", response_model=Analysis, summary="Analysis for an incident")
def get_incident_fix(incident_id: UUID, user_id: str = Depends(require_current_user)) -> Analysis:
    _load_incident(incident_id, user_id, columns="id")
    try:
        fix = db.get_latest_fix(str(incident_id))
    except DatabaseError:
        raise _db_unavailable()
    if not fix:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No analysis for this incident yet.")
    return Analysis.model_validate(fix)


@router.get("/{incident_id}/pr", response_model=PullRequestInfo, summary="Pull request for an incident")
def get_incident_pr(incident_id: UUID, user_id: str = Depends(require_current_user)) -> PullRequestInfo:
    _load_incident(incident_id, user_id, columns="id")
    try:
        pr = db.get_pull_request_for_incident(str(incident_id))
    except DatabaseError:
        raise _db_unavailable()
    if not pr or not _is_github_url(pr.get("pr_url")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pull request for this incident.")
    return PullRequestInfo.model_validate(pr)


def _is_github_url(url: Optional[str]) -> bool:
    return bool(url) and url.startswith("https://github.com/")  # type: ignore[union-attr]
