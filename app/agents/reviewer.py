"""
Reviewer Agent — independent code review of the proposed fix.

Receives the root cause, the exact diff (built by the patch engine, not by
an LLM), the surrounding source and the results of the deterministic
checks.  Its verdict decides the next step:

    approve  → the decision step may open a pull request
    revise   → back to the Fix Engineer with concrete instructions
    reject   → no automated PR; the incident is flagged with guidance
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, list_items, optional_text, required_choice, required_float, required_text
from app.agents.formatting import format_code, format_incident
from app.core.errors import AgentOutputError
from app.core.security import fence_untrusted


class ReviewOutput(BaseModel):
    verdict: Literal["approve", "revise", "reject"]
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(max_length=1500)
    issues: List[str] = Field(default_factory=list)
    revision_instructions: str = Field(default="", max_length=2000)


class ReviewerAgent(BaseAgent[ReviewOutput]):
    name = "reviewer"
    title = "Reviewer Agent"
    system_prompt = """
You are the Reviewer Agent in TrueAI — a senior engineer doing a careful code review of an automated fix
before it becomes a pull request. You are independent of the engineer who wrote it: never rubber-stamp.

Check, in order:
1. Correctness — does the change actually remove the root cause, on every code path that reaches it?
2. Regressions — could it break callers, change behaviour for valid inputs, or mask real errors?
3. Safety — no new security issues (injection, auth bypass, secrets, unsafe execution, weakened checks).
4. Minimality — only necessary lines changed, in the project's existing style.
5. Completeness — obvious edge cases handled; it would pass review at a strong engineering team.

Verdicts:
  approve — correct, safe and minimal; you would merge it.
  revise  — the direction is right but specific problems must be fixed (give precise instructions).
  reject  — wrong approach, unsafe, or the root cause analysis itself looks wrong.

confidence is your probability that this exact patch fixes the incident without introducing regressions.
""".strip()

    def build_prompt(
        self,
        *,
        event: Dict[str, Any],
        investigation: Dict[str, Any],
        fix: Dict[str, Any],
        diff: str,
        code_context: Dict[str, Dict[str, Any]],
        automated_checks: List[str],
        attempt: int,
        max_attempts: int,
        **_: Any,
    ) -> str:
        checks = "\n".join(f"- {item}" for item in automated_checks) or "- all automated checks passed"
        revise_note = (
            "You may request a revision."
            if attempt < max_attempts
            else "This is the final attempt: choose approve or reject (revise is treated as reject)."
        )
        sections = [
            f"Review of fix attempt {attempt} of {max_attempts}. {revise_note}",
            "INCIDENT\n" + format_incident(event),
            "ROOT CAUSE\n"
            f"{investigation.get('root_cause')}\n\n{investigation.get('explanation')}",
            "FIX ENGINEER'S DESCRIPTION\n"
            f"Title: {fix.get('summary')}\nRationale: {fix.get('rationale')}\nSelf-assessed risk: {fix.get('risk')}",
            "PROPOSED CHANGE (unified diff)\n" + fence_untrusted("diff", diff, max_len=12_000),
            "ORIGINAL SOURCE (before the change)\n" + format_code(code_context, budget=14_000),
            "AUTOMATED CHECKS\n" + checks,
            "Reply with exactly these tags and nothing else:\n"
            "<verdict>approve | revise | reject</verdict>\n"
            "<confidence>0.00–1.00</confidence>\n"
            "<summary>A short review a human reviewer would find useful.</summary>\n"
            "<issues>\n<issue>each concrete problem found (omit when none)</issue>\n</issues>\n"
            "<revision_instructions>Required when verdict is revise: exactly what to change.</revision_instructions>",
        ]
        return "\n\n".join(sections)

    def parse(self, text: str) -> ReviewOutput:
        verdict = required_choice(text, "verdict", ("approve", "revise", "reject"))
        instructions = optional_text(text, "revision_instructions", max_len=2000) or ""
        issues = list_items(text, "issues", "issue", max_items=10, max_len=500)
        if verdict == "revise" and not (instructions or issues):
            raise AgentOutputError("a 'revise' verdict must include <revision_instructions>")
        return ReviewOutput(
            verdict=verdict,  # type: ignore[arg-type]
            confidence=required_float(text, "confidence"),
            summary=required_text(text, "summary", max_len=1500),
            issues=issues,
            revision_instructions=instructions,
        )
