"""
Pydantic v2 models for incoming Sentry webhook payloads.

Sentry webhook payloads are notoriously inconsistent across SDK versions,
project configurations, and issue types.  Every field outside of event_id is
treated as optional, and validators normalise the most common shape variations
(e.g. tags as dict vs. list-of-pairs, timestamps as ISO strings vs. floats)
so that downstream code never has to deal with raw Sentry quirks.

Reference:
  https://docs.sentry.io/product/integrations/integration-platform/webhooks/
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ------------------------------------------------------------------ #
# Stack frame                                                          #
# ------------------------------------------------------------------ #

class SentryStackFrame(BaseModel):
    """
    A single frame from a Sentry exception stacktrace.

    All fields are Optional because:
    - Native/C-extension frames often omit filename and lineno.
    - Minified JS payloads may have no context lines at all.
    - Sentry's own internal frames sometimes carry only a module path.
    """

    model_config = ConfigDict(extra="allow")   # preserve any extra Sentry fields

    filename: Optional[str] = Field(
        default=None,
        description="Relative path to the source file.",
    )
    abs_path: Optional[str] = Field(
        default=None,
        description="Absolute filesystem path (as seen on the server).",
    )
    lineno: Optional[int] = Field(
        default=None,
        description="1-based line number where the error occurred.",
    )
    colno: Optional[int] = Field(
        default=None,
        description="Column number (present in JS payloads).",
    )
    function: Optional[str] = Field(
        default=None,
        description="Name of the function / method in the frame.",
    )
    module: Optional[str] = Field(
        default=None,
        description="Python module path (e.g. 'app.services.github.client').",
    )
    context_line: Optional[str] = Field(
        default=None,
        description="The exact source line that was executing.",
    )
    pre_context: List[str] = Field(
        default_factory=list,
        description="Lines immediately before context_line.",
    )
    post_context: List[str] = Field(
        default_factory=list,
        description="Lines immediately after context_line.",
    )
    in_app: Optional[bool] = Field(
        default=None,
        description=(
            "True when Sentry considers the frame to belong to user code "
            "rather than a third-party library or the standard library."
        ),
    )
    vars: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Local variables captured at this frame.",
    )

    @field_validator("pre_context", "post_context", mode="before")
    @classmethod
    def coerce_context_to_list(cls, v: Any) -> List[str]:
        """Sentry occasionally sends None instead of an empty list."""
        if v is None:
            return []
        if isinstance(v, list):
            return [str(line) for line in v]
        return [str(v)]

    @field_validator("lineno", "colno", mode="before")
    @classmethod
    def coerce_lineno(cls, v: Any) -> Optional[int]:
        """Guard against Sentry sending lineno as a string ('42')."""
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def is_in_app(self) -> bool:
        """
        Return True if this frame belongs to user-authored code.

        Falls back to a filename heuristic when Sentry's in_app flag is
        absent: frames whose filename starts with a path component that
        looks like site-packages or a stdlib path are considered external.
        """
        if self.in_app is not None:
            return self.in_app

        # Heuristic fallback
        f = self.filename or self.module or ""
        external_markers = (
            "site-packages",
            "dist-packages",
            "lib/python",
            "<frozen ",
            "<string>",
            "importlib",
        )
        return not any(marker in f for marker in external_markers)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict suitable for storing in IncidentState.stack_frames."""
        return {
            "filename": self.filename,
            "abs_path": self.abs_path,
            "lineno": self.lineno,
            "function": self.function,
            "module": self.module,
            "context_line": self.context_line,
            "pre_context": self.pre_context,
            "post_context": self.post_context,
            "in_app": self.in_app,
            "vars": self.vars,
        }


# ------------------------------------------------------------------ #
# Stacktrace                                                           #
# ------------------------------------------------------------------ #

class SentryStacktrace(BaseModel):
    """Container for an ordered list of stack frames."""

    model_config = ConfigDict(extra="allow")

    frames: List[SentryStackFrame] = Field(
        default_factory=list,
        description=(
            "Frames in innermost-last order (same as Python tracebacks). "
            "The last frame is the one closest to the raised exception."
        ),
    )

    @field_validator("frames", mode="before")
    @classmethod
    def coerce_frames(cls, v: Any) -> List[Any]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return []


# ------------------------------------------------------------------ #
# Exception value                                                      #
# ------------------------------------------------------------------ #

