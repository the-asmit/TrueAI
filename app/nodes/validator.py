"""
Validator node — two-stage verification of the generated code fix.

Stage 1 — Syntax / structural check (no LLM):
    Verify the fix_diff is a valid unified diff by checking for the
    mandatory markers: --- / +++ header lines, @@ hunk header, and at
    least one changed line (+/-).  This is cheap and catches the most
    common LLM formatting mistakes before wasting an LLM call.

Stage 2 — LLM critique (only if Stage 1 passes):
    Claude reviews the diff in the context of the root cause and the
    original source code to confirm semantic correctness.

Parsing rules (strictly enforced per project spec):
    Use re.search() with DOTALL flag.
    Validate EVERY extracted value:
        is_valid       : None or empty → validation_passed = False, log WARNING
        critique       : None or empty → log WARNING, continue (non-critical)
        updated_confidence : cannot cast to float → keep existing confidence, log WARNING
    If the entire LLM parse fails → validation_passed = False, log WARNING.
    NEVER crash. NEVER set status = "failed" — a failed validation is a
    normal pipeline outcome that routes to flag_for_review.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_llm
from app.core.logging import get_logger
from app.core.state import IncidentState

logger = get_logger(__name__)

_SYSTEM_PROMPT: str = (
    "You are a senior code reviewer specialising in patch safety and correctness. "
    "You evaluate proposed fixes rigorously — you never rubber-stamp a patch. "
    "You respond with the exact XML format requested — no prose outside the XML tags."
)


async def validator_node(state: IncidentState) -> IncidentState:
    """
    Validate the generated fix_diff in two stages.

    Reads:
        fix_diff, root_cause, error_type, github_context, confidence

    Writes:
        validation_passed
        confidence  (updated by LLM if it returns a valid updated_confidence)

    Never writes error / status = "failed" — validation failure is a normal
    outcome that the decision node handles via action = "flag_for_review".
    """
    state = {**state}
    incident_id = state.get("incident_id", "unknown")
    logger.debug("validator_node ENTRY | incident_id=%s", incident_id)

    try:
        fix_diff: str = state.get("fix_diff") or ""

        # ---- Fast exit: no diff to validate -------------------------- #
        if not fix_diff.strip():
            state["validation_passed"] = False
            logger.info(
                "validator_node: fix_diff is empty — validation_passed=False | "
                "incident_id=%s",
                incident_id,
            )
            return state

        # ---- Stage 1: Structural / syntax check ---------------------- #
        syntax_ok, syntax_reason = _check_unified_diff_syntax(fix_diff)
        if not syntax_ok:
            state["validation_passed"] = False
            logger.warning(
                "validator_node: Stage 1 FAILED — invalid diff format | "
                "incident_id=%s | reason=%s",
                incident_id,
                syntax_reason,
            )
            return state

        logger.debug(
            "validator_node: Stage 1 PASSED | incident_id=%s", incident_id
        )

        # ---- Stage 2: LLM semantic review ---------------------------- #
        prompt = _build_prompt(state)
        llm = get_llm()
        response = await llm.ainvoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        response_text: str = response.content or ""

        validation_passed, updated_confidence = _parse_llm_response(
            response_text, state, incident_id
        )

        state["validation_passed"] = validation_passed
        if updated_confidence is not None:
            state["confidence"] = updated_confidence

        # ---- Persist fix to DB when validation passes ---------------- #
        if validation_passed:
            try:
                from app.services.supabase import create_fix

                fix_record = await asyncio.to_thread(
                    create_fix,
                    {
                        "incident_id": state.get("incident_id"),
                        "root_cause": state.get("root_cause"),
                        "explanation": state.get("explanation"),
                        "fix_diff": state.get("fix_diff"),
                        "confidence": state.get("confidence"),
                        "status": "pending",
                    },
                )
                if fix_record:
                    state["fix_id"] = fix_record["id"]
                    logger.debug(
                        "validator_node: fix persisted | incident_id=%s | fix_id=%s",
                        incident_id,
                        fix_record["id"],
                    )
                else:
                    logger.warning(
                        "validator_node: failed to persist fix to DB | incident_id=%s",
                        incident_id,
                    )
            except Exception as persist_exc:
                logger.error(
                    "validator_node: error persisting fix | incident_id=%s | error=%s",
                    incident_id,
                    persist_exc,
                )

        logger.debug(
            "validator_node EXIT | incident_id=%s | validation_passed=%s | "
            "confidence=%.3f",
            incident_id,
            validation_passed,
            state.get("confidence", 0.0),
        )
        return state

    except Exception as exc:
        # Validator exceptions → validation_passed=False, never crash.
        state["validation_passed"] = False
        logger.error(
            "validator_node EXCEPTION (setting validation_passed=False) | "
            "incident_id=%s | error=%s — %s",
            incident_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return state


# ------------------------------------------------------------------ #
# Stage 1: structural syntax check                                     #
# ------------------------------------------------------------------ #

def _check_unified_diff_syntax(diff: str) -> tuple[bool, str]:
    """
    Return (is_valid, reason) for a minimal unified diff structural check.

    A valid unified diff must have:
        1. At least one --- header line
        2. At least one +++ header line
        3. At least one @@ hunk header line
        4. At least one line starting with + or - (an actual change)
        5. The + and - headers must be distinct (not the same file to itself)
    """
    lines = diff.splitlines()

    has_old_header = any(l.startswith("--- ") for l in lines)
    if not has_old_header:
        return False, "No '--- ' header line found."

    has_new_header = any(l.startswith("+++ ") for l in lines)
    if not has_new_header:
        return False, "No '+++ ' header line found."

    has_hunk = any(l.startswith("@@") for l in lines)
    if not has_hunk:
        return False, "No '@@ ' hunk header found."

    # Must contain at least one genuinely added or removed line
    # (lines starting with + or - that are NOT the file headers)
    has_change = any(
        l.startswith("+") and not l.startswith("+++")
        or l.startswith("-") and not l.startswith("---")
        for l in lines
    )
    if not has_change:
        return False, "Diff has no added (+) or removed (-) lines."

    return True, "OK"


# ------------------------------------------------------------------ #
# Stage 2: LLM response parser                                        #
# ------------------------------------------------------------------ #

def _parse_llm_response(
    response_text: str,
    state: IncidentState,
    incident_id: str,
) -> tuple[bool, float | None]:
    """
    Parse the LLM validation response.

    Returns:
        (validation_passed, updated_confidence_or_None)

    On any parse failure → validation_passed=False, updated_confidence=None,
    with a WARNING log.  Never raises.
    """
    existing_confidence: float = float(state.get("confidence") or 0.0)

    # ---- is_valid ---------------------------------------------------- #
    is_valid_match = re.search(
        r"<is_valid>(.*?)</is_valid>", response_text, re.DOTALL
    )
    is_valid_raw = is_valid_match.group(1).strip() if is_valid_match else None

    if not is_valid_raw:
        logger.warning(
            "validator_node: <is_valid> tag absent or empty | incident_id=%s "
            "— setting validation_passed=False",
            incident_id,
        )
        return False, None

    validation_passed: bool = is_valid_raw.lower() in ("true", "yes", "1", "valid")

    # ---- critique (non-critical) ------------------------------------- #
    critique_match = re.search(
        r"<critique>(.*?)</critique>", response_text, re.DOTALL
    )
    critique = critique_match.group(1).strip() if critique_match else None
    if not critique:
        logger.warning(
            "validator_node: <critique> tag absent or empty | incident_id=%s",
            incident_id,
        )
        # Non-critical — continue without it

    if critique:
        logger.info(
            "validator_node LLM critique | incident_id=%s | valid=%s | critique=%s",
            incident_id,
            validation_passed,
            critique[:200],
        )

    # ---- updated_confidence ----------------------------------------- #
    updated_conf_match = re.search(
        r"<updated_confidence>(.*?)</updated_confidence>", response_text, re.DOTALL
    )
    updated_conf_raw = (
        updated_conf_match.group(1).strip() if updated_conf_match else None
    )

    updated_confidence: float | None = None
    if updated_conf_raw:
        try:
            parsed_conf = float(updated_conf_raw)
            updated_confidence = max(0.0, min(1.0, parsed_conf))
        except (TypeError, ValueError):
            logger.warning(
                "validator_node: cannot parse <updated_confidence> '%s' | "
                "incident_id=%s — keeping existing confidence=%.3f",
                updated_conf_raw,
                incident_id,
                existing_confidence,
            )
            # Keep existing confidence — do NOT update state

    return validation_passed, updated_confidence


# ------------------------------------------------------------------ #
# Prompt builder                                                       #
# ------------------------------------------------------------------ #

def _build_prompt(state: IncidentState) -> str:
    error_type = state.get("error_type", "Unknown")
    error_message = state.get("error_message", "")
    root_cause = state.get("root_cause", "")
    fix_diff = state.get("fix_diff", "")
    github_context: Dict[str, str] = state.get("github_context") or {}
    confidence = float(state.get("confidence") or 0.0)

    github_block = _format_github(github_context)

    return f"""You are reviewing a proposed code fix for a production incident.
