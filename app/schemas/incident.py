"""
Pydantic v2 models for incident data structures.

These models are the contract between:
  - The API layer (request/response serialisation)
  - The Supabase persistence layer (ORM-mode deserialisation via from_attributes)
  - The pipeline (status transitions)

Design principles:
  - IncidentCreate   — minimal fields required to INSERT a row
  - IncidentUpdate   — partial fields accepted for PATCH; all Optional so
                       callers only send what they want to change
  - IncidentResponse — complete row as returned by SELECT; always includes
                       server-assigned id and timestamps
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ------------------------------------------------------------------ #
# Enumerations                                                         #
# ------------------------------------------------------------------ #

class IncidentStatus(str, Enum):
    """Allowed lifecycle states for an incident row."""

    PENDING = "pending"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    FAILED = "failed"
    FLAGGED = "flagged"


class IssueClassification(str, Enum):
    """
    Categorical classification of the root cause type.

    Kept as a schema-level enum so the API rejects invalid values before
    they reach the pipeline.
    """

    CODE_BUG = "code_bug"
    CONFIG_ISSUE = "config_issue"
    INFRASTRUCTURE = "infrastructure"
    DATA_ISSUE = "data_issue"
    DEPENDENCY = "dependency"
    UNKNOWN = "unknown"           # default when classifier has not run yet


# ------------------------------------------------------------------ #
# IncidentCreate                                                       #
# ------------------------------------------------------------------ #

class IncidentCreate(BaseModel):
    """
    Fields required to open a new incident record in the database.

    Typically constructed by the webhook route immediately after the Sentry
    payload is validated.
    """

    user_id: str = Field(
        description="Identifier of the workspace/tenant that owns this incident.",
    )
    sentry_event_id: Optional[str] = Field(
        default=None,
        description="Sentry event UUID from the webhook payload.  Stored for dedup.",
        max_length=255,
    )
    error_type: Optional[str] = Field(
        default=None,
        description="Exception class name extracted from the Sentry event.",
        max_length=512,
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Stringified exception message.",
    )
    environment: Optional[str] = Field(
        default=None,
        description="Deployment environment (production / staging / dev).",
        max_length=128,
    )
    level: Optional[str] = Field(
        default=None,
        description="Sentry severity level (debug / info / warning / error / fatal).",
        max_length=32,
    )
    platform: Optional[str] = Field(
        default=None,
        description="Runtime platform (python / javascript / etc.).",
        max_length=64,
    )
    raw_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Complete original Sentry webhook payload for audit / re-processing.",
    )
    status: IncidentStatus = Field(
        default=IncidentStatus.PENDING,
        description="Initial lifecycle status; defaults to 'pending'.",
    )
    issue_classification: IssueClassification = Field(
        default=IssueClassification.UNKNOWN,
        description="Classification assigned by the pipeline classifier node.",
    )

    @field_validator("user_id")
    @classmethod
    def user_id_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id must not be blank.")
        return v.strip()

    @field_validator("level", mode="before")
    @classmethod
    def normalise_level(cls, v: Optional[str]) -> Optional[str]:
        return v.lower() if isinstance(v, str) else v


# ------------------------------------------------------------------ #
# IncidentUpdate                                                       #
# ------------------------------------------------------------------ #

class IncidentUpdate(BaseModel):
    """
    Partial update payload accepted by the PATCH /incidents/{id} endpoint.

    All fields are Optional — the service layer merges only the supplied
    keys into the existing row.
    """

    status: Optional[IncidentStatus] = Field(
        default=None,
        description="New lifecycle status.",
    )
    issue_classification: Optional[IssueClassification] = Field(
        default=None,
        description="Updated issue classification (set after pipeline runs).",
    )
    error_type: Optional[str] = Field(
        default=None,
        max_length=512,
    )
    error_message: Optional[str] = Field(default=None)
    environment: Optional[str] = Field(default=None, max_length=128)
    pipeline_error: Optional[str] = Field(
        default=None,
        description="Error message recorded if the pipeline failed.",
    )


# ------------------------------------------------------------------ #
# IncidentResponse                                                     #
# ------------------------------------------------------------------ #

class IncidentResponse(BaseModel):
    """
    Full incident record returned by GET /incidents/{id} and list endpoints.

    ``from_attributes=True`` enables construction from ORM objects or
    Supabase row dicts with attribute-style access.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: UUID = Field(description="Database-assigned UUID primary key.")
    user_id: str
    sentry_event_id: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    environment: Optional[str] = None
    level: Optional[str] = None
    platform: Optional[str] = None
    status: IncidentStatus
    issue_classification: IssueClassification
    pipeline_error: Optional[str] = None
    created_at: datetime = Field(description="UTC timestamp when the row was created.")
    updated_at: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp of the last row update.",
    )


# ------------------------------------------------------------------ #
# IncidentListResponse                                                 #
# ------------------------------------------------------------------ #

class IncidentListResponse(BaseModel):
    """Paginated list of incidents returned by GET /incidents."""

    items: List[IncidentResponse]
    total: int = Field(description="Total number of matching incidents (unpaginated).")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def total_pages(self) -> int:
        """Number of pages given the current page_size."""
        if self.page_size == 0:
            return 0
        import math
        return math.ceil(self.total / self.page_size)
