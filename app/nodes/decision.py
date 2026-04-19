"""
Decision node — pure logic routing between "create_pr" and "flag_for_review".

No LLM calls.  No external I/O.  This node reads confidence and
validation_passed from state and applies a single deterministic rule.

Routing rule:
    confidence >= CONFIDENCE_AUTO_FIX_THRESHOLD (0.75)
    AND validation_passed is True
    → action = "create_pr"

    Any other combination (low confidence, failed validation, missing values)
    → action = "flag_for_review"

Treating missing values as flag_for_review is the safe default — we never
auto-merge a fix when we are uncertain.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.state import IncidentState
from app.schemas.fix import CONFIDENCE_AUTO_FIX_THRESHOLD

logger = get_logger(__name__)


async def decision_node(state: IncidentState) -> IncidentState:
    """
    Route the pipeline to automatic PR creation or human-review escalation.

    Reads:
        confidence, validation_passed

    Writes:
        action  →  "create_pr" | "flag_for_review"

    Never writes error / status = "failed" — this node cannot fail because
    it performs no I/O and the routing rule covers every possible input.
    """
    state = {**state}
    incident_id = state.get("incident_id", "unknown")
    logger.debug("decision_node ENTRY | incident_id=%s", incident_id)

    try:
        confidence: float = float(state.get("confidence") or 0.0)
        validation_passed: bool = bool(state.get("validation_passed", False))

        meets_threshold = confidence >= CONFIDENCE_AUTO_FIX_THRESHOLD
        action: str = (
            "create_pr" if (meets_threshold and validation_passed)
            else "flag_for_review"
        )

        state["action"] = action

        logger.info(
            "decision_node EXIT | incident_id=%s | confidence=%.3f | "
            "threshold=%.2f | validation_passed=%s | action=%s",
            incident_id,
            confidence,
            CONFIDENCE_AUTO_FIX_THRESHOLD,
            validation_passed,
            action,
        )
        return state

    except Exception as exc:
        # Should never happen since this node does no I/O, but guard anyway.
        state["action"] = "flag_for_review"
        logger.error(
            "decision_node EXCEPTION (defaulting to flag_for_review) | "
            "incident_id=%s | error=%s — %s",
            incident_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        return state