Your job is to determine if this fix is correct, safe, and minimal.

═══════════════════════════════════════════════════════════════════════
INCIDENT
═══════════════════════════════════════════════════════════════════════
Error Type    : {error_type}
Error Message : {error_message}
Root Cause    : {root_cause}
Current Confidence: {confidence:.2f}

═══════════════════════════════════════════════════════════════════════
PROPOSED FIX (unified diff)
═══════════════════════════════════════════════════════════════════════
{fix_diff}

═══════════════════════════════════════════════════════════════════════
ORIGINAL SOURCE CODE
═══════════════════════════════════════════════════════════════════════
{github_block}

═══════════════════════════════════════════════════════════════════════
REVIEW CRITERIA
═══════════════════════════════════════════════════════════════════════
1. Does the fix correctly address the confirmed root cause?
2. Does the fix introduce any new bugs, regressions, or security issues?
3. Is the fix minimal — does it change only what is necessary?
4. Will the diff apply cleanly to the code shown above?
5. Are there edge cases the fix does not handle that could cause failures?

Respond with EXACTLY this XML — no other text:

<is_valid>true or false</is_valid>
<critique>Concise explanation: what is correct, what is wrong, what edge cases are missed. Be specific — reference line numbers and function names.</critique>
<updated_confidence>A float 0.00–1.00. Increase if the fix is clearly correct. Decrease if you identified issues. Keep near current if uncertain.</updated_confidence>"""


def _format_github(github_ctx: Dict[str, str]) -> str:
    if not github_ctx:
        return "  (no source files available)"
    blocks = []
    for file_path, content in github_ctx.items():
        blocks.append(f"=== {file_path} ===\n{content}\n=== end {file_path} ===")
    return "\n\n".join(blocks)
