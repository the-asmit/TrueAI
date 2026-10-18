"""
Base class shared by every TrueAI agent.

An agent is a small, single-purpose unit with:

    name            key used for model routing (``AGENT_<NAME>_*`` settings)
    title           human-readable name shown on the dashboard timeline
    system_prompt   the agent's role and rules
    build_prompt()  turns pipeline inputs into the user message
    parse()         turns the model's reply into a typed, validated output

``run()`` resolves the agent's own model, calls it, and parses the reply.
If the reply does not follow the required format, the agent gets ONE repair
turn: the parse error is sent back so the model can correct itself.  A
second failure raises :class:`AgentOutputError`.

Structured output uses XML-style tags rather than JSON: code snippets inside
JSON strings need escaping that models frequently get wrong, while tagged
blocks carry code verbatim.  Untrusted text in prompts is fenced with
``fence_untrusted`` so it cannot impersonate these tags.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, List, Optional, Sequence, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.errors import AgentOutputError
from app.core.llm import ModelSpec, invoke_llm, resolve_model_spec
from app.core.logging import get_logger
from app.core.security import UNTRUSTED_DATA_NOTICE

logger = get_logger(__name__)

OutputT = TypeVar("OutputT")

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass
class AgentResult(Generic[OutputT]):
    """A parsed agent output plus the metadata recorded on the timeline."""

    output: OutputT
    spec: ModelSpec
    input_tokens: int
    output_tokens: int
    duration_ms: int
    attempts: int


class BaseAgent(ABC, Generic[OutputT]):
    name: str = ""
    title: str = ""
    system_prompt: str = ""

    @abstractmethod
    def build_prompt(self, **inputs: Any) -> str:
        """Return the user message for this run."""

    @abstractmethod
    def parse(self, text: str) -> OutputT:
        """Parse the model reply; raise AgentOutputError describing what is wrong."""

    async def run(self, **inputs: Any) -> AgentResult[OutputT]:
        spec = resolve_model_spec(self.name)
        messages: List[BaseMessage] = [
            SystemMessage(content=f"{self.system_prompt.strip()}\n\n{UNTRUSTED_DATA_NOTICE}"),
            HumanMessage(content=self.build_prompt(**inputs)),
        ]
        input_tokens = output_tokens = duration_ms = 0

        for attempt in (1, 2):
            response = await invoke_llm(spec, messages)
            spec = response.spec  # may be the fallback model
            input_tokens += response.input_tokens
            output_tokens += response.output_tokens
            duration_ms += response.duration_ms
            try:
                output = self.parse(strip_reasoning(response.text))
            except AgentOutputError as exc:
                if attempt == 2:
                    raise AgentOutputError(f"The AI model's reply could not be used: {exc}") from exc
                logger.info("%s reply did not parse (%s) — asking it to correct the format.", self.title, exc)
                hint = "Your reply was cut off because it was too long; be more concise. " if response.truncated else ""
                messages += [
                    AIMessage(content=response.text[:6000]),
                    HumanMessage(
                        content=(
                            f"Your previous reply could not be used: {exc}\n{hint}"
                            "Reply again with the complete answer in exactly the required tag format."
                        )
                    ),
                ]
                continue
            return AgentResult(
                output=output,
                spec=spec,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_ms=duration_ms,
                attempts=attempt,
            )
        raise AssertionError("unreachable")  # pragma: no cover


# ================================================================== #
# Tag parsing helpers                                                  #
# ================================================================== #

def strip_reasoning(text: str) -> str:
    """Drop <think> blocks emitted by reasoning models before parsing."""
    return _THINK_BLOCK_RE.sub("", text or "")


def tag(text: str, name: str) -> Optional[str]:
    """Inner text of the first ``<name>…</name>`` block, or None."""
    match = re.search(rf"<{name}>(.*?)</{name}>", text, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else None


def tags(text: str, name: str) -> List[str]:
    return re.findall(rf"<{name}>(.*?)</{name}>", text, re.DOTALL | re.IGNORECASE)


_ODD_SPACES_RE = re.compile(r"[      　]")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


def clean_prose(value: str) -> str:
    """
    Normalise model prose for display: exotic Unicode spaces → normal spaces,
    HTML line breaks → newlines.  Never used on code fields, which must stay
    byte-exact.
    """
    value = _ODD_SPACES_RE.sub(" ", value)
    value = _BR_RE.sub("\n", value)
    return value.strip()


def required_text(text: str, name: str, *, max_len: int = 4000) -> str:
    value = clean_prose(tag(text, name) or "")
    if not value:
        raise AgentOutputError(f"the <{name}> tag is missing or empty")
    return value[:max_len]


def optional_text(text: str, name: str, *, max_len: int = 4000) -> Optional[str]:
    value = clean_prose(tag(text, name) or "")
    if not value or value.lower() in ("none", "n/a", "null", "-"):
        return None
    return value[:max_len]


def required_choice(text: str, name: str, choices: Sequence[str]) -> str:
    raw = required_text(text, name).lower()
    cleaned = re.sub(r"[^a-z_]", "", raw.replace("-", "_").replace(" ", "_"))
    if cleaned not in choices:
        raise AgentOutputError(f"<{name}> must be one of {', '.join(choices)} (got '{raw[:40]}')")
    return cleaned


def required_float(text: str, name: str) -> float:
    raw = required_text(text, name)
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        raise AgentOutputError(f"<{name}> must be a number between 0 and 1 (got '{raw[:40]}')")
    value = float(match.group(0))
    if 1.0 < value <= 100.0:
        value = value / 100.0  # the model answered on a 0–100 scale ("85" or "85%")
    return max(0.0, min(1.0, value))


def required_bool(text: str, name: str) -> bool:
    raw = required_text(text, name).lower()
    if raw.startswith(("true", "yes", "1")):
        return True
    if raw.startswith(("false", "no", "0")):
        return False
    raise AgentOutputError(f"<{name}> must be true or false (got '{raw[:40]}')")


def list_items(text: str, container: str, item: str, *, max_items: int = 12, max_len: int = 600) -> List[str]:
    block = tag(text, container)
    if block is None:
        return []
    block = clean_prose(block)
    items = [entry.strip() for entry in tags(block, item) if entry.strip()]
    if not items:
        # Tolerate a plain bulleted/numbered list inside the container.
        items = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip() for line in block.splitlines()]
        items = [entry for entry in items if entry and entry.lower() not in ("none", "n/a")]
    return [entry[:max_len] for entry in items[:max_items]]
