"""
Pydantic models for incident API requests and responses.

Incident lifecycle
──────────────────
    queued      accepted from Sentry, waiting for a worker (or a retry)
    processing  the agent pipeline is running
    pr_open     a fix pull request is open and awaiting review
    resolved    the fix PR was merged, or a user marked it resolved
    flagged     a human is needed — diagnosis and next steps are attached
    failed      analysis could not complete (re-run is available)
    ignored     a user dismissed it
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IncidentStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    PR_OPEN = "pr_open"
    RESOLVED = "resolved"
    FLAGGED = "flagged"
    FAILED = "failed"
    IGNORED = "ignored"


class IssueClassification(str, Enum):
    CODE_BUG = "code_bug"
    CONFIG_ISSUE = "config_issue"
    INFRASTRUCTURE = "infrastructure"
    DATA_ISSUE = "data_issue"
    DEPENDENCY = "dependency"


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)


class IncidentSummary(_Row):
    id: UUID
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    environment: Optional[str] = None
    level: Optional[str] = None
    platform: Optional[str] = None
    status: str
    issue_classification: Optional[str] = None
    severity: Optional[str] = None
    culprit: Optional[str] = None
    occurrence_count: int = 1
    last_seen_at: Optional[datetime] = None
    sentry_project: Optional[str] = None
    repo_full_name: Optional[str] = None
    current_step: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class IncidentListResponse(BaseModel):
    items: List[IncidentSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class IncidentStats(BaseModel):
    total: int
    by_status: Dict[str, int]


class Analysis(_Row):
    root_cause: Optional[str] = None
    explanation: Optional[str] = None
    confidence: Optional[float] = None
    fix_confidence: Optional[float] = None
    fix_diff: Optional[str] = None
    files_changed: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    rationale: Optional[str] = None
    risk: Optional[str] = None
    validation_passed: Optional[bool] = None
    review_verdict: Optional[str] = None
    review_notes: Optional[str] = None
    remediation: Optional[Dict[str, Any]] = None
    flag_reason: Optional[str] = None
    policy_violations: List[str] = Field(default_factory=list)
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PullRequestInfo(_Row):
    pr_url: str
    pr_number: int
    branch_name: str
    repo_full_name: Optional[str] = None
    title: Optional[str] = None
    status: str
    merged_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class PipelineStep(_Row):
    id: UUID
    step: str
    kind: str
    status: str
    summary: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    duration_ms: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    created_at: datetime


class IncidentDetail(IncidentSummary):
    sentry_event_id: Optional[str] = None
    sentry_issue_id: Optional[str] = None
    sentry_issue_url: Optional[str] = None
    fingerprint: Optional[str] = None
    branch: Optional[str] = None
    pipeline_error: Optional[str] = None
    stack_trace: Optional[Any] = None
    attempts: int = 0
    started_at: Optional[datetime] = None
    llm_input_tokens: Optional[int] = None
    llm_output_tokens: Optional[int] = None
    analysis: Optional[Analysis] = None
    pull_request: Optional[PullRequestInfo] = None
    steps: List[PipelineStep] = Field(default_factory=list)


class IncidentUpdate(BaseModel):
    """User triage actions from the dashboard."""

    status: Literal["resolved", "ignored", "flagged"] = Field(
        description="resolved = fixed; ignored = dismiss; flagged = reopen for review."
    )
