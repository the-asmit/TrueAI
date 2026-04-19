"""
Pydantic v2 models for GitHub OAuth tokens, file context, and PR requests.

Security notes:
  - GitHubTokenResponse deliberately omits access_token and refresh_token.
    Tokens are write-once: stored on creation, never re-exposed via the API.
  - token_type is included in the response so callers know which OAuth flow
    produced the token (e.g. 'bearer' vs. installation token).
  - All token fields are marked as SecretStr internally to prevent accidental
    serialisation into logs.  The Supabase service layer is responsible for
    calling .get_secret_value() only when writing to the database.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


# ------------------------------------------------------------------ #
# GitHub OAuth token models                                            #
# ------------------------------------------------------------------ #

class GitHubTokenCreate(BaseModel):
    """
    Payload used to persist a GitHub OAuth access token for a workspace user.

    The token is stored as :class:`~pydantic.SecretStr` so that calling
    ``str(model)`` or serialising to JSON does not accidentally leak the
    raw value.  The Supabase service layer calls
    ``access_token.get_secret_value()`` exactly once, at write time.
    """

    user_id: str = Field(
        description="TrueAI workspace user ID that owns this token.",
    )
    access_token: SecretStr = Field(
        description="GitHub OAuth access token (write-once; never re-exposed).",
    )
    token_type: str = Field(
        default="bearer",
        description="OAuth token type as returned by GitHub ('bearer').",
        max_length=64,
    )
    scope: Optional[str] = Field(
        default=None,
        description=(
            "Space-separated list of granted OAuth scopes "
            "(e.g. 'repo,read:user')."
        ),
        max_length=512,
    )
    github_username: str = Field(
        description="GitHub login (username) of the authenticated user.",
        max_length=255,
    )
    github_user_id: Optional[int] = Field(
        default=None,
        description="GitHub numeric user ID for stable cross-rename identification.",
    )
    repo_name: Optional[str] = Field(
        default=None,
        description=(
            "Default repository in 'owner/repo' format that this token is "
            "used to access.  Nullable; some tokens cover the whole account."
        ),
        max_length=512,
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description=(
            "UTC expiry time for fine-grained PATs or GitHub App tokens. "
            "None for classic OAuth tokens that do not expire."
        ),
    )

    @field_validator("user_id", "github_username")
    @classmethod
    def not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank.")
        return v.strip()

    @field_validator("repo_name", mode="before")
    @classmethod
    def normalise_repo_name(cls, v: Optional[str]) -> Optional[str]:
        """Ensure repo_name is in 'owner/repo' format when provided."""
        if v is None:
            return None
        v = v.strip()
        if v and "/" not in v:
            raise ValueError(
                f"repo_name must be in 'owner/repo' format, got: {v!r}"
            )
        return v or None


class GitHubTokenResponse(BaseModel):
    """
    GitHub token record as returned by the API.

    access_token is intentionally excluded — once written it is never
    re-exposed.  Clients that need to re-authenticate should go through
    the OAuth flow again.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    user_id: str
    token_type: str
    scope: Optional[str] = None
    github_username: str
    github_user_id: Optional[int] = None
    repo_name: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # access_token is deliberately absent from this model.


# ------------------------------------------------------------------ #
# GitHub file context                                                  #
# ------------------------------------------------------------------ #

