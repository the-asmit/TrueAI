"""
LLM model registry and resilient invocation for TrueAI's agents.

Per-agent models
────────────────
Each agent asks for its model by name (``resolve_model_spec("reviewer")``).
The spec comes from ``AGENT_<NAME>_*`` settings and falls back to the global
``LLM_*`` settings, so today every agent can share one model and tomorrow the
Fix Engineer can run on a different provider without touching agent code.

Supported providers: ``groq`` (default), ``openai`` (also any OpenAI-compatible
endpoint via ``OPENAI_BASE_URL``) and ``anthropic`` (requires the optional
``langchain-anthropic`` package).

Retries
───────
Only transient failures are retried — rate limits (honouring
``Retry-After``), timeouts, connection errors and 5xx.  Authentication and
bad-request errors fail immediately.  When retries are exhausted and a
fallback model is configured (``LLM_FALLBACK_*``) it is tried once.

Client caching
──────────────
Provider SDKs keep async HTTP connection pools bound to the event loop that
created them.  Chat model instances are therefore cached per (event loop,
spec) — reusing one across loops fails with "Event loop is closed".
"""

from __future__ import annotations

import asyncio
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from app.core.config import AGENT_NAMES, settings
from app.core.errors import ConfigurationError, LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    provider: str
    model: str
    temperature: float
    max_tokens: int

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class LLMResponse:
    text: str
    spec: ModelSpec
    input_tokens: int
    output_tokens: int
    duration_ms: int
    truncated: bool = False  # the model hit max_tokens before finishing


# ================================================================== #
# Model resolution                                                     #
# ================================================================== #

def resolve_model_spec(agent_name: str) -> ModelSpec:
    """Return the model spec for *agent_name* (per-agent override → global default)."""
    if agent_name not in AGENT_NAMES:
        raise ConfigurationError(f"Unknown agent '{agent_name}'.")
    prefix = f"AGENT_{agent_name.upper()}_"
    provider = getattr(settings, prefix + "PROVIDER") or settings.LLM_PROVIDER
    model = getattr(settings, prefix + "MODEL") or (
        settings.LLM_MODEL if provider == settings.LLM_PROVIDER else None
    )
    if not model:
        raise ConfigurationError(f"{prefix}MODEL must be set when {prefix}PROVIDER differs from LLM_PROVIDER.")
    temperature = getattr(settings, prefix + "TEMPERATURE")
    max_tokens = getattr(settings, prefix + "MAX_TOKENS")
    return ModelSpec(
        provider=provider,
        model=model,
        temperature=settings.LLM_TEMPERATURE if temperature is None else float(temperature),
        max_tokens=settings.LLM_MAX_TOKENS if max_tokens is None else int(max_tokens),
    )


def fallback_spec(primary: ModelSpec) -> Optional[ModelSpec]:
    if not settings.LLM_FALLBACK_MODEL:
        return None
    spec = ModelSpec(
        provider=settings.LLM_FALLBACK_PROVIDER or primary.provider,
        model=settings.LLM_FALLBACK_MODEL,
        temperature=primary.temperature,
        max_tokens=primary.max_tokens,
    )
    return None if spec == primary else spec


def configured_agents() -> Dict[str, str]:
    """``{agent: "provider:model"}`` — shown on the dashboard and logged at startup."""
    return {name: resolve_model_spec(name).label for name in AGENT_NAMES}


def validate_llm_configuration() -> None:
    """Fail fast at startup when an agent's provider has no API key or package."""
    for name in AGENT_NAMES:
        _check_provider_ready(resolve_model_spec(name).provider)
    if settings.LLM_FALLBACK_MODEL:
        _check_provider_ready(settings.LLM_FALLBACK_PROVIDER or settings.LLM_PROVIDER)


def _check_provider_ready(provider: str) -> None:
    key_setting = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}[provider]
    if not settings.secret(key_setting) and not (provider == "openai" and settings.OPENAI_BASE_URL):
        raise ConfigurationError(f"{key_setting} is required because an agent uses the '{provider}' provider.")
    if provider == "anthropic":
        try:
            import langchain_anthropic  # noqa: F401
        except ImportError as exc:
            raise ConfigurationError("Install 'langchain-anthropic' to use the anthropic provider.") from exc


# ================================================================== #
# Client construction (cached per event loop)                          #
# ================================================================== #

_models: Dict[Tuple[int, ModelSpec], BaseChatModel] = {}
_models_lock = threading.Lock()


def get_chat_model(spec: ModelSpec) -> BaseChatModel:
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = 0
    cache_key = (loop_id, spec)
    with _models_lock:
        model = _models.get(cache_key)
        if model is None:
            if len(_models) >= 64:  # entries for finished event loops are dead weight
                _models.clear()
            model = _build_model(spec)
            _models[cache_key] = model
    return model


def reset_models() -> None:
    with _models_lock:
        _models.clear()


