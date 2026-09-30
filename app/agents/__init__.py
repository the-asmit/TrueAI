"""
TrueAI's agent team.

Each agent has one job and its own model configuration
(``AGENT_<NAME>_PROVIDER`` / ``_MODEL`` / ``_TEMPERATURE`` / ``_MAX_TOKENS``):

    Triage Agent        classify the incident and its severity
    Investigator Agent  root-cause analysis; may request more source files
    Fix Engineer Agent  minimal code change as search/replace edits
    Reviewer Agent      independent review: approve / revise / reject
    Remediation Agent   concrete human steps when no PR is opened

The LangGraph pipeline in ``app.core.graph`` orchestrates them together with
deterministic tools (source context, patch engine, policy guard, GitHub PR).
"""

from app.agents.fix_engineer import FixEngineerAgent, FixOutput
from app.agents.investigator import InvestigationOutput, InvestigatorAgent
from app.agents.remediation import RemediationAgent, RemediationOutput
from app.agents.reviewer import ReviewerAgent, ReviewOutput
from app.agents.triage import TriageAgent, TriageOutput

AGENTS = {
    TriageAgent.name: TriageAgent,
    InvestigatorAgent.name: InvestigatorAgent,
    FixEngineerAgent.name: FixEngineerAgent,
    ReviewerAgent.name: ReviewerAgent,
    RemediationAgent.name: RemediationAgent,
}

__all__ = [
    "AGENTS",
    "FixEngineerAgent",
    "FixOutput",
    "InvestigationOutput",
    "InvestigatorAgent",
    "RemediationAgent",
    "RemediationOutput",
    "ReviewOutput",
    "ReviewerAgent",
    "TriageAgent",
    "TriageOutput",
]
