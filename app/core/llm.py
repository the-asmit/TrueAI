"""
LLM client factory and call wrapper for TrueAI ? Anthropic Claude only.

Design decisions
----------------
- Singleton pattern via module-level cache: the ChatAnthropic object is
  constructed once and reused across all requests in the same process.
  This avoids redundant validation and HTTP-client initialisation on every
  call while remaining safe for multi-threaded use (construction is
  idempotent and GIL-protected at the assignment step).
- temperature=0: deterministic outputs are critical for code-patch
  generation; we never want creative drift between retry attempts.
- max_tokens=8192: generous ceiling that accommodates large diff outputs
  without surprising truncation mid-patch.
- streaming=False by default; individual nodes may override per-invocation
  via .stream() or astream() if incremental output is needed.

Retry strategy (call_llm_with_retry)
-------------------------------------
Wraps every Anthropic API call with a tenacity retry policy so nodes do
not need to implement their own backoff logic.

Retried errors:
  - anthropic.RateLimitError      (HTTP 429)
  - anthropic.APIStatusError      *only* when HTTP status is 502, 503, or 529

NOT retried (fail immediately):
  - anthropic.AuthenticationError ? bad key, nothing a retry can fix
  - anthropic.BadRequestError     ? malformed request, caller bug

Backoff:  exponential  min=2 s  max=60 s  multiplier=2
Attempts: 4  (1 original + 3 retries)

After all attempts: raises anthropic.APIConnectionError with a clear
message so the Celery task can surface it correctly.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

import anthropic
from langchain_anthropic import ChatAnthropic
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

_MODEL_ID: str = "claude-sonnet-4-5"
_llm_instance: Optional[ChatAnthropic] = None
_llm_lock: threading.Lock = threading.Lock()

# ------------------------------------------------------------------ #
# Retry predicate                                                      #
# ------------------------------------------------------------------ #

# HTTP status codes that are transient and worth retrying.
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({502, 503, 529})

# Exceptions that represent permanent caller errors ? retrying cannot help.
_NON_RETRYABLE_TYPES: tuple[type[BaseException], ...] = (
    anthropic.AuthenticationError,
    anthropic.BadRequestError,
)


def _is_retryable(exc: BaseException) -> bool:
    """
    Return True if *exc* is a transient Anthropic API error worth retrying.

    Logic:
    - Never retry AuthenticationError or BadRequestError (permanent).
    - Always retry RateLimitError (HTTP 429).
    - Retry APIStatusError only for status codes 502, 503, 529.
    - Do not retry any other exception type (e.g. network timeouts are
      handled by the underlying httpx client; unexpected exceptions should
      surface immediately to the caller for diagnosis).
    """
    if isinstance(exc, _NON_RETRYABLE_TYPES):
        return False

    if isinstance(exc, anthropic.RateLimitError):
        return True

    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in _RETRYABLE_STATUS_CODES

    return False


# ------------------------------------------------------------------ #
# Async retry wrapper                                                  #
# ------------------------------------------------------------------ #


async def call_llm_with_retry(
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """
    Asynchronously invoke *fn* (an async Anthropic API call) with automatic
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
        anthropic.AuthenticationError: Immediately (not retried).
        anthropic.BadRequestError:     Immediately (not retried).
        anthropic.APIConnectionError:  After all retry attempts are
            exhausted, with message "Anthropic API unavailable after retries".
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
            "call_llm_with_retry: non-retryable Anthropic error (type=%s) — "
            "aborting immediately.",
            type(fn).__name__,   # fn type, not exc, to stay credential-safe
        )
        raise
    except Exception as exc:
        # tenacity exhausted all attempts — wrap in APIConnectionError so
        # the Celery task and callers have a single predictable type to handle.
        logger.error(
            "call_llm_with_retry: all retry attempts exhausted "
            "(last_error_type=%s) — raising APIConnectionError.",
            type(exc).__name__,
        )
        raise anthropic.APIConnectionError(
            request=None,  # type: ignore[arg-type]
            message="Anthropic API unavailable after retries",
        ) from exc


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def get_llm() -> ChatAnthropic:
    """
    Return the shared, pre-configured :class:`ChatAnthropic` instance.

    The instance is constructed lazily on the first call and cached for all
    subsequent calls.  Thread-safe via a module-level lock.

    Raises:
        RuntimeError: If ``ANTHROPIC_API_KEY`` is not configured in the
            environment.  The error message is intentionally descriptive so
            that on-call engineers can resolve the issue without digging
            through source code.

    Returns:
        A :class:`ChatAnthropic` LLM ready for use inside LangChain chains
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
            "Initialising Anthropic LLM client (model=%s).", _MODEL_ID
        )

        _llm_instance = ChatAnthropic(
            model=_MODEL_ID,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0,
            max_tokens=8192,
            # Disable the SDK's own retry layer: tenacity's call_llm_with_retry
            # is the single retry boundary.  Stacking two retry strategies
            # would cause silent over-retry against rate-limit quotas.
            max_retries=0,
            timeout=120,          # seconds ? long enough for a full diff generation
            streaming=False,
        )

        logger.info("Anthropic LLM client ready.")

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
    Raise a clear :class:`RuntimeError` if the Anthropic API key is absent
    or obviously malformed, so the service fails fast at startup rather than
    producing cryptic 401 errors mid-request.
    """
    key = settings.ANTHROPIC_API_KEY

    if not key or not key.strip():
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env file or environment before starting the service.\n"
            "  Example:  ANTHROPIC_API_KEY=sk-ant-..."
        )

    # Anthropic keys start with "sk-ant-"; warn (don't hard-fail) if the
    # format is unexpected ? it may be a proxy key with a different prefix.
    if not key.startswith("sk-ant-"):
        logger.warning(
            "ANTHROPIC_API_KEY does not start with 'sk-ant-'. "
            "Proceeding anyway ? this is expected if you are routing through a proxy."
        )
