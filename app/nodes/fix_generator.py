"""
Fix generator node — uses Claude to produce a unified-diff code patch.

Short-circuit rules (no LLM call):
    issue_classification == "config_issue"   → flag_for_review, no patch
    issue_classification == "infrastructure" → flag_for_review, no patch
    These categories require human intervention, not code changes.

Fixable categories (LLM is invoked):
    code_bug, data_issue, dependency

Parsing rules (strictly enforced per project spec):
    Use re.search() with DOTALL flag.
    Validate EVERY extracted value after extraction:
        fix_diff      : None or empty → status="failed", return full state
        files_changed : cannot be parsed as a list → status="failed", return full state
    NEVER best-guess or default missing fields.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import call_llm_with_retry, get_llm
from app.core.logging import get_logger
from app.core.state import IncidentState

logger = get_logger(__name__)

# Classifications that should never receive an automated code fix.
_UNFIXABLE_CLASSIFICATIONS = frozenset({"config_issue", "infrastructure"})

_SYSTEM_PROMPT: str = (
    "You are a principal software engineer who writes precise, minimal code fixes. "
    "You always output valid unified diff patches that apply cleanly with `git apply`. "
    "You respond with the exact XML format requested — no prose outside the XML tags."
)


async def fix_generator_node(state: IncidentState) -> IncidentState:
    """
    Generate a unified-diff code fix for the analysed incident.

    Reads:
        issue_classification, error_type, error_message, root_cause,
        explanation, stack_frames, github_context

    Writes (fixable path):
        fix_diff, files_changed

    Writes (unfixable path):
        fix_diff = "", action = "flag_for_review"
        explanation  (appends a note explaining why no fix was generated)

    On critical field parse failure writes:
        error, status = "failed"
    """
    state = {**state}
    incident_id = state.get("incident_id", "unknown")
    classification = state.get("issue_classification", "")
    logger.debug(
        "fix_generator_node ENTRY | incident_id=%s | classification=%s",
        incident_id,
        classification,
    )

    try:
        # ---- Short-circuit for unfixable categories ------------------- #
        if classification in _UNFIXABLE_CLASSIFICATIONS:
            reason = (
                f"Issue classified as '{classification}'. "
                "Automated code fixes are not appropriate for this category — "
                "human intervention is required to resolve configuration or "
                "infrastructure problems."
            )
            state["fix_diff"] = ""
            state["files_changed"] = []
            state["action"] = "flag_for_review"
            # Append the reason to explanation so reviewers understand why
            existing_explanation = state.get("explanation", "")
            state["explanation"] = (
                f"{existing_explanation}\n\n[No automated fix generated] {reason}"
                if existing_explanation
                else f"[No automated fix generated] {reason}"
            )
            logger.info(
                "fix_generator_node: skipping LLM call for classification='%s' | "
                "incident_id=%s",
                classification,
                incident_id,
            )
            return state

        # ---- LLM fix generation --------------------------------------- #
        prompt = _build_prompt(state)
        llm = get_llm()
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = await call_llm_with_retry(llm.ainvoke, messages)
        response_text: str = response.content or ""

        logger.debug(
            "fix_generator_node: LLM responded | incident_id=%s | response_len=%d",
            incident_id,
            len(response_text),
        )

        # ---- Parse fix_diff ------------------------------------------ #
        fix_diff_match = re.search(
            r"<fix_diff>(.*?)</fix_diff>", response_text, re.DOTALL
        )
        fix_diff = fix_diff_match.group(1).strip() if fix_diff_match else None

        if not fix_diff:
            state["error"] = (
                "LLM response missing or empty <fix_diff> tag. "
                "Cannot proceed without a patch."
            )
            state["status"] = "failed"
            logger.error(
                "fix_generator_node: missing <fix_diff> | incident_id=%s | "
                "response_snippet=%s",
                incident_id,
                response_text[:300],
            )
            return state

        # ---- Parse files_changed ------------------------------------- #
        files_changed_match = re.search(
            r"<files_changed>(.*?)</files_changed>", response_text, re.DOTALL
        )
        files_changed_raw = (
            files_changed_match.group(1).strip() if files_changed_match else None
        )

        files_changed = _parse_files_changed(files_changed_raw)

        if files_changed is None:
            state["error"] = (
                f"LLM returned an unparseable <files_changed> value: "
                f"{files_changed_raw!r}. Cannot proceed."
            )
            state["status"] = "failed"
            logger.error(
                "fix_generator_node: unparseable <files_changed> '%s' | "
                "incident_id=%s",
                files_changed_raw,
                incident_id,
            )
            return state

        # ---- Write results ------------------------------------------- #
        state["fix_diff"] = fix_diff
        state["files_changed"] = files_changed

        logger.debug(
            "fix_generator_node EXIT | incident_id=%s | files_changed=%s | "
            "diff_len=%d",
            incident_id,
            files_changed,
            len(fix_diff),
        )
        return state

    except Exception as exc:
        state["error"] = (
            f"fix_generator_node unhandled exception: {type(exc).__name__}: {exc}"
        )
        state["status"] = "failed"
        logger.error(
            "fix_generator_node EXCEPTION | incident_id=%s | error=%s",
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
    root_cause = state.get("root_cause", "")
    explanation = state.get("explanation", "")
    stack_frames: List[Dict[str, Any]] = state.get("stack_frames") or []
    github_context: Dict[str, str] = state.get("github_context") or {}

    frames_block = _format_frames_for_fix(stack_frames)
    github_block = _format_github_for_fix(github_context)

    return f"""You are generating a minimal, targeted code fix for a confirmed production bug.

