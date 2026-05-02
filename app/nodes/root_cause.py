"""
Root-cause analysis node — uses Claude to identify WHY an error occurred.

This node builds a rich, structured prompt that includes every piece of
evidence gathered so far: error details, parsed stack frames, Sentry event
context, and the fetched GitHub source files.  Claude responds with three
XML-tagged fields that the pipeline carries forward.

Parsing rules (strictly enforced per project spec):
    Use re.search() with DOTALL flag.
    Validate EVERY extracted value individually after extraction:
        root_cause  : None or empty → status="failed", return full state
        explanation : None or empty → status="failed", return full state
        confidence  : cannot cast to float → status="failed", return full state
    NEVER best-guess or default any of these fields.

Low-confidence early exit:
    If confidence < CONFIDENCE_LOW_THRESHOLD (0.40) the fix is unlikely to
    be useful.  Set action = "flag_for_review" immediately so the decision
    node does not override this judgement.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import call_llm_with_retry, get_llm
from app.core.logging import get_logger
from app.core.state import IncidentState
from app.schemas.fix import CONFIDENCE_LOW_THRESHOLD

logger = get_logger(__name__)

_SYSTEM_PROMPT: str = (
    "You are a principal software engineer who specialises in post-mortem "
    "root-cause analysis.  You reason carefully from evidence and never guess. "
    "You always respond with the exact XML format requested — no prose outside "
    "the XML tags."
)


async def root_cause_node(state: IncidentState) -> IncidentState:
    """
    Perform LLM-based root-cause analysis using all available evidence.

    Reads:
        error_type, error_message, stack_frames, sentry_context,
        github_context, issue_classification

    Writes:
        root_cause, explanation, confidence
        action = "flag_for_review"  (when confidence < CONFIDENCE_LOW_THRESHOLD)

    On critical field parse failure writes:
        error, status = "failed"
    """
    state = {**state}
    incident_id = state.get("incident_id", "unknown")
    logger.debug("root_cause_node ENTRY | incident_id=%s", incident_id)

    try:
        prompt = _build_prompt(state)
        llm = get_llm()
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = await call_llm_with_retry(llm.ainvoke, messages)
        response_text: str = response.content or ""

        logger.debug(
            "root_cause_node: LLM responded | incident_id=%s | response_len=%d",
            incident_id,
            len(response_text),
        )

        # ---- Parse root_cause ---------------------------------------- #
        root_cause_match = re.search(
            r"<root_cause>(.*?)</root_cause>", response_text, re.DOTALL
        )
        root_cause = root_cause_match.group(1).strip() if root_cause_match else None

        if not root_cause:
            state["error"] = (
                "LLM response missing or empty <root_cause> tag. "
                "Cannot proceed without a root cause."
            )
            state["status"] = "failed"
            logger.error(
                "root_cause_node: missing <root_cause> | incident_id=%s | "
                "response_snippet=%s",
                incident_id,
                response_text[:300],
            )
            return state

        # ---- Parse explanation --------------------------------------- #
        explanation_match = re.search(
            r"<explanation>(.*?)</explanation>", response_text, re.DOTALL
        )
        explanation = explanation_match.group(1).strip() if explanation_match else None

        if not explanation:
            state["error"] = (
                "LLM response missing or empty <explanation> tag. "
                "Cannot proceed without an explanation."
            )
            state["status"] = "failed"
            logger.error(
                "root_cause_node: missing <explanation> | incident_id=%s",
                incident_id,
            )
            return state

        # ---- Parse confidence ---------------------------------------- #
        confidence_match = re.search(
            r"<confidence>(.*?)</confidence>", response_text, re.DOTALL
        )
        confidence_str = (
            confidence_match.group(1).strip() if confidence_match else None
        )

        try:
            confidence = float(confidence_str)
        except (TypeError, ValueError):
            state["error"] = (
                f"LLM returned non-numeric confidence value: {confidence_str!r}. "
                "Cannot proceed without a parseable confidence score."
            )
            state["status"] = "failed"
            logger.error(
                "root_cause_node: invalid confidence '%s' | incident_id=%s",
                confidence_str,
                incident_id,
            )
            return state

        # Clamp to [0.0, 1.0] — the LLM occasionally returns values like 0.82.
        confidence = max(0.0, min(1.0, confidence))

        # ---- Write results ------------------------------------------- #
        state["root_cause"] = root_cause
        state["explanation"] = explanation
        state["confidence"] = confidence

        # Early action decision for very low confidence
        if confidence < CONFIDENCE_LOW_THRESHOLD:
            state["action"] = "flag_for_review"
            logger.info(
                "root_cause_node: confidence=%.3f below threshold=%.2f — "
                "setting action=flag_for_review | incident_id=%s",
                confidence,
                CONFIDENCE_LOW_THRESHOLD,
                incident_id,
            )

        logger.debug(
            "root_cause_node EXIT | incident_id=%s | confidence=%.3f | "
            "root_cause_len=%d | explanation_len=%d",
            incident_id,
            confidence,
            len(root_cause),
            len(explanation),
        )
        return state

    except Exception as exc:
        state["error"] = (
            f"root_cause_node unhandled exception: {type(exc).__name__}: {exc}"
        )
        state["status"] = "failed"
        logger.error(
            "root_cause_node EXCEPTION | incident_id=%s | error=%s",
            incident_id,
            exc,
            exc_info=True,
        )
        return state


# ------------------------------------------------------------------ #
# Prompt builder                                                       #
# ------------------------------------------------------------------ #

def _build_prompt(state: IncidentState) -> str:
    error_type = state.get("error_type", "Unknown")
    error_message = state.get("error_message", "")
    classification = state.get("issue_classification", "unknown")
    stack_frames: List[Dict[str, Any]] = state.get("stack_frames") or []
    sentry_context: Dict[str, Any] = state.get("sentry_context") or {}
    github_context: Dict[str, str] = state.get("github_context") or {}

    frames_block = _format_stack_frames(stack_frames)
    context_block = _format_sentry_context(sentry_context)
    github_block = _format_github_context(github_context)

    return f"""You are analysing a production software incident.  Identify the root cause
