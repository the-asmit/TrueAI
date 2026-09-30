"""
Typed error hierarchy shared by services, agents and pipeline nodes.

The ``retryable`` flag is the contract between the pipeline and the Celery
task: a failure caused by a transient upstream problem (rate limit, timeout,
5xx) is retried with backoff; a permanent failure (bad credentials, invalid
input, policy rejection) is recorded once and never retried.
"""

from __future__ import annotations


class TrueAIError(Exception):
    """Base class for all domain errors."""

    retryable: bool = False

    def __init__(self, message: str, *, retryable: bool | None = None) -> None:
        super().__init__(message)
        if retryable is not None:
            self.retryable = retryable

    @property
    def message(self) -> str:
        return str(self)


class ConfigurationError(TrueAIError):
    """A required setting or credential is missing or invalid."""


class DatabaseError(TrueAIError):
    """A Supabase/PostgREST call failed."""

    retryable = True


class LLMError(TrueAIError):
    """An LLM provider call failed (after retries when transient)."""


class AgentOutputError(TrueAIError):
    """An agent's response could not be parsed into its output schema."""


class GitHubError(TrueAIError):
    """A GitHub API call failed."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool | None = None) -> None:
        if retryable is None:
            retryable = status is None or status == 429 or status >= 500
        super().__init__(message, retryable=retryable)
        self.status = status


class PatchError(TrueAIError):
    """A proposed edit could not be applied or failed validation."""


class SentryAPIError(TrueAIError):
    """A Sentry REST API call failed."""
