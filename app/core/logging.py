"""
Production-grade logging setup for TrueAI.

Features:
- Structured format:  timestamp | level | module | message
- Simultaneous output to console (stdout) and a rotating log file
- RotatingFileHandler: 10 MB per file, 5 backups
- SensitiveDataFilter: redacts API keys, tokens, and secrets before any
  log record is emitted — prevents credential leakage in log aggregators
- Thread-safe: the stdlib logging module is thread-safe by design
"""

import logging
import logging.handlers
import re
import sys
from pathlib import Path
from typing import Final


# ------------------------------------------------------------------ #
# Constants                                                            #
# ------------------------------------------------------------------ #

_LOG_DIR: Final[Path] = Path("logs")
_LOG_FILE: Final[Path] = _LOG_DIR / "app.log"
_MAX_BYTES: Final[int] = 10 * 1024 * 1024   # 10 MB
_BACKUP_COUNT: Final[int] = 5
_DATE_FMT: Final[str] = "%Y-%m-%dT%H:%M:%S"

# Structured format — all fields separated by " | " for easy parsing
_LOG_FMT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# ------------------------------------------------------------------ #
# Sensitive-data redaction                                             #
# ------------------------------------------------------------------ #

# Each tuple is (compiled_regex, replacement_string).
# Order matters: more specific patterns should come first.
_SENSITIVE_PATTERNS: Final[list] = [
    # Generic key=value / key: value patterns
    (
        re.compile(
            r'(?i)(api[_-]?key|apikey|secret|password|passwd|token|bearer'
            r'|authorization|auth|credential|private[_-]?key)'
            r'(["\s:=]+)([A-Za-z0-9+/=_\-\.]{8,})',
            re.IGNORECASE,
        ),
        r"\1\2[REDACTED]",
    ),
    # Anthropic sk-ant-... keys
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "[ANTHROPIC_KEY_REDACTED]"),
    # GitHub tokens (ghp_, ghs_, github_pat_)
    (re.compile(r"(ghp_|ghs_|github_pat_)[A-Za-z0-9_]{20,}"), "[GITHUB_TOKEN_REDACTED]"),
    # JWT — three base64url segments separated by dots
    (
        re.compile(
            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
        ),
        "[JWT_REDACTED]",
    ),
    # Supabase service-role / anon keys (long base64-like strings after "ey")
    (re.compile(r"ey[A-Za-z0-9_\-]{40,}\.[A-Za-z0-9_\-]{40,}"), "[SUPABASE_KEY_REDACTED]"),
]


def _redact(text: str) -> str:
    """Apply all sensitive-data patterns to *text* and return the sanitised result."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that redacts credentials from log records in-place.

    Applied to both handlers so no sensitive data can reach the console
    or the log file, regardless of which logger emitted the record.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        # Redact the main message
        record.msg = _redact(str(record.msg))

        # Redact any extra positional args (used in %-style formatting)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact(str(v)) for k, v in record.args.items()}
            else:
                record.args = tuple(_redact(str(a)) for a in record.args)

        # Redact exc_text if an exception was already formatted
        if record.exc_text:
            record.exc_text = _redact(record.exc_text)

        return True  # always pass the record through (after sanitisation)


# ------------------------------------------------------------------ #
# Internal setup — runs once at import time                            #
# ------------------------------------------------------------------ #

def _configure_root_logger() -> None:
    """
    Configure the root logger exactly once.

    Subsequent calls to get_logger() simply retrieve a child logger that
    inherits handlers from root — no duplicate handlers are created.
    """
    root = logging.getLogger()

    # Avoid re-configuring if already set up (e.g., in a testing context)
    if root.handlers:
        return

    root.setLevel(logging.DEBUG)  # handlers control the effective level

    formatter = logging.Formatter(fmt=_LOG_FMT, datefmt=_DATE_FMT)
    sensitive_filter = SensitiveDataFilter()

    # ---- Console handler (INFO+) --------------------------------------- #
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)

    # ---- Rotating file handler (DEBUG+) -------------------------------- #
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        filename=_LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,   # defer file creation until the first record is emitted
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(sensitive_filter)

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Silence overly verbose third-party loggers at WARNING+
    for noisy_lib in ("httpx", "httpcore", "urllib3", "celery", "kombu"):
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)


# Run once on first import
_configure_root_logger()


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger that inherits the root logger's handlers.

    Usage::

        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Webhook received", extra={"incident_id": incident_id})

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A :class:`logging.Logger` pre-configured with structured formatting
        and sensitive-data redaction.
    """
    return logging.getLogger(name)
