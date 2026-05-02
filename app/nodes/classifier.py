"""
Classifier node — uses Claude to categorise the incident type.

The classifier is the ONLY node that is allowed to default to a fallback value
instead of failing the pipeline.  Classification is a soft signal used to
guide downstream nodes; an incorrect or defaulted classification degrades
output quality but does not block analysis.

Classification categories:
    code_bug       — logic errors, type errors, uncaught exceptions, NPE
    config_issue   — misconfiguration, wrong environment variables, bad settings
    infrastructure — server outages, OOM kills, network timeouts, disk full
    data_issue     — database integrity errors, unexpected NULL, corrupt data
    dependency     — third-party library errors, version conflicts, API failures

Parsing rules (strictly enforced):
    Use re.search() with DOTALL flag.
    If <classification> tag is absent OR its content is empty → default to
    "code_bug" and log a WARNING.  Never crash.
    If the extracted value is not one of the five categories → default and warn.
"""

from __future__ import annotations

import re
from typing import Final

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import call_llm_with_retry, get_llm
from app.core.logging import get_logger
from app.core.state import IncidentState, ISSUE_CLASSIFICATIONS

logger = get_logger(__name__)

_DEFAULT_CLASSIFICATION: Final[str] = "code_bug"

_SYSTEM_PROMPT: Final[str] = (
    "You are an expert site reliability engineer who specialises in classifying "
    "production software incidents. You always respond with the exact XML format "
    "requested — never add prose outside the XML tags."
)


async def classifier_node(state: IncidentState) -> IncidentState:
    """
    Classify the incident into one of the five issue categories.

    Reads:
        error_type, error_message, stack_frames, sentry_context

    Writes:
        issue_classification

    Never writes error / status = "failed".  On any failure (LLM error,
    parse failure, invalid category) defaults to "code_bug" and logs WARNING.
    """
    state = {**state}
    incident_id = state.get("incident_id", "unknown")
    logger.debug("classifier_node ENTRY | incident_id=%s", incident_id)

    try:
        prompt = _build_prompt(state)
        llm = get_llm()
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = await call_llm_with_retry(llm.ainvoke, messages)
        response_text: str = response.content or ""

        classification = _parse_classification(response_text, incident_id)
        state["issue_classification"] = classification

        logger.debug(
            "classifier_node EXIT | incident_id=%s | classification=%s",
            incident_id,
            classification,
        )
        return state

    except Exception as exc:
        # Classifier is the ONLY node allowed to default instead of failing.
        logger.warning(
            "classifier_node EXCEPTION (defaulting to '%s') | "
            "incident_id=%s | error=%s — %s",
            _DEFAULT_CLASSIFICATION,
            incident_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        state["issue_classification"] = _DEFAULT_CLASSIFICATION
        return state


# ------------------------------------------------------------------ #
# Prompt builder                                                       #
# ------------------------------------------------------------------ #

def _build_prompt(state: IncidentState) -> str:
    error_type = state.get("error_type", "Unknown")
    error_message = state.get("error_message", "")
    stack_frames = state.get("stack_frames") or []
    sentry_context = state.get("sentry_context") or {}

    # Summarise top 5 frames for the prompt (avoid token overuse)
    frame_summary_lines = []
    for frame in stack_frames[-5:]:
        fname = frame.get("filename", "?")
        lineno = frame.get("lineno", "?")
        func = frame.get("function", "?")
        ctx = frame.get("context_line", "").strip()
        frame_summary_lines.append(f"  {fname}:{lineno} in {func}() → {ctx}")
    frame_summary = "\n".join(frame_summary_lines) or "  (no frames)"

    environment = sentry_context.get("environment", "unknown")
    platform = sentry_context.get("platform", "unknown")

    return f"""Classify this production incident into exactly one category.

CATEGORIES (choose one):
  code_bug       — logic errors, type errors, uncaught exceptions, assertion failures
  config_issue   — misconfiguration, missing/wrong env variables, bad settings files
  infrastructure — server outages, OOM kills, network timeouts, disk full, CPU throttle
  data_issue     — database integrity errors, unexpected NULL, malformed/corrupt data
  dependency     — third-party library errors, version conflicts, external API failures

INCIDENT DETAILS:
  Error Type    : {error_type}
  Error Message : {error_message}
  Environment   : {environment}
  Platform      : {platform}

STACK FRAMES (innermost last):
{frame_summary}

Respond with EXACTLY this XML — no other text:
<classification>one of: code_bug | config_issue | infrastructure | data_issue | dependency</classification>
<reasoning>one sentence explaining why</reasoning>"""


# ------------------------------------------------------------------ #
# Parser                                                               #
# ------------------------------------------------------------------ #

def _parse_classification(response_text: str, incident_id: str) -> str:
    """
    Extract and validate the <classification> tag from LLM output.

    Returns the valid category string, or _DEFAULT_CLASSIFICATION with a
    WARNING log if the tag is absent, empty, or contains an unrecognised value.
    """
    match = re.search(r"<classification>(.*?)</classification>", response_text, re.DOTALL)

    if match is None:
        logger.warning(
            "classifier_node: <classification> tag not found in LLM response | "
            "incident_id=%s — defaulting to '%s'",
            incident_id,
            _DEFAULT_CLASSIFICATION,
        )
        return _DEFAULT_CLASSIFICATION

    extracted = match.group(1).strip().lower()

    if not extracted:
        logger.warning(
            "classifier_node: <classification> tag is empty | "
            "incident_id=%s — defaulting to '%s'",
            incident_id,
            _DEFAULT_CLASSIFICATION,
        )
        return _DEFAULT_CLASSIFICATION

    # Strip surrounding punctuation/whitespace the LLM may have added
    # (e.g. "code_bug." or "**code_bug**")
    cleaned = re.sub(r"[^a-z_]", "", extracted)

    if cleaned not in ISSUE_CLASSIFICATIONS:
        logger.warning(
            "classifier_node: extracted classification '%s' (cleaned: '%s') "
            "is not valid | incident_id=%s — defaulting to '%s'",
            extracted,
            cleaned,
            incident_id,
            _DEFAULT_CLASSIFICATION,
        )
        return _DEFAULT_CLASSIFICATION

    return cleaned
