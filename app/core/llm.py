"""
LLM client factory and call wrapper for TrueAI — Groq only.

Design decisions
----------------
- Singleton pattern via module-level cache: the ChatGroq object is
  constructed once and reused across all requests in the same process.
  This avoids redundant validation and HTTP-client initialisation on every
  call while remaining safe for multi-threaded use (construction is
  idempotent and GIL-protected at the assignment step).
- temperature=0.2: low but non-zero; Groq inference is fast enough that
  a small amount of variance does not hurt latency meaningfully.
- streaming=False by default; individual nodes may override per-invocation
  via .stream() or astream() if incremental output is needed.

Retry strategy (call_llm_with_retry)
-------------------------------------
Wraps every Groq API call with a tenacity retry policy so nodes do
not need to implement their own backoff logic.

Retried errors:
  - Any transient exception (network errors, 429 rate limits, 502/503/529
    upstream errors) — detected via _is_retryable().

NOT retried (fail immediately):
  - ValueError / TypeError — caller bug in request construction.

Backoff:  exponential  min=2 s  max=60 s  multiplier=2
Attempts: 4  (1 original + 3 retries)

After all attempts: raises RuntimeError with a clear message so the
Celery task can surface it correctly.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from langchain_groq import ChatGroq
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------ #
# Module-level singleton state                                         #
# ------------------------------------------------------------------ #

_MODEL_ID: str = "llama-3.3-70b-versatile"
_llm_instance: Optional[ChatGroq] = None
_llm_lock: threading.Lock = threading.Lock()

# ------------------------------------------------------------------ #
# Retry predicate                                                      #
# ------------------------------------------------------------------ #

# Exception types that represent permanent caller errors — retrying cannot help.
_NON_RETRYABLE_TYPES: tuple[type[BaseException], ...] = (
    ValueError,
    TypeError,
)


def _is_retryable(exc: BaseException) -> bool:
    """
    Return True if *exc* is a transient Groq API error worth retrying.

    Logic:
    - Never retry ValueError or TypeError (permanent caller bugs).
    - Retry everything else (network timeouts, rate limits, upstream 5xx).
    """
    if isinstance(exc, _NON_RETRYABLE_TYPES):
        return False
    return True


# ------------------------------------------------------------------ #
# Async retry wrapper                                                  #
# ------------------------------------------------------------------ #


async def call_llm_with_retry(
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Asynchronously invoke *fn* (an async Groq API call) with automatic
    retry/backoff on transient failures.

    This is the single retry boundary for all LLM calls in TrueAI.
    Nodes call this wrapper instead of awaiting the LLM directly::

        from app.core.llm import call_llm_with_retry, get_llm

        result = await call_llm_with_retry(get_llm().ainvoke, messages)

    Uses tenacity's ``AsyncRetrying`` so that the retry loop itself runs
    inside the async event loop — compatible with LangChain's ``ainvoke``
    and any other async coroutine function.

    Each retry is logged at INFO level (attempt number, wait seconds, error
    type) via ``before_sleep_log``.  No API keys, tokens, or request bodies
    are ever logged.

    Args:
        fn:       Async callable to invoke (e.g. ``llm.ainvoke``).
        *args:    Positional arguments forwarded to *fn*.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        Whatever *fn* returns (awaited) on success.

    Raises:
        ValueError: Immediately (not retried) — caller bug.
        TypeError:  Immediately (not retried) — caller bug.
        RuntimeError: After all retry attempts are exhausted, with message
            "Groq API unavailable after retries".
    """
    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_retryable),
            stop=stop_after_attempt(4),               # 1 original + 3 retries
            wait=wait_exponential(multiplier=1, min=2, max=60),
            before_sleep=before_sleep_log(logger, 20),  # logging.INFO == 20
            reraise=False,   # we intercept exhaustion in the except below
        ):
            with attempt:
                return await fn(*args, **kwargs)
    except _NON_RETRYABLE_TYPES:
        # Permanent caller error — log without exposing credentials, re-raise.
        logger.error(
            "call_llm_with_retry: non-retryable error (type=%s) — "
            "aborting immediately.",
            type(fn).__name__,   # fn type, not exc, to stay credential-safe
        )
        raise
    except Exception as exc:
        # tenacity exhausted all attempts — wrap in RuntimeError so
        # the Celery task and callers have a single predictable type to handle.
        logger.error(
            "call_llm_with_retry: all retry attempts exhausted "
            "(last_error_type=%s) — raising RuntimeError.",
            type(exc).__name__,
        )
        raise RuntimeError("Groq API unavailable after retries") from exc


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def get_llm() -> ChatGroq:
    """
    Return the shared, pre-configured :class:`ChatGroq` instance.

    The instance is constructed lazily on the first call and cached for all
    subsequent calls.  Thread-safe via a module-level lock.

    Raises:
        RuntimeError: If ``GROQ_API_KEY`` is not configured in the
            environment.  The error message is intentionally descriptive so
            that on-call engineers can resolve the issue without digging
            through source code.

    Returns:
        A :class:`ChatGroq` LLM ready for use inside LangChain chains
        or LangGraph nodes.  Wrap invocations with
        :func:`call_llm_with_retry` for production-grade resilience.
    """
    global _llm_instance

    if _llm_instance is not None:
        return _llm_instance

    with _llm_lock:
        # Double-checked locking: re-test inside the lock to handle the race
        # where two threads both saw _llm_instance as None.
        if _llm_instance is not None:
            return _llm_instance

        _validate_api_key()

        logger.info(
            "Initialising Groq LLM client (model=%s).", _MODEL_ID
        )

        _llm_instance = ChatGroq(
            model=_MODEL_ID,
            api_key=settings.GROQ_API_KEY,
            temperature=0.2,
        )

        logger.info("Groq LLM client ready.")

    return _llm_instance


def reset_llm() -> None:
    """
    Discard the cached LLM instance so the next :func:`get_llm` call
    constructs a fresh one.

    Intended for use in tests where the API key or model must be swapped
    between test cases.
    """
    global _llm_instance
    with _llm_lock:
        _llm_instance = None
    logger.debug("LLM instance cache cleared.")


# ------------------------------------------------------------------ #
# Internal helpers                                                     #
# ------------------------------------------------------------------ #

def _validate_api_key() -> None:
    """
    Raise a clear :class:`RuntimeError` if the Groq API key is absent
    or obviously malformed, so the service fails fast at startup rather than
    producing cryptic 401 errors mid-request.
    """
    key = settings.GROQ_API_KEY

    if not key or not key.strip():
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment before starting the service.\n"
            "  Example:  GROQ_API_KEY=gsk_..."
        )

    # Groq keys start with "gsk_"; warn (don't hard-fail) if the
    # format is unexpected — it may be a proxy key with a different prefix.
    if not key.startswith("gsk_"):
        logger.warning(
            "GROQ_API_KEY does not start with 'gsk_'. "
            "Proceeding anyway — this is expected if you are routing through a proxy."
        )
