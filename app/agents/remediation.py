"""
Remediation Agent — actionable guidance when TrueAI will not open a PR.

Runs for every incident that ends up needing a human: configuration and
infrastructure problems, low-confidence analyses, fixes the Reviewer
rejected, patches blocked by policy, or repositories TrueAI cannot write to.
It turns everything the other agents learned into concrete next steps.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, list_items, optional_text, required_text
from app.agents.formatting import format_frames, format_incident
from app.core.errors import AgentOutputError
from app.core.security import fence_untrusted


class RemediationOutput(BaseModel):
    summary: str = Field(max_length=800)
    steps: List[str] = Field(min_length=1)
    verification: str = Field(default="", max_length=1000)
    prevention: str = Field(default="", max_length=1000)


class RemediationAgent(BaseAgent[RemediationOutput]):
    name = "remediation"
    title = "Remediation Agent"
    system_prompt = """
You are the Remediation Agent in TrueAI. An incident needs a human, and your job is to make their work
fast: concrete, ordered steps specific to THIS incident — which setting, file, service or query to check,
and what to change. No generic advice ("check your logs") unless you say exactly what to look for.
""".strip()

    def build_prompt(
        self,
        *,
        event: Dict[str, Any],
        triage: Optional[Dict[str, Any]],
        investigation: Optional[Dict[str, Any]],
        flag_reason: str,
        suggested_diff: Optional[str],
        **_: Any,
    ) -> str:
        sections = [
            "INCIDENT\n" + format_incident(event),
            "STACK FRAMES (crash site last)\n" + format_frames(event.get("frames") or [], limit=6),
            "WHY A HUMAN IS NEEDED\n" + flag_reason,
        ]
        if triage:
            sections.append(f"TRIAGE\nCategory: {triage.get('category')} | Severity: {triage.get('severity')}\n{triage.get('summary')}")
        if investigation:
            sections.append(
                "ROOT CAUSE ANALYSIS\n"
                f"{investigation.get('root_cause')}\n\n{investigation.get('explanation')}\n"
                f"(confidence {float(investigation.get('confidence') or 0):.2f})"
            )
        if suggested_diff:
            sections.append(
                "A PATCH WAS DRAFTED BUT NOT AUTO-APPLIED (reference only)\n"
                + fence_untrusted("draft_patch", suggested_diff, max_len=5000)
            )
        sections.append(
            "Reply with exactly these tags and nothing else:\n"
            "<summary>What is wrong, in one or two sentences.</summary>\n"
            "<steps>\n<step>First concrete action</step>\n<step>Next action</step>\n</steps>\n"
            "<verification>How to confirm the problem is resolved.</verification>\n"
            "<prevention>What would stop this class of incident recurring.</prevention>"
        )
        return "\n\n".join(sections)

    def parse(self, text: str) -> RemediationOutput:
        steps = list_items(text, "steps", "step", max_items=10, max_len=600)
        if not steps:
            raise AgentOutputError("<steps> must contain at least one <step>")
        return RemediationOutput(
            summary=required_text(text, "summary", max_len=800),
            steps=steps,
            verification=optional_text(text, "verification", max_len=1000) or "",
            prevention=optional_text(text, "prevention", max_len=1000) or "",
        )
