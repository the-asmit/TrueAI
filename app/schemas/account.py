"""
Pydantic request models for account, API key and integration endpoints.

All free-text input is length-limited and stripped; identifiers (repository,
branch, Sentry slugs) are validated against the character sets the external
services themselves allow, so nothing unexpected reaches GitHub, Sentry or
PostgREST filters.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
_BRANCH_FORBIDDEN = re.compile(r"(\.\.|[\x00-\x20~^:?*\[\\]|@\{|//|/$|^/|\.lock$|\.$)")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def _clean_text(value: str) -> str:
    return _CONTROL_CHARS.sub("", value or "").strip()


def validate_repo_full_name(value: str) -> str:
    value = (value or "").strip().removeprefix("https://github.com/").rstrip("/").removesuffix(".git")
    if not _REPO_RE.match(value) or value.split("/")[1] in (".", ".."):
        raise ValueError("Repository must look like 'owner/repo'.")
    return value


def validate_branch_name(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > 250 or _BRANCH_FORBIDDEN.search(value):
        raise ValueError("Enter a valid Git branch name.")
    return value


def validate_sentry_slug(value: str) -> str:
    value = (value or "").strip().lower()
    if not _SLUG_RE.match(value):
        raise ValueError("Use the slug shown in Sentry URLs (lowercase letters, numbers, - and _).")
    return value


class ProfileUpdateRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)

    @field_validator("full_name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = _clean_text(value)
        if not value:
            raise ValueError("Name cannot be empty.")
        return value


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(default="Sentry webhook", max_length=60)

    @field_validator("name")
    @classmethod
    def _label(cls, value: str) -> str:
        return _clean_text(value) or "Sentry webhook"


class RepoSelectRequest(BaseModel):
    repo_name: str
    branch_name: Optional[str] = None

    @field_validator("repo_name")
    @classmethod
    def _repo(cls, value: str) -> str:
        return validate_repo_full_name(value)

    @field_validator("branch_name")
    @classmethod
    def _branch(cls, value: Optional[str]) -> Optional[str]:
        return validate_branch_name(value) if value else None


class BranchSelectRequest(BaseModel):
    branch_name: str

    @field_validator("branch_name")
    @classmethod
    def _branch(cls, value: str) -> str:
        return validate_branch_name(value)


class RepoMappingRequest(BaseModel):
    sentry_project: str
    repo_full_name: str
    branch: Optional[str] = None

    @field_validator("sentry_project")
    @classmethod
    def _project(cls, value: str) -> str:
        return validate_sentry_slug(value)

    @field_validator("repo_full_name")
    @classmethod
    def _repo(cls, value: str) -> str:
        return validate_repo_full_name(value)

    @field_validator("branch")
    @classmethod
    def _branch(cls, value: Optional[str]) -> Optional[str]:
        return validate_branch_name(value) if value else None


class SentrySettingsRequest(BaseModel):
    """Every field is optional; send an empty string to clear a stored secret."""

    org_slug: Optional[str] = None
    base_url: Optional[str] = None
    auth_token: Optional[str] = Field(default=None, max_length=500)
    webhook_secret: Optional[str] = Field(default=None, max_length=500)

    @field_validator("org_slug")
    @classmethod
    def _org(cls, value: Optional[str]) -> Optional[str]:
        return validate_sentry_slug(value) if value else value

    @field_validator("auth_token", "webhook_secret")
    @classmethod
    def _secret(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None


class GitHubCompleteRequest(BaseModel):
    handoff: str = Field(min_length=20, max_length=200)
