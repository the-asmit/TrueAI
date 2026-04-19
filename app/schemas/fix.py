"""
Pydantic v2 models for fix proposals and pull request records.

Data flow:
  1. Pipeline generates a fix  →  FixCreate  →  Supabase fixes table
  2. pr_creator node opens PR  →  PRCreate   →  Supabase pull_requests table
  3. API layer returns          →  FixResponse / PRResponse

Confidence is validated to [0.0, 1.0] at schema level so the rest of the
codebase can assume it is always a well-formed probability.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _validate_confidence(v: float) -> float:
    """Raise ValueError if *v* is not in [0.0, 1.0]."""
    if not (0.0 <= v <= 1.0):
        raise ValueError(
            f"confidence must be between 0.0 and 1.0, got {v!r}."
        )
    return round(v, 6)   # normalise precision; avoids 0.9999999999 noise


# ------------------------------------------------------------------ #
# Fix models                                                           #
# ------------------------------------------------------------------ #

class FixCreate(BaseModel):
    """
    Fields required to persist a generated fix to the database.

    Constructed by the fix_generator node after the LLM produces a patch
    and the validator node marks it as passing.
    """

    incident_id: UUID = Field(
        description="Foreign key to the incidents table.",
    )
    root_cause: str = Field(
        description=(
            "Concise technical description of why the error occurred, "
            "as produced by the root_cause node."
        ),
    )
    explanation: str = Field(
        description=(
            "Human-readable explanation of the root cause and fix rationale, "
            "suitable for inclusion in a PR description."
        ),
    )
    fix_diff: str = Field(
        description=(
            "Unified diff (patch format) of the proposed code change. "
            "Must be applicable with `git apply` against the target repository."
        ),
    )
    confidence: float = Field(
        description="LLM self-reported confidence in the fix, normalised to [0.0, 1.0].",
    )
    files_changed: List[str] = Field(
        default_factory=list,
        description="Relative repository paths of every file the diff touches.",
    )
    validation_passed: bool = Field(
        default=False,
        description="True when the validator node approved the diff.",
    )
    model_version: Optional[str] = Field(
        default=None,
        description="Identifier of the LLM model that generated the fix (for audit).",
        max_length=128,
    )

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        return _validate_confidence(v)

    @field_validator("root_cause", "explanation", "fix_diff")
    @classmethod
    def not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank.")
        return v

    @field_validator("files_changed", mode="before")
    @classmethod
    def coerce_files_changed(cls, v) -> List[str]:
        if v is None:
            return []
        return [str(f).strip() for f in v if f]


class FixResponse(BaseModel):
    """
    Complete fix record as returned by the API.

    Does not expose the raw diff in list views — callers must fetch the
    individual resource to retrieve fix_diff.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    incident_id: UUID
    root_cause: str
    explanation: str
    fix_diff: str
    confidence: float
    files_changed: List[str]
    validation_passed: bool
    model_version: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class FixSummaryResponse(BaseModel):
    """
    Lightweight fix record for embedding inside an incident response.

    Omits fix_diff to keep list payloads small.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    confidence: float
    validation_passed: bool
    files_changed: List[str]
    created_at: datetime


# ------------------------------------------------------------------ #
# PR models                                                            #
# ------------------------------------------------------------------ #

class PRCreate(BaseModel):
    """
    Fields required to persist a GitHub pull request record to the database.

    Created by the pr_creator node after the GitHub API confirms the PR.
    """

    fix_id: UUID = Field(
        description="Foreign key to the fixes table.",
    )
    incident_id: UUID = Field(
        description=(
            "Denormalised foreign key to the incidents table for convenient "
            "queries without a JOIN."
        ),
    )
    pr_url: str = Field(
        description="Full HTML URL of the created pull request.",
    )
    pr_number: int = Field(
        description="GitHub PR number within the repository.",
        ge=1,
    )
    branch_name: str = Field(
        description="Name of the feature branch the PR was opened from.",
        max_length=255,
    )
    repo_full_name: Optional[str] = Field(
        default=None,
        description="GitHub repository full name in 'owner/repo' format.",
        max_length=255,
    )
    title: Optional[str] = Field(
        default=None,
        description="Title of the pull request.",
        max_length=512,
    )
    merged: bool = Field(
        default=False,
        description="True once the PR has been merged.",
    )

    @field_validator("pr_url")
    @classmethod
    def pr_url_must_be_github(cls, v: str) -> str:
        if not v.startswith("https://github.com/"):
            raise ValueError(
                f"pr_url must be a valid GitHub URL starting with "
                f"'https://github.com/', got: {v!r}"
            )
        return v

    @field_validator("branch_name")
    @classmethod
    def branch_name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("branch_name must not be blank.")
        return v.strip()


class PRResponse(BaseModel):
    """Full pull request record as returned by the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    fix_id: UUID
    incident_id: UUID
    pr_url: str
    pr_number: int
    branch_name: str
    repo_full_name: Optional[str] = None
    title: Optional[str] = None
    merged: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# ------------------------------------------------------------------ #
# Confidence threshold constants                                       #
# ------------------------------------------------------------------ #

# The decision node uses these thresholds to choose between "create_pr"
# and "flag_for_review".  Centralised here so the values are easy to tune
# without hunting through pipeline code.

CONFIDENCE_AUTO_FIX_THRESHOLD: float = 0.75
"""Minimum confidence required to open a PR automatically."""

CONFIDENCE_LOW_THRESHOLD: float = 0.40
"""Below this value, the fix is considered unreliable and is discarded."""
