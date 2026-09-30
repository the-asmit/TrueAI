"""
LangGraph orchestration of TrueAI's multi-agent incident pipeline.

Graph topology
──────────────

    parser ─► triage ─► context ─► investigator ──(needs more files)──► context ─┐
                                        ▲                                         │
                                        └─────────────────────────────────────────┘
                                        │
                     (not code-fixable / low confidence)
                                        ├──────────────────────────────► remediation ─► finalize
                                        ▼                                    ▲
                                  fix_engineer ◄──(patch failed / revise)──┐ │
                                        │                                  │ │
                                        ▼                                  │ │
                                    reviewer ──────────────────────────────┘ │
                                        │ approve                            │
                                        ▼                                    │
                                    decision ──(flag)────────────────────────┤
                                        │ create_pr                          │
                                        ▼                                    │
                                   pr_creator ──(PR failed)──────────────────┘
                                        │
                                        ▼
                                    finalize ─► END

Agents (LLM):  triage, investigator, fix_engineer, reviewer, remediation
Tools:         parser, context, pr_creator (+ the patch engine inside fix_engineer)
Logic:         decision, finalize

Any node that sets ``status = "failed"`` routes straight to ``finalize``.

Design rules (unchanged from the original pipeline):
    1. Routing functions read with ``state.get()`` — keys may be absent.
    2. Routing functions are named, documented functions (no lambdas) so they
       appear clearly in LangGraph's Mermaid diagrams and stack traces.
    3. The compiled graph is a module-level singleton (``incident_graph``).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.core.config import settings
from app.core.logging import get_logger
from app.core.state import IncidentState
from app.nodes.context import context_node
from app.nodes.decision import decision_node
from app.nodes.finalize import finalize_node
from app.nodes.fix_engineer import fix_engineer_node
from app.nodes.investigator import investigator_node
from app.nodes.parser import parser_node
from app.nodes.pr_creator import pr_creator_node
from app.nodes.remediation import remediation_node
from app.nodes.reviewer import reviewer_node
from app.nodes.triage import triage_node

logger = get_logger(__name__)


# ================================================================== #
# Routing functions                                                    #
# ================================================================== #

def _failed(state: IncidentState) -> bool:
    return state.get("status") == "failed"


def route_after_simple_step(state: IncidentState) -> str:
    """parser / triage / context: stop on failure, otherwise continue."""
    return "finalize" if _failed(state) else "continue"


def route_after_context(state: IncidentState) -> str:
    """Always go to the Investigator (first pass and after fetching requested files)."""
    return "finalize" if _failed(state) else "investigator"


def route_after_investigator(state: IncidentState) -> str:
    """
    More files requested → context.  Not code-fixable, low confidence or no
    repository → remediation.  Otherwise → fix_engineer.
    """
    if _failed(state):
        return "finalize"
    if state.get("pending_file_requests"):
        return "context"
    investigation = state.get("investigation") or {}
    if not investigation.get("code_fixable"):
        return "remediation"
    if float(investigation.get("confidence") or 0) < settings.CONFIDENCE_MIN_FIX_THRESHOLD:
        return "remediation"
    if not state.get("repo"):
        return "remediation"
    return "fix_engineer"


def route_after_fix_engineer(state: IncidentState) -> str:
    """Flagged → remediation.  No usable patch yet → try again.  Otherwise → reviewer."""
    if _failed(state):
        return "finalize"
    if state.get("action") == "flag_for_review":
        return "remediation"
    if not (state.get("patch") or {}).get("files"):
        return "fix_engineer"
    return "reviewer"


def route_after_reviewer(state: IncidentState) -> str:
    """Approved → decision.  Revision requested → fix_engineer.  Rejected → remediation."""
    if _failed(state):
        return "finalize"
    if state.get("action") == "flag_for_review":
        return "remediation"
    if (state.get("review") or {}).get("verdict") == "approve":
        return "decision"
    return "fix_engineer"


def route_after_decision(state: IncidentState) -> str:
    return "pr_creator" if state.get("action") == "create_pr" else "remediation"


def route_after_pr_creator(state: IncidentState) -> str:
    if _failed(state):
        return "finalize"
    return "finalize" if state.get("pr") else "remediation"


# ================================================================== #
# Graph construction                                                   #
# ================================================================== #

def build_graph() -> StateGraph:
    """Construct the (uncompiled) pipeline graph — kept separate for tests."""
    graph = StateGraph(IncidentState)

    graph.add_node("parser", parser_node)
    graph.add_node("triage", triage_node)
    graph.add_node("context", context_node)
    graph.add_node("investigator", investigator_node)
    graph.add_node("fix_engineer", fix_engineer_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("decision", decision_node)
    graph.add_node("pr_creator", pr_creator_node)
    graph.add_node("remediation", remediation_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "parser")
    graph.add_conditional_edges("parser", route_after_simple_step, {"continue": "triage", "finalize": "finalize"})
    graph.add_conditional_edges("triage", route_after_simple_step, {"continue": "context", "finalize": "finalize"})
    graph.add_conditional_edges("context", route_after_context, {"investigator": "investigator", "finalize": "finalize"})
    graph.add_conditional_edges(
        "investigator",
        route_after_investigator,
        {"context": "context", "remediation": "remediation", "fix_engineer": "fix_engineer", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "fix_engineer",
        route_after_fix_engineer,
        {"fix_engineer": "fix_engineer", "reviewer": "reviewer", "remediation": "remediation", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {"decision": "decision", "fix_engineer": "fix_engineer", "remediation": "remediation", "finalize": "finalize"},
    )
    graph.add_conditional_edges("decision", route_after_decision, {"pr_creator": "pr_creator", "remediation": "remediation"})
    graph.add_conditional_edges(
        "pr_creator", route_after_pr_creator, {"finalize": "finalize", "remediation": "remediation"}
    )
    graph.add_edge("remediation", "finalize")
    graph.add_edge("finalize", END)
    return graph


# Loops are bounded by MAX_INVESTIGATION_ROUNDS and MAX_FIX_ATTEMPTS; the
# recursion limit is a safety net far above the longest legitimate path.
RECURSION_LIMIT = 60

incident_graph = build_graph().compile()
logger.debug("Incident pipeline graph compiled.")