class SentryExceptionValue(BaseModel):
    """
    A single exception value within Sentry's ``exception.values`` list.

    Chained exceptions (``__cause__`` / ``__context__``) each produce a
    separate entry in this list.
    """

    model_config = ConfigDict(extra="allow")

    type: Optional[str] = Field(
        default=None,
        description="Exception class name (e.g. 'KeyError', 'IntegrityError').",
    )
    value: Optional[str] = Field(
        default=None,
        description="Stringified exception message.",
    )
    module: Optional[str] = Field(
        default=None,
        description="Python module in which the exception type is defined.",
    )
    stacktrace: Optional[SentryStacktrace] = Field(
        default=None,
        description="Stacktrace associated with this exception value.",
    )
    mechanism: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Sentry mechanism metadata (handled, type, etc.).",
    )

    def get_frames(self) -> List[SentryStackFrame]:
        """Return all stack frames for this exception, or an empty list."""
        if self.stacktrace is None:
            return []
        return self.stacktrace.frames


# ------------------------------------------------------------------ #
# Exception container                                                  #
# ------------------------------------------------------------------ #

class SentryExceptionContainer(BaseModel):
    """
    Wraps the top-level ``exception`` key in a Sentry event.

    The ``values`` list holds one entry per exception in a chain; index 0
    is the outermost / root cause exception.
    """

    model_config = ConfigDict(extra="allow")

    values: List[SentryExceptionValue] = Field(default_factory=list)

    @field_validator("values", mode="before")
    @classmethod
    def coerce_values(cls, v: Any) -> List[Any]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        # Some Sentry SDK versions wrap it in an extra dict level
        if isinstance(v, dict):
            return v.get("values", [])
        return []


# ------------------------------------------------------------------ #
# Sentry user context                                                  #
# ------------------------------------------------------------------ #

