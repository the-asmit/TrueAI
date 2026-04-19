"""
LLM client factory for TrueAI — Anthropic Claude only.

Design decisions:
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
"""

import threading
from typing import Optional

from langchain_anthropic import ChatAnthropic

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
        or LangGraph nodes.
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
            # Retry behaviour: langchain-anthropic wraps the SDK's built-in
            # retry logic; we keep the default 2 retries with exponential
            # back-off to handle transient 529 / rate-limit responses.
            max_retries=2,
            timeout=120,          # seconds — long enough for a full diff generation
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
    # format is unexpected — it may be a proxy key with a different prefix.
    if not key.startswith("sk-ant-"):
        logger.warning(
            "ANTHROPIC_API_KEY does not start with 'sk-ant-'. "
            "Proceeding anyway — this is expected if you are routing through a proxy."
        )