with precision — do not speculate beyond the evidence provided.

═══════════════════════════════════════════════════════════════════════
INCIDENT SUMMARY
═══════════════════════════════════════════════════════════════════════
Error Type    : {error_type}
Error Message : {error_message}
Classification: {classification}

═══════════════════════════════════════════════════════════════════════
STACK FRAMES  (user-code frames only, innermost last)
═══════════════════════════════════════════════════════════════════════
{frames_block}

═══════════════════════════════════════════════════════════════════════
SENTRY EVENT CONTEXT
═══════════════════════════════════════════════════════════════════════
{context_block}

═══════════════════════════════════════════════════════════════════════
SOURCE CODE FROM GITHUB
═══════════════════════════════════════════════════════════════════════
{github_block}

═══════════════════════════════════════════════════════════════════════
INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════
Analyse ALL the evidence above.  Respond with EXACTLY this XML — no other text:

<root_cause>One concise technical sentence explaining the specific code path or condition that caused the error.</root_cause>
<explanation>A detailed, human-readable explanation of: (1) what went wrong, (2) why it went wrong, (3) what conditions triggered it. Write this as if for a PR description — clear enough for a junior engineer to understand.</explanation>
<confidence>A float between 0.00 and 1.00 representing your confidence in this analysis. Use 0.90+ only when the evidence is conclusive. Use 0.50-0.74 when you have a strong hypothesis but limited code context. Use below 0.40 when you are largely guessing.</confidence>"""


def _format_stack_frames(frames: List[Dict[str, Any]]) -> str:
    if not frames:
        return "  (no user-code frames available)"
    lines = []
    for i, frame in enumerate(frames, 1):
        fname = frame.get("filename") or "?"
        lineno = frame.get("lineno") or "?"
        func = frame.get("function") or "?"
        ctx = (frame.get("context_line") or "").strip()
        pre = frame.get("pre_context") or []
        post = frame.get("post_context") or []

        lines.append(f"Frame {i}: {fname}:{lineno} in {func}()")
        if pre:
            for pl in pre[-3:]:
                lines.append(f"    {pl}")
        if ctx:
            lines.append(f"  → {ctx}   ← error here")
        if post:
            for pl in post[:3]:
                lines.append(f"    {pl}")
        lines.append("")
    return "\n".join(lines)


def _format_sentry_context(ctx: Dict[str, Any]) -> str:
    lines = []
    for key in ("environment", "level", "platform", "release", "transaction", "server_name"):
        val = ctx.get(key)
        if val:
            lines.append(f"  {key}: {val}")
    tags = ctx.get("tags")
    if tags:
        lines.append(f"  tags: {tags}")
    user = ctx.get("user")
    if user:
        lines.append(f"  user: {user}")
    request = ctx.get("request")
    if request:
        lines.append(f"  request: {request}")
    return "\n".join(lines) if lines else "  (no Sentry context)"


def _format_github_context(github_ctx: Dict[str, str]) -> str:
    if not github_ctx:
        return "  (no source code fetched from GitHub)"
    blocks = []
    for file_path, content in github_ctx.items():
        blocks.append(f"=== {file_path} ===\n{content}\n=== end {file_path} ===")
    return "\n\n".join(blocks)
