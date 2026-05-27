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

import asyncio
import json
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_llm
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
            suggestion = await _generate_manual_fix_suggestion(state)
            state["fix_diff"] = ""
            state["files_changed"] = []
            state["action"] = "flag_for_review"
            state["explanation"] = suggestion
            logger.info(
                "fix_generator_node: skipping LLM call for classification='%s' | "
                "incident_id=%s",
                classification,
                incident_id,
            )

            # ---- Persist a fix record for the frontend to display -------- #
            # Even though there is no code patch, we save a fix row so the
            # frontend can show the manual remediation guidance.
            if suggestion:
                try:
                    from app.services.supabase import create_fix

                    # fix_diff must be non-blank (DB / schema constraint).
                    # root_cause may not be in state yet at this node — fall back
                    # to a placeholder so the insert does not fail a NOT NULL check.
                    _root_cause = state.get("root_cause") or (
                        f"Flagged as {classification} — see explanation."
                    )

                    fix_record = await asyncio.to_thread(
                        create_fix,
                        {
                            "incident_id": state.get("incident_id"),
                            "root_cause": _root_cause,
                            "explanation": suggestion,
                            "fix_diff": "# No patch — manual fix required.",
                            "confidence": 0.0,
                            "files_changed": [],
                            "validation_passed": False,
                        },
                    )
                    if fix_record:
                        state["fix_id"] = fix_record["id"]
                        logger.info(
                            "fix_generator_node: flagged fix record persisted | "
                            "incident_id=%s | fix_id=%s",
                            incident_id,
                            fix_record["id"],
                        )
                    else:
                        logger.warning(
                            "fix_generator_node: create_fix returned None for flagged "
                            "incident — DB insert may have failed silently | "
                            "incident_id=%s",
                            incident_id,
                        )
                except Exception as persist_exc:
                    logger.error(
                        "fix_generator_node: error persisting flagged fix | "
                        "incident_id=%s | error_type=%s | error=%s",
                        incident_id,
                        type(persist_exc).__name__,
                        persist_exc,
                        exc_info=True,
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
# Manual fix suggestion (for unfixable classifications)                #
# ------------------------------------------------------------------ #

async def _generate_manual_fix_suggestion(state: IncidentState) -> str:
    """
    Call the LLM synchronously (via asyncio.to_thread) to produce a
    structured, human-readable remediation guide for incidents classified
    as unfixable (e.g. config_issue, infrastructure).

    Uses llm.invoke() instead of ainvoke() so it is safe to run inside a
    Celery worker where there may be no running event loop.

    Falls back to a rich static message built from the incident's own data
    if the LLM call fails for any reason, so reviewers always get useful
    context.
    """
    error_type = state.get("error_type", "Unknown error")
    error_message = state.get("error_message", "")
    classification = state.get("issue_classification", "")
    root_cause = state.get("root_cause", "")

    prompt = f"""A production incident was flagged for human review because it is a '{classification}' issue that cannot be auto-fixed with a code patch.

Error: {error_type}: {error_message}
Root Cause: {root_cause}

Provide a clear, actionable explanation for a developer:
1. What exactly is wrong
2. Step-by-step manual fix instructions
3. How to prevent this in future

Be concise and specific. No fluff."""

    try:
        llm = get_llm()
        messages = [
            SystemMessage(content="You are a senior DevOps/backend engineer explaining production incidents to developers."),
            HumanMessage(content=prompt),
        ]
        # Use synchronous invoke inside to_thread — safe in Celery workers
        # where there is no running event loop to run ainvoke.
        response = await asyncio.to_thread(llm.invoke, messages)
        return response.content or _static_manual_suggestion(
            error_type, error_message, classification, root_cause
        )
    except Exception as exc:
        logger.warning(
            "fix_generator: LLM call for manual suggestion failed (%s: %s) — "
            "using static fallback | classification=%s",
            type(exc).__name__,
            exc,
            classification,
        )
        return _static_manual_suggestion(
            error_type, error_message, classification, root_cause
        )


def _static_manual_suggestion(
    error_type: str,
    error_message: str,
    classification: str,
    root_cause: str,
) -> str:
    """
    Build a structured, informative manual-review message from the incident's
    own data when the LLM is unavailable.
    """
    guidance: dict = {
        "config_issue": (
            "Configuration issues cannot be resolved by changing application code.\n\n"
            "Recommended steps:\n"
            "1. Review your environment variables, secrets, and config files for the "
            "value referenced in the error.\n"
            "2. Verify the config is correctly set in all environments "
            "(development, staging, production).\n"
            "3. Restart the affected service after updating the config.\n"
            "4. Add startup validation (e.g. Pydantic Settings) to catch missing "
            "config at boot time rather than at runtime."
        ),
        "infrastructure": (
            "Infrastructure issues require changes outside the application codebase.\n\n"
            "Recommended steps:\n"
            "1. Check the health of the affected infrastructure component "
            "(database, cache, message broker, external API).\n"
            "2. Review recent deployment changes, scaling events, or network "
            "configuration updates.\n"
            "3. Check service quotas and resource limits (memory, connections, disk).\n"
            "4. Add health checks and alerting for the affected component to "
            "detect failures earlier in future."
        ),
    }
    type_guidance = guidance.get(
        classification,
        (
            "This incident requires manual review.\n\n"
            "Investigate the root cause listed above and apply the appropriate fix "
            "for your environment."
        ),
    )

    parts = [
        f"Error: {error_type}: {error_message}" if error_message else f"Error: {error_type}",
    ]
    if root_cause:
        parts.append(f"Root Cause: {root_cause}")
    parts.append("")
    parts.append(type_guidance)

    return "\n".join(parts)


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