class GitHubFileContext(BaseModel):
    """
    Represents a file (or a relevant slice of a file) fetched from GitHub.

    The fetcher service populates a list of these objects for every filename
    that appears in the filtered stack frames.  They are then stored in
    ``IncidentState.github_context`` as a ``Dict[file_path, content]``.

    Having line range metadata (start_line / end_line) lets the LLM know
    whether it received the complete file or just a focused excerpt, which
    affects how it reasons about the surrounding context.
    """

    file_path: str = Field(
        description="Relative path within the repository (e.g. 'app/services/redis.py').",
    )
    content: str = Field(
        description="Raw UTF-8 text content of the file or excerpt.",
    )
    start_line: int = Field(
        default=1,
        ge=1,
        description=(
            "1-based index of the first line in *content* relative to the "
            "full file.  Always 1 when the full file is returned."
        ),
    )
    end_line: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "1-based index of the last line in *content* relative to the "
            "full file.  None when the full file is returned."
        ),
    )
    sha: Optional[str] = Field(
        default=None,
        description="Git blob SHA of the file at the fetched commit.",
        max_length=64,
    )
    ref: Optional[str] = Field(
        default=None,
        description="Git ref (branch name or commit SHA) the content was fetched from.",
        max_length=255,
    )
    size_bytes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Size of the complete file in bytes as reported by the GitHub API.",
    )
    truncated: bool = Field(
        default=False,
        description=(
            "True when content is a focused excerpt rather than the full file. "
            "The LLM prompt should mention truncation to avoid hallucinating "
            "lines outside the provided window."
        ),
    )

    @field_validator("file_path")
    @classmethod
    def file_path_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("file_path must not be blank.")
        return v.strip().lstrip("/")   # normalise away leading slash

    @field_validator("content", mode="before")
    @classmethod
    def coerce_content(cls, v) -> str:
        """Accept bytes (GitHub API sometimes returns them) by decoding UTF-8."""
        if isinstance(v, bytes):
            return v.decode("utf-8", errors="replace")
        return str(v) if v is not None else ""

    @property
    def line_count(self) -> int:
        """Number of lines in *content*."""
        return self.content.count("\n") + 1 if self.content else 0

    def to_prompt_block(self) -> str:
        """
        Format the file context as a labelled code block for LLM prompts.

        Example output::

            === app/services/redis.py (lines 1-120, sha: a1b2c3) ===
            <content here>
            === end app/services/redis.py ===
        """
        header_parts = [self.file_path]
        if self.truncated and self.end_line:
            header_parts.append(f"lines {self.start_line}–{self.end_line}")
        if self.sha:
            header_parts.append(f"sha: {self.sha[:7]}")
        header = " | ".join(header_parts)
        return f"=== {header} ===\n{self.content}\n=== end {self.file_path} ==="


# ------------------------------------------------------------------ #
# GitHub PR request                                                    #
# ------------------------------------------------------------------ #

class GitHubPRRequest(BaseModel):
    """
    All data required by the pr_creator node to open a GitHub pull request.

    Constructed by the decision node once the fix is approved, using
    information from IncidentState and the FixCreate record.
    """

    branch_name: str = Field(
        description=(
            "Name of the source branch that carries the fix commits. "
            "Convention: 'trueai/fix-<incident_id[:8]>'."
        ),
        max_length=255,
    )
    base_branch: str = Field(
        default="main",
        description="Target branch the PR should merge into.",
        max_length=255,
    )
    title: str = Field(
        description="PR title shown in the GitHub UI.",
        max_length=512,
    )
    body: str = Field(
        description=(
            "Markdown PR description.  Should include root cause, explanation, "
            "confidence score, and a link back to the Sentry event."
        ),
    )
    draft: bool = Field(
        default=False,
        description=(
            "Open as a draft PR when True — useful for low-confidence fixes "
            "that need human review before the CI suite runs."
        ),
    )
    labels: List[str] = Field(
        default_factory=lambda: ["trueai", "automated-fix"],
        description="GitHub label names to attach to the PR on creation.",
    )
    assignees: List[str] = Field(
        default_factory=list,
        description="GitHub usernames to assign as reviewers.",
    )

    @field_validator("branch_name", "base_branch", "title")
    @classmethod
    def not_blank(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be blank.")
        return v.strip()

    @field_validator("branch_name")
    @classmethod
    def branch_name_safe(cls, v: str) -> str:
        """
        Reject branch names containing characters that Git or GitHub forbid:
        spaces, ``..``, leading/trailing dots or slashes, ``~``, ``^``,
        ``:`` and control characters.
        """
        forbidden = (" ", "..", "~", "^", ":", "\\", "?", "*", "[")
        for char in forbidden:
            if char in v:
                raise ValueError(
                    f"branch_name contains forbidden character {char!r}."
                )
        if v.startswith(".") or v.startswith("/") or v.endswith("/") or v.endswith(".lock"):
            raise ValueError(
                f"branch_name {v!r} violates Git ref naming rules."
            )
        return v

    @field_validator("labels", "assignees", mode="before")
    @classmethod
    def coerce_to_list(cls, v) -> List[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(item) for item in v]
