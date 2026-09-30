"""
Triage Agent — first look at an incident.

Decides what kind of problem this is and how urgent it is, from the Sentry
event alone (no source code yet).  Its answer is a prior for the
Investigator and drives how the dashboard labels the incident.
"""

from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from app.agents.base import BaseAgent, optional_text, required_bool, required_choice, required_text
from app.agents.formatting import format_breadcrumbs, format_frames, format_incident

Category = Literal["code_bug", "config_issue", "infrastructure", "data_issue", "dependency"]
Severity = Literal["critical", "high", "medium", "low"]

CATEGORIES = ("code_bug", "config_issue", "infrastructure", "data_issue", "dependency")
SEVERITIES = ("critical", "high", "medium", "low")


class TriageOutput(BaseModel):
    category: Category
    severity: Severity
    code_fixable: bool
    summary: str = Field(max_length=300)
    reasoning: str = Field(default="", max_length=1500)


class TriageAgent(BaseAgent[TriageOutput]):
    name = "triage"
    title = "Triage Agent"
    system_prompt = """
You are the Triage Agent in TrueAI, an automated incident-response team.
You receive a production error captured by Sentry and classify it quickly and accurately.

Categories:
  code_bug       — a defect in the application's own code (logic error, unhandled None/undefined,
                   wrong type, missing key, off-by-one, bad state handling).
  config_issue   — wrong or missing configuration: environment variables, settings files, feature flags, secrets.
  infrastructure — the environment failed: network timeouts, DNS, database/cache down, OOM, disk full, quota.
  data_issue     — unexpected or corrupt data: integrity violations, malformed records, schema drift.
  dependency     — a third-party library or external API misbehaving or used incorrectly after an upgrade.

Severity: critical = outage or data loss; high = a core flow is broken; medium = a degraded or partial
feature; low = cosmetic or rare edge case.

code_fixable = true when a change to the application's source code could plausibly prevent this error
(including defensive handling of bad data or failing dependencies). Pure infrastructure outages and
missing configuration values are normally false.
""".strip()

    def build_prompt(self, *, event: Dict[str, Any], **_: Any) -> str:
        sections = [
            "Classify this production incident.",
            "INCIDENT\n" + format_incident(event),
            "STACK FRAMES (application code, crash site last)\n" + format_frames(event.get("frames") or [], limit=8),
        ]
        crumbs = format_breadcrumbs(event, limit=5)
        if crumbs:
            sections.append("RECENT BREADCRUMBS\n" + crumbs)
        sections.append(
            "Reply with exactly these tags and nothing else:\n"
            "<category>code_bug | config_issue | infrastructure | data_issue | dependency</category>\n"
            "<severity>critical | high | medium | low</severity>\n"
            "<code_fixable>true | false</code_fixable>\n"
            "<summary>One plain sentence describing what failed, for an engineer skimming a list.</summary>\n"
            "<reasoning>Two or three sentences citing the evidence that led to this classification.</reasoning>"
        )
        return "\n\n".join(sections)

    def parse(self, text: str) -> TriageOutput:
        return TriageOutput(
            category=required_choice(text, "category", CATEGORIES),  # type: ignore[arg-type]
            severity=required_choice(text, "severity", SEVERITIES),  # type: ignore[arg-type]
            code_fixable=required_bool(text, "code_fixable"),
            summary=required_text(text, "summary", max_len=300),
            reasoning=optional_text(text, "reasoning", max_len=1500) or "",
        )
