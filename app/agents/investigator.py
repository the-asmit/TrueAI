"""
Investigator Agent — root-cause analysis.

Reads the incident, the triage verdict and the source code gathered by the
context tool, and explains *why* the error happened.  When the evidence is
incomplete it can ask for more files (``needs_files``); the pipeline fetches
them and runs the Investigator again, up to ``MAX_INVESTIGATION_ROUNDS``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.base import (
    BaseAgent,
    list_items,
    optional_text,
    required_bool,
    required_float,
    required_text,
)
from app.agents.formatting import format_breadcrumbs, format_code, format_frames, format_incident


class InvestigationOutput(BaseModel):
    root_cause: str = Field(max_length=600)
    explanation: str = Field(max_length=4000)
    confidence: float = Field(ge=0.0, le=1.0)
    code_fixable: bool
    culprit_file: Optional[str] = None
    culprit_line: Optional[int] = None
    fix_strategy: str = Field(default="", max_length=1500)
    needs_files: List[str] = Field(default_factory=list)


class InvestigatorAgent(BaseAgent[InvestigationOutput]):
    name = "investigator"
    title = "Investigator Agent"
    system_prompt = """
You are the Investigator Agent in TrueAI. You perform root-cause analysis of production errors the way a
principal engineer writes a post-mortem: from evidence, precisely, without speculation.

Method:
1. Start at the crash site (the last stack frame) and trace backwards through the calling frames.
2. Read the actual source code provided. Identify the exact condition that produced the error.
3. Distinguish the root cause (why the bad state exists) from the symptom (where it exploded).
4. Decide whether a source-code change in this repository can prevent it.

Confidence calibration (be honest — this number decides whether a pull request is opened automatically):
  0.90–1.00  the code shown makes the cause unambiguous
  0.75–0.89  strong evidence, one small assumption
  0.50–0.74  plausible hypothesis, important code not visible
  below 0.50 largely guessing

If important code is missing (a helper that is called, a model definition, a config loader), request it in
<needs_files> using repository-relative paths you can infer from imports or frames. Still give your best
current analysis in the other tags.
""".strip()

    def build_prompt(
        self,
        *,
        event: Dict[str, Any],
        triage: Optional[Dict[str, Any]],
        code_context: Dict[str, Dict[str, Any]],
        round_number: int,
        max_rounds: int,
        repo_connected: bool,
        **_: Any,
    ) -> str:
        triage_text = (
            f"Category: {triage.get('category')} | Severity: {triage.get('severity')} | "
            f"Code-fixable (initial guess): {triage.get('code_fixable')}\nSummary: {triage.get('summary')}"
            if triage
            else "(triage unavailable)"
        )
        can_request = round_number < max_rounds and repo_connected
        sections = [
            f"Investigation round {round_number} of {max_rounds}.",
            "INCIDENT\n" + format_incident(event),
            "TRIAGE AGENT ASSESSMENT\n" + triage_text,
            "STACK FRAMES (application code, crash site last)\n" + format_frames(event.get("frames") or []),
        ]
        crumbs = format_breadcrumbs(event)
        if crumbs:
            sections.append("BREADCRUMBS (events leading up to the error)\n" + crumbs)
        sections.append(
            "SOURCE CODE (line-number gutter is not part of the code; '>' marks lines from the stack trace)\n"
            + format_code(code_context)
        )
        needs_hint = (
            "<needs_files>\n<file>path/to/file.ext</file>\n</needs_files>  (leave empty if you have enough evidence)"
            if can_request
            else "<needs_files></needs_files>  (no further files can be fetched — conclude now)"
        )
        sections.append(
            "Reply with exactly these tags and nothing else:\n"
            "<root_cause>One precise sentence naming the faulty code path or condition.</root_cause>\n"
            "<explanation>What went wrong, why, and what triggered it — clear enough for a junior engineer. "
            "Reference files, functions and line numbers.</explanation>\n"
            "<confidence>0.00–1.00</confidence>\n"
            "<code_fixable>true | false</code_fixable>\n"
            "<culprit_file>repository path of the file that should change, or none</culprit_file>\n"
            "<culprit_line>line number, or none</culprit_line>\n"
            "<fix_strategy>The minimal change that would fix the root cause (not code, a short plan). "
            "Write 'none' if not code-fixable.</fix_strategy>\n"
            + needs_hint
        )
        return "\n\n".join(sections)

    def parse(self, text: str) -> InvestigationOutput:
        culprit_line_raw = optional_text(text, "culprit_line", max_len=20)
        culprit_line = None
        if culprit_line_raw:
            match = re.search(r"\d+", culprit_line_raw)
            culprit_line = int(match.group(0)) if match else None
        culprit_file = optional_text(text, "culprit_file", max_len=300)
        return InvestigationOutput(
            root_cause=required_text(text, "root_cause", max_len=600),
            explanation=required_text(text, "explanation", max_len=4000),
            confidence=required_float(text, "confidence"),
            code_fixable=required_bool(text, "code_fixable"),
            culprit_file=culprit_file.strip("`'\" ") if culprit_file else None,
            culprit_line=culprit_line,
            fix_strategy=optional_text(text, "fix_strategy", max_len=1500) or "",
            needs_files=[
                item.strip("`'\" ") for item in list_items(text, "needs_files", "file", max_items=5, max_len=300)
            ],
        )