═══════════════════════════════════════════════════════════════════════
CONFIRMED ROOT CAUSE
═══════════════════════════════════════════════════════════════════════
Error Type    : {error_type}
Error Message : {error_message}
Classification: {classification}
Root Cause    : {root_cause}

Explanation:
{explanation}

═══════════════════════════════════════════════════════════════════════
STACK FRAMES (innermost last)
═══════════════════════════════════════════════════════════════════════
{frames_block}

═══════════════════════════════════════════════════════════════════════
SOURCE CODE
═══════════════════════════════════════════════════════════════════════
{github_block}

═══════════════════════════════════════════════════════════════════════
INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════
Generate a minimal, safe, targeted fix.  Rules:
1. Change ONLY what is necessary to fix the confirmed root cause.
2. The diff MUST be valid unified diff format applicable with `git apply -p1`.
3. Include 3 lines of context (unchanged lines) before and after each change.
4. Do NOT reformat, rename, or refactor unrelated code.
5. Do NOT add new dependencies unless fixing a dependency issue.

Respond with EXACTLY this XML — no other text:

<fix_diff>
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -N,M +N,M @@
 context line
-old line to remove
+new line to add
 context line
</fix_diff>
<files_changed>
path/to/file.py
</files_changed>"""


def _format_frames_for_fix(frames: List[Dict[str, Any]]) -> str:
    if not frames:
        return "  (no frames available)"
    lines = []
    for frame in frames[-5:]:
        fname = frame.get("filename") or "?"
        lineno = frame.get("lineno") or "?"
        func = frame.get("function") or "?"
        ctx = (frame.get("context_line") or "").strip()
        lines.append(f"  {fname}:{lineno} in {func}() → {ctx}")
    return "\n".join(lines)


def _format_github_for_fix(github_ctx: Dict[str, str]) -> str:
    if not github_ctx:
        return "  (no source files fetched)"
    blocks = []
    for file_path, content in github_ctx.items():
        blocks.append(f"=== {file_path} ===\n{content}\n=== end {file_path} ===")
    return "\n\n".join(blocks)


# ------------------------------------------------------------------ #
# files_changed parser                                                 #
# ------------------------------------------------------------------ #

def _parse_files_changed(raw: str | None) -> List[str] | None:
    """
    Parse the raw <files_changed> content into a list of file path strings.

    Accepts:
        - JSON array:               ["a.py", "b.py"]
        - Newline-separated:        a.py\\nb.py
        - Comma-separated:          a.py, b.py
        - Single file (no newline): a.py

    Returns:
        A non-empty list of stripped file path strings, or None if the input
        is absent/empty/unparseable (signalling a pipeline failure).
    """
    if not raw:
        return None

    # Try JSON array first (most explicit)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            files = [str(f).strip() for f in parsed if str(f).strip()]
            return files if files else None
    except (json.JSONDecodeError, ValueError):
        pass

    # Newline-separated (LLM most commonly uses this)
    if "\n" in raw:
        files = [line.strip() for line in raw.splitlines() if line.strip()]
        return files if files else None

    # Comma-separated
    if "," in raw:
        files = [f.strip() for f in raw.split(",") if f.strip()]
        return files if files else None

    # Single file path
    single = raw.strip()
    return [single] if single else None
