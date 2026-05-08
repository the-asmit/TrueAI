"""
Incident query and management routes for TrueAI.

Endpoints
─────────
GET  /incidents            — paginated list of the caller's incidents
GET  /incidents/{id}       — single incident by UUID
PATCH /incidents/{id}      — update status or classification
GET  /incidents/{id}/fix   — get the generated fix for an incident
GET  /incidents/{id}/pr    — get the PR record for an incident

All endpoints are scoped to the authenticated user — a user can only
see incidents created under their user_id.  The Supabase service layer
uses the service-role key, so row-level security is enforced here at the
application level by always filtering on user_id.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import require_current_user
from app.core.logging import get_logger
from app.schemas.incident import (
    IncidentListResponse,
    IncidentResponse,
    IncidentStatus,
    IncidentUpdate,
    IssueClassification,
)

logger = get_logger(__name__)

router = APIRouter()


# ================================================================== #
# List incidents                                                       #
# ================================================================== #

@router.get(
    "",
    summary="List incidents",
    response_model=IncidentListResponse,
)
async def list_incidents(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page."),
    status_filter: Optional[IncidentStatus] = Query(
        default=None,
        alias="status",
        description="Filter by lifecycle status.",
    ),
    classification: Optional[IssueClassification] = Query(
        default=None,
        description="Filter by issue classification.",
    ),
    user_id: str = Depends(require_current_user),
) -> IncidentListResponse:
    """
    Return a paginated list of incidents owned by the authenticated user.

    Results are ordered by ``created_at`` descending (most recent first).
    """
    try:
        from app.services.supabase import get_supabase

        client = get_supabase()
        offset = (page - 1) * page_size

        # Build query
        query = (
            client.table("incidents")
            .select("*", count="exact")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .range(offset, offset + page_size - 1)
        )

        if status_filter:
            query = query.eq("status", status_filter.value)
        if classification:
            query = query.eq("issue_classification", classification.value)

        response = query.execute()
        rows: List[Dict[str, Any]] = response.data or []
        total: int = response.count or 0

        items = [IncidentResponse.model_validate(row) for row in rows]

        logger.debug(
            "list_incidents | user_id=%s | page=%d | page_size=%d | "
            "total=%d | returned=%d",
            user_id,
            page,
            page_size,
            total,
            len(items),
        )

        return IncidentListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as exc:
        logger.error(
            "list_incidents: DB error | user_id=%s | error=%s — %s",
            user_id,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve incidents.",
        )


# ================================================================== #
# Get single incident                                                  #
# ================================================================== #

@router.get(
    "/{incident_id}",
    summary="Get incident by ID",
    response_model=IncidentResponse,
)
async def get_incident(
    incident_id: UUID,
    user_id: str = Depends(require_current_user),
) -> IncidentResponse:
    """Return a single incident record.  Returns 404 if not found or not owned."""
    row = _fetch_incident_row(str(incident_id), user_id)
    return IncidentResponse.model_validate(row)


# ================================================================== #
# Update incident                                                      #
# ================================================================== #

@router.patch(
    "/{incident_id}",
    summary="Update incident",
    response_model=IncidentResponse,
)
async def update_incident(
    incident_id: UUID,
    body: IncidentUpdate,
    user_id: str = Depends(require_current_user),
) -> IncidentResponse:
    """
    Partially update an incident's mutable fields.

    Only ``status``, ``issue_classification``, and ``pipeline_error``
    are accepted.  The incident must be owned by the caller.
    """
    # Verify ownership
    _fetch_incident_row(str(incident_id), user_id)

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No updatable fields provided.",
        )

    # Serialize enum values to strings for Supabase
    for key, val in list(update_data.items()):
        if hasattr(val, "value"):
            update_data[key] = val.value

    try:
        from app.services.supabase import update_incident as _update

        updated = _update(incident_id=str(incident_id), update_data=update_data)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Update succeeded but returned no data.",
            )

        logger.info(
            "update_incident | user_id=%s | incident_id=%s | fields=%s",
            user_id,
            incident_id,
            list(update_data.keys()),
        )
        return IncidentResponse.model_validate(updated)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "update_incident: DB error | incident_id=%s | error=%s — %s",
            incident_id,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update incident.",
        )


# ================================================================== #
# Get fix for incident                                                 #
# ================================================================== #

@router.get(
    "/{incident_id}/fix",
    summary="Get generated fix",
    response_model=Dict[str, Any],
)
async def get_incident_fix(
    incident_id: UUID,
    user_id: str = Depends(require_current_user),
) -> Dict[str, Any]:
    """Return the generated code fix associated with this incident."""
    # Verify ownership
    _fetch_incident_row(str(incident_id), user_id)

    try:
        from app.services.supabase import get_supabase

        response = (
            get_supabase()
            .table("fixes")
            .select("*")
            .eq("incident_id", str(incident_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No fix found for incident {incident_id}.",
            )
        return rows[0]

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "get_incident_fix: DB error | incident_id=%s | error=%s",
            incident_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve fix.",
        )


# ================================================================== #
# Get PR record for incident                                           #
# ================================================================== #

@router.get(
    "/{incident_id}/pr",
    summary="Get pull request record",
    response_model=Dict[str, Any],
)
async def get_incident_pr(
    incident_id: UUID,
    user_id: str = Depends(require_current_user),
) -> Dict[str, Any]:
    """Return the GitHub pull request record created for this incident."""
    _fetch_incident_row(str(incident_id), user_id)

    try:
        from app.services.supabase import get_supabase

        # First, find the latest fix for this incident
        fix_response = (
            get_supabase()
            .table("fixes")
            .select("id")
            .eq("incident_id", str(incident_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        fix_rows = fix_response.data or []
        if not fix_rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No pull request found for incident {incident_id}.",
            )
            
        fix_id = fix_rows[0]["id"]

        # Now get the PR for that fix
        response = (
            get_supabase()
            .table("pull_requests")
            .select("*")
            .eq("fix_id", fix_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No pull request found for incident {incident_id}.",
            )
        return rows[0]

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "get_incident_pr: DB error | incident_id=%s | error=%s",
            incident_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve PR record.",
        )


# ================================================================== #
# Internal helpers                                                     #
# ================================================================== #

def _fetch_incident_row(incident_id: str, user_id: str) -> Dict[str, Any]:
    """
    Fetch a single incident row, enforcing user ownership.

    Raises HTTPException(404) if the row does not exist or belongs to a
    different user — intentionally indistinguishable to prevent enumeration.
    """
    try:
        from app.services.supabase import get_supabase

        response = (
            get_supabase()
            .table("incidents")
            .select("*")
            .eq("id", incident_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        row: Optional[Dict[str, Any]] = response.data
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Incident {incident_id} not found.",
            )
        return row

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "_fetch_incident_row: DB error | incident_id=%s | error=%s",
            incident_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch incident.",
        )