class SentryUser(BaseModel):
    """Optional user context attached to a Sentry event."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = Field(default=None)
    username: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    ip_address: Optional[str] = Field(default=None)


# ------------------------------------------------------------------ #
# Sentry request context                                               #
# ------------------------------------------------------------------ #

class SentryRequest(BaseModel):
    """HTTP request context captured at the time of the error."""

    model_config = ConfigDict(extra="allow")

    url: Optional[str] = Field(default=None)
    method: Optional[str] = Field(default=None)
    headers: Optional[Dict[str, Any]] = Field(default=None)
    query_string: Optional[Union[str, Dict[str, Any]]] = Field(default=None)
    data: Optional[Any] = Field(default=None)
    env: Optional[Dict[str, Any]] = Field(default=None)


# ------------------------------------------------------------------ #
# Top-level Sentry webhook payload                                     #
# ------------------------------------------------------------------ #

class SentryWebhookPayload(BaseModel):
    """
    Top-level model for a Sentry ``issue.created`` or ``error`` webhook event.

    Designed to be maximally defensive:
    - Unknown keys are preserved via ``extra="allow"`` for audit logging.
    - The ``tags`` field is normalised from either ``{"k": "v"}`` dicts or
      ``[["k", "v"], ...]`` list-of-pairs into a consistent ``Dict[str, str]``.
    - ``timestamp`` is normalised to a UTC-aware ``datetime`` regardless of
      whether Sentry sent an ISO 8601 string or a Unix float.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    event_id: Optional[str] = Field(
        default=None,
        description="Sentry event UUID.",
    )
    level: Optional[str] = Field(
        default=None,
        description="Severity level: 'debug', 'info', 'warning', 'error', 'fatal'.",
    )
    environment: Optional[str] = Field(
        default=None,
        description="Deployment environment (e.g. 'production', 'staging').",
    )
    platform: Optional[str] = Field(
        default=None,
        description="SDK platform identifier (e.g. 'python', 'javascript').",
    )
    release: Optional[Union[str, Any]] = Field(
        default=None,
        description="Application release/version string.",
    )
    timestamp: Optional[datetime] = Field(
        default=None,
        description="UTC datetime when the event was captured.",
    )
    exception: Optional[SentryExceptionContainer] = Field(
        default=None,
        description="Exception chain captured by the Sentry SDK.",
    )
    tags: Dict[str, str] = Field(
        default_factory=dict,
        description="Key/value metadata tags attached to the event.",
    )
    user: Optional[SentryUser] = Field(
        default=None,
        description="User context at the time of the error.",
    )
    request: Optional[SentryRequest] = Field(
        default=None,
        description="HTTP request context at the time of the error.",
    )
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary extra context dict attached by the application.",
    )
    breadcrumbs: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Sentry breadcrumbs trail leading up to the event.",
    )
    server_name: Optional[str] = Field(
        default=None,
        description="Hostname of the server that captured the event.",
    )
    transaction: Optional[str] = Field(
        default=None,
        description="Name of the active transaction / route when the error occurred.",
    )

    # ---------------------------------------------------------------- #
    # Validators                                                         #
    # ---------------------------------------------------------------- #

    @field_validator("tags", mode="before")
    @classmethod
    def normalise_tags(cls, v: Any) -> Dict[str, str]:
        """
        Normalise Sentry tags into a plain ``Dict[str, str]``.

        Sentry sends tags in two formats depending on SDK version:
          - Dict:           ``{"server_name": "web-1", "runtime": "CPython 3.11"}``
          - List of pairs:  ``[["server_name", "web-1"], ["runtime", "CPython 3.11"]]``
        """
        if v is None:
            return {}
        if isinstance(v, dict):
            return {str(k): str(val) for k, val in v.items()}
        if isinstance(v, list):
            result: Dict[str, str] = {}
            for item in v:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    result[str(item[0])] = str(item[1])
                elif isinstance(item, dict) and "key" in item and "value" in item:
                    # Some integrations emit {"key": "...", "value": "..."}
                    result[str(item["key"])] = str(item["value"])
            return result
        return {}

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalise_timestamp(cls, v: Any) -> Optional[datetime]:
        """
        Accept ISO 8601 strings, Unix float/int timestamps, or None.

        Always returns a UTC-aware datetime so callers never have to guess
        the timezone.
        """
        if v is None:
            return None
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        if isinstance(v, str):
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None

    @field_validator("level", mode="before")
    @classmethod
    def normalise_level(cls, v: Any) -> Optional[str]:
        """Lower-case the level string for consistent comparisons downstream."""
        if v is None:
            return None
        return str(v).lower()

    @model_validator(mode="before")
    @classmethod
    def extract_nested_event_data(cls, data: Any) -> Any:
        """
        Promote fields from a nested ``event`` key up to the top level.

        Some Sentry webhook formats (e.g. issue.created alerts) wrap the
        actual error event inside a top-level ``event`` key rather than
        inlining it directly.  This validator normalises both shapes so the
        rest of the model always sees a flat structure.

        Fields promoted (only when the top-level field is absent/empty):
          - ``exception``  — the exception chain with stack frames
          - ``message``    — human-readable error message
          - ``level``      — severity level string
          - ``timestamp``  — event capture time
        """
        if not isinstance(data, dict):
            return data

        nested_event = data.get("event", {}) or {}

        # If top-level exception is missing/empty, use nested event's exception
        if not data.get("exception") and nested_event.get("exception"):
            data["exception"] = nested_event["exception"]

        # If top-level message is missing, use nested event's message
        if not data.get("message") and nested_event.get("message"):
            data["message"] = nested_event["message"]

        # If top-level level is missing, use nested event's level
        if not data.get("level") and nested_event.get("level"):
            data["level"] = nested_event["level"]

        # If top-level timestamp is missing, use nested event's timestamp
        if not data.get("timestamp") and nested_event.get("timestamp"):
            data["timestamp"] = nested_event["timestamp"]

        return data

    # ---------------------------------------------------------------- #
    # Public helpers                                                     #
    # ---------------------------------------------------------------- #

    def get_stack_frames(self) -> List[SentryStackFrame]:
        """
        Return all stack frames across every exception in the chain.

        Frames are returned in the order they appear in the payload —
        innermost-last per Sentry convention.  The parser node is responsible
        for filtering to in-app frames only.

        Returns:
            A flat list of :class:`SentryStackFrame` objects; empty list when
            the payload carries no exception data.
        """
        if self.exception is None:
            return []

        frames: List[SentryStackFrame] = []
        for exc_value in self.exception.values:
            frames.extend(exc_value.get_frames())
        return frames

    def get_primary_exception(self) -> Optional[SentryExceptionValue]:
        """
        Return the innermost (most recent) exception value, which is
        typically the direct cause of the error.

        Returns None when no exception data is present.
        """
        if not self.exception or not self.exception.values:
            return None
        # Sentry stores the chain innermost-last
        return self.exception.values[-1]

    def get_error_type(self) -> Optional[str]:
        """Convenience accessor for the primary exception type string."""
        exc = self.get_primary_exception()
        return exc.type if exc else None

    def get_error_message(self) -> Optional[str]:
        """Convenience accessor for the primary exception message string."""
        exc = self.get_primary_exception()
        return exc.value if exc else None

    def get_in_app_frames(self) -> List[SentryStackFrame]:
        """
        Return only frames that belong to user-authored code.

        Uses :meth:`SentryStackFrame.is_in_app` which checks Sentry's flag
        first and falls back to a path heuristic when the flag is absent.
        """
        return [f for f in self.get_stack_frames() if f.is_in_app()]