def _build_model(spec: ModelSpec) -> BaseChatModel:
    _check_provider_ready(spec.provider)
    timeout = settings.LLM_TIMEOUT_SECONDS
    if spec.provider == "groq":
        from langchain_groq import ChatGroq

        groq_kwargs: Dict[str, Any] = {}
        if settings.LLM_REASONING_EFFORT and spec.model.startswith("openai/gpt-oss"):
            groq_kwargs["reasoning_effort"] = settings.LLM_REASONING_EFFORT
        return ChatGroq(
            model=spec.model,
            api_key=settings.secret("GROQ_API_KEY"),
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
            timeout=timeout,
            max_retries=0,  # retries are handled by invoke_llm
            **groq_kwargs,
        )
    if spec.provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: Dict[str, Any] = {}
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        return ChatOpenAI(
            model=spec.model,
            api_key=settings.secret("OPENAI_API_KEY") or "not-needed",
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
            timeout=timeout,
            max_retries=0,
            **kwargs,
        )
    if spec.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic  # type: ignore[import-not-found]

        return ChatAnthropic(
            model=spec.model,
            api_key=settings.secret("ANTHROPIC_API_KEY"),
            temperature=spec.temperature,
            max_tokens=spec.max_tokens,
            timeout=timeout,
            max_retries=0,
        )
    raise ConfigurationError(f"Unsupported LLM provider '{spec.provider}'.")


# ================================================================== #
# Invocation                                                           #
# ================================================================== #

async def invoke_llm(spec: ModelSpec, messages: List[BaseMessage]) -> LLMResponse:
    """
    Call the model with retry on transient errors, then the fallback model.

    Raises:
        LLMError: ``retryable=True`` when the provider stayed unavailable,
            ``retryable=False`` for permanent errors (auth, bad request).
    """
    try:
        return await _invoke_with_retry(spec, messages)
    except LLMError as primary_error:
        backup = fallback_spec(spec)
        if backup is None:
            raise
        logger.warning("LLM %s failed (%s) — trying fallback %s.", spec.label, primary_error, backup.label)
        return await _invoke_with_retry(backup, messages)


async def _invoke_with_retry(spec: ModelSpec, messages: List[BaseMessage]) -> LLMResponse:
    attempts = settings.LLM_MAX_ATTEMPTS
    last_error: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            model = get_chat_model(spec)
            response = await asyncio.wait_for(model.ainvoke(messages), timeout=settings.LLM_TIMEOUT_SECONDS + 5)
        except ConfigurationError:
            raise
        except Exception as exc:  # classify below
            last_error = exc
            retryable, wait_hint = _classify(exc)
            if not retryable:
                raise LLMError(f"The AI model rejected the request ({_describe(exc)})", retryable=False) from exc
            if attempt == attempts:
                break
            delay = _backoff(attempt, wait_hint)
            logger.info(
                "LLM %s transient error (%s) — attempt %d/%d, retrying in %.1fs.",
                spec.label, _describe(exc), attempt, attempts, delay,
            )
            await asyncio.sleep(delay)
            continue

        usage = getattr(response, "usage_metadata", None) or {}
        metadata = getattr(response, "response_metadata", None) or {}
        finish = str(metadata.get("finish_reason") or metadata.get("stop_reason") or "").lower()
        return LLMResponse(
            text=_content_text(response.content),
            spec=spec,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            duration_ms=int((time.perf_counter() - started) * 1000),
            truncated=finish in ("length", "max_tokens"),
        )

    raise LLMError(
        f"The AI model is unavailable right now ({_describe(last_error)})", retryable=True
    ) from last_error


def check_models_available() -> List[str]:
    """
    Ask each provider which models this API key can use and return a warning
    for every configured model that is not available (e.g. retired by the
    provider).  Network problems are reported but never raise.
    """
    import httpx

    wanted: Dict[str, set] = {}
    for name in AGENT_NAMES:
        spec = resolve_model_spec(name)
        wanted.setdefault(spec.provider, set()).add(spec.model)
    if settings.LLM_FALLBACK_MODEL:
        wanted.setdefault(settings.LLM_FALLBACK_PROVIDER or settings.LLM_PROVIDER, set()).add(settings.LLM_FALLBACK_MODEL)

    endpoints = {
        "groq": ("https://api.groq.com/openai/v1/models", settings.secret("GROQ_API_KEY")),
        "openai": (f"{(settings.OPENAI_BASE_URL or 'https://api.openai.com/v1').rstrip('/')}/models", settings.secret("OPENAI_API_KEY")),
    }
    warnings: List[str] = []
    for provider, models in wanted.items():
        if provider not in endpoints:
            continue
        url, key = endpoints[provider]
        try:
            response = httpx.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=10)
            response.raise_for_status()
            available = {item.get("id") for item in response.json().get("data", [])}
        except Exception as exc:
            warnings.append(f"Could not list {provider} models ({type(exc).__name__}); skipped availability check.")
            continue
        for model in sorted(models - available):
            warnings.append(f"Model '{model}' is not available to your {provider} API key (retired or no access).")
    return warnings


def _content_text(content: Any) -> str:
    """Providers return either a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content or "")


def _classify(exc: BaseException) -> Tuple[bool, Optional[float]]:
    """Return ``(retryable, retry_after_seconds)`` for a provider exception."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True, None
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if isinstance(status, int):
        if status in (408, 409, 425, 429) or status >= 500:
            return True, _retry_after(exc)
        return False, None
    name = type(exc).__name__.lower()
    if any(word in name for word in ("timeout", "connection", "ratelimit", "overloaded", "unavailable", "internalserver")):
        return True, _retry_after(exc)
    return False, None


def _retry_after(exc: BaseException) -> Optional[float]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _backoff(attempt: int, hint: Optional[float]) -> float:
    exponential = min(30.0, 2.0 ** attempt) + random.uniform(0, 1)
    return min(60.0, max(exponential, hint or 0.0))


def _describe(exc: Optional[BaseException]) -> str:
    if exc is None:
        return "unknown error"
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}{f' (HTTP {status})' if status else ''}"
