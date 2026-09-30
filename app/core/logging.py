"""
Logging for TrueAI.

- One root configuration per process (``configure_logging``), text or JSON.
- Redaction runs on the *final formatted string*, so secrets inside
  exception tracebacks, third-party log lines and uvicorn access logs
  (which carry the webhook ``?key=`` query string) are scrubbed too.
- ``request_id`` / ``incident_id`` are carried in context variables and
  attached to every record emitted while they are set.
- Optional rotating file output, one file per process type so the API and
  the Celery worker never fight over the same file handle.
"""

from __future__ import annotations

import contextvars
import json
import logging
import logging.handlers
import re
import sys
from datetime import datetime, timezone
from typing import Final, Optional

_DATE_FMT: Final[str] = "%Y-%m-%dT%H:%M:%S"
_TEXT_FMT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s%(ctx)s"
_MAX_BYTES: Final[int] = 10 * 1024 * 1024
_BACKUP_COUNT: Final[int] = 5

request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("request_id", default=None)
incident_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("incident_id", default=None)

# ------------------------------------------------------------------ #
# Redaction                                                            #
# ------------------------------------------------------------------ #

_SENSITIVE_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    # TrueAI API keys (also inside ?key= query strings)
    (re.compile(r"tai_[A-Za-z0-9_\-]{8,}"), "tai_[REDACTED]"),
    # key=value pairs in URLs / query strings
    (re.compile(r"(?i)([?&](?:key|api_key|token|access_token|code|state|handoff)=)[^&\s\"']+"), r"\1[REDACTED]"),
    # GitHub tokens
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[GITHUB_TOKEN_REDACTED]"),
    # LLM provider keys
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"), "[GROQ_KEY_REDACTED]"),
    (re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b"), "[LLM_KEY_REDACTED]"),
    # Sentry tokens
    (re.compile(r"\bsntry[su]_[A-Za-z0-9_=\-]{20,}\b"), "[SENTRY_TOKEN_REDACTED]"),
    # JWTs (Supabase access tokens, service role key)
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"), "[JWT_REDACTED]"),
    # Authorization headers
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9+/=_\-\.]{12,}"), r"\1 [REDACTED]"),
    # Generic key: value / key=value secrets
    (
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|passwd|client_secret|access_token|refresh_token|private[_-]?key)"
            r"(\s*[\"']?\s*[:=]\s*[\"']?)([^\s\"',&]{6,})"
        ),
        r"\1\2[REDACTED]",
    ),
]


def redact(text: str) -> str:
    """Return *text* with every known credential pattern replaced."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class _ContextFilter(logging.Filter):
    """Attach request/incident correlation ids to every record."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = request_id_var.get()
        record.incident_id = incident_id_var.get()
        try:
            message = record.getMessage()
        except Exception:  # a malformed record still gets logged; the formatter reports the problem
            message = ""
        parts = []
        for key in ("request_id", "incident_id"):
            value = getattr(record, key)
            # Skip ids the message already names, so lines don't repeat them.
            if value and f"{key}={value}" not in message:
                parts.append(f"{key}={value}")
        record.ctx = f" | {' '.join(parts)}" if parts else ""
        return True


class RedactingTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "ctx"):
            record.ctx = ""
        return redact(super().format(record))


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "incident_id"):
            value = getattr(record, key, None)
            if value:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str, ensure_ascii=False))


class SensitiveDataFilter(logging.Filter):
    """
    Logger-level filter for loggers that bypass the root handlers
    (uvicorn installs its own handlers).  Redacts string message/args in
    place while preserving the args structure — uvicorn's access formatter
    unpacks ``record.args`` positionally.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


# ------------------------------------------------------------------ #
# Configuration                                                        #
# ------------------------------------------------------------------ #

_configured_service: Optional[str] = None


def configure_logging(service: str = "app", *, force: bool = False) -> None:
    """
    Configure the root logger for this process.  Safe to call repeatedly —
    only the first call (or a ``force=True`` call) has an effect.
    """
    global _configured_service
    if _configured_service is not None and not force:
        return

    # Imported lazily so this module has no import-time dependency on config
    # (config validation errors must still be loggable).
    try:
        from app.core.config import settings

        level = getattr(logging, settings.LOG_LEVEL)
        use_json = settings.LOG_FORMAT == "json"
        log_dir = settings.log_dir_path
    except Exception:  # pragma: no cover - misconfigured env
        level, use_json, log_dir = logging.INFO, False, None

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(min(level, logging.DEBUG) if log_dir else level)

    formatter: logging.Formatter = (
        RedactingJsonFormatter() if use_json else RedactingTextFormatter(_TEXT_FMT, _DATE_FMT)
    )
    context_filter = _ContextFilter()

    # Windows consoles default to cp1252; never let a non-ASCII character in a
    # log line (e.g. a user's error message) raise UnicodeEncodeError.
    try:
        sys.stdout.reconfigure(errors="backslashreplace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    console.addFilter(context_filter)
    root.addHandler(console)

    if log_dir is not None and service != "test":
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_dir / f"{service}.log",
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
                delay=True,
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            file_handler.addFilter(context_filter)
            root.addHandler(file_handler)
        except OSError as exc:  # read-only filesystem in containers
            root.warning("File logging disabled (%s): %s", log_dir, exc)

    for noisy in ("httpx", "httpcore", "urllib3", "hpack", "celery", "kombu", "github", "openai", "groq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # uvicorn logs through its own handlers; redact at the logger level so
    # ``?key=tai_...`` never reaches the access log.
    redactor = SensitiveDataFilter()
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        if not any(isinstance(f, SensitiveDataFilter) for f in uv_logger.filters):
            uv_logger.addFilter(redactor)

    _configured_service = service


def get_logger(name: str) -> logging.Logger:
    """Return a named logger; configures logging with defaults on first use."""
    if _configured_service is None:
        configure_logging("app")
    return logging.getLogger(name)
