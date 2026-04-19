"""
LangGraph StateGraph construction and compilation for TrueAI.

Graph topology
──────────────
parser → dedup → classifier → context → root_cause → fix_generator
       → validator → decision → pr_creator → END

Early-exit edges (→ END) are inserted after every node that can fail or
produce a terminal result:

    parser        status == "failed"         → END
    dedup         status == "duplicate"       → END
    context       status == "failed"          → END
    root_cause    status == "failed"          → END
                  action == "flag_for_review" → END   (low confidence)
    fix_generator status == "failed"          → END
                  action == "flag_for_review" → END   (unfixable category)
    validator     status == "failed"          → END

    classifier and decision always advance to the next node.
    pr_creator always advances to END.

Design rules applied throughout:
    1. All routing functions use state.get() — never state["key"].
       TypedDict fields are optional (total=False); direct access raises
       KeyError on absent keys, breaking the graph.
    2. Routing functions are named and documented — no anonymous lambdas.
       Named functions surface clearly in LangGraph's Mermaid diagram output
       and in stack traces.
    3. The compiled graph is a module-level singleton (incident_graph).
       Import it wherever you need to invoke the pipeline — do not rebuild
       the graph per-request.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.core.logging import get_logger
from app.core.state import IncidentState
from app.nodes.classifier import classifier_node
from app.nodes.context import context_node
from app.nodes.decision import decision_node
from app.nodes.dedup import dedup_node
from app.nodes.fix_generator import fix_generator_node
from app.nodes.parser import parser_node
from app.nodes.pr_creator import pr_creator_node
from app.nodes.root_cause import root_cause_node
from app.nodes.validator import validator_node

logger = get_logger(__name__)


# ================================================================== #
# Routing functions                                                    #
#                                                                      #
# Each function receives the FULL state after a node completes and     #
# returns a string key that maps to the next node name or END.         #
# ALL field access uses state.get() to handle absent keys safely.      #
# ================================================================== #

def _route_after_parser(state: IncidentState) -> str:
    """
    Exit early if parsing failed (malformed payload, no user-code frames).
    Otherwise continue to deduplication.
    """
    if state.get("status") == "failed":
        logger.debug(
            "graph: parser → END (status=failed, error=%s)",
            state.get("error", ""),
        )
        return "end"
    return "continue"


def _route_after_dedup(state: IncidentState) -> str:
    """
    Exit early if this Sentry event has already been processed.
    Otherwise continue to classification.
    """
    if state.get("status") == "duplicate":
        logger.debug(
            "graph: dedup → END (status=duplicate, incident_id=%s)",
            state.get("incident_id", ""),
        )
        return "end"
    return "continue"


def _route_after_context(state: IncidentState) -> str:
    """
    Exit early if ALL GitHub file fetches failed (no source context available).
    Otherwise continue to root-cause analysis.
    """
    if state.get("status") == "failed":
        logger.debug(
            "graph: context → END (status=failed, error=%s)",
            state.get("error", ""),
        )
        return "end"
    return "continue"


def _route_after_root_cause(state: IncidentState) -> str:
    """
    Exit early on pipeline failure (LLM error, missing XML fields).
    Exit early when confidence is below the low threshold — the root-cause
    node has already set action="flag_for_review" in this case.
    Otherwise continue to fix generation.
    """
    if state.get("status") == "failed":
        logger.debug(
            "graph: root_cause → END (status=failed, error=%s)",
            state.get("error", ""),
        )
        return "end"
    if state.get("action") == "flag_for_review":
        logger.debug(
            "graph: root_cause → END (action=flag_for_review, "
            "confidence=%.3f)",
            state.get("confidence") or 0.0,
        )
        return "end"
    return "continue"


def _route_after_fix_generator(state: IncidentState) -> str:
    """
    Exit early on pipeline failure (LLM error, missing diff).
    Exit early when the issue classification is unfixable (config_issue,
    infrastructure) — fix_generator has already set action="flag_for_review".
    Otherwise continue to validation.
    """
    if state.get("status") == "failed":
        logger.debug(
            "graph: fix_generator → END (status=failed, error=%s)",
            state.get("error", ""),
        )
        return "end"
    if state.get("action") == "flag_for_review":
        logger.debug(
            "graph: fix_generator → END (action=flag_for_review, "
            "classification=%s)",
            state.get("issue_classification", ""),
        )
        return "end"
    return "continue"


def _route_after_validator(state: IncidentState) -> str:
    """
    Exit early on pipeline failure (unexpected LLM / network error).
    Validation failure itself (validation_passed=False) is NOT a pipeline
    failure — it is a normal outcome that continues to the decision node,
    which routes to flag_for_review.
    """
    if state.get("status") == "failed":
        logger.debug(
            "graph: validator → END (status=failed, error=%s)",
            state.get("error", ""),
        )
        return "end"
    return "continue"


# ================================================================== #
# Graph construction                                                   #
# ================================================================== #

def _build_graph() -> StateGraph:
    """
    Construct and return the compiled TrueAI incident pipeline graph.

    Kept in a factory function so the graph can be rebuilt in tests
    without module-level side effects being re-executed.
    """
    graph = StateGraph(IncidentState)

    # ---- Register nodes -------------------------------------------- #
    graph.add_node("parser",        parser_node)
    graph.add_node("dedup",         dedup_node)
    graph.add_node("classifier",    classifier_node)
    graph.add_node("context",       context_node)
    graph.add_node("root_cause",    root_cause_node)
    graph.add_node("fix_generator", fix_generator_node)
    graph.add_node("validator",     validator_node)
    graph.add_node("decision",      decision_node)
    graph.add_node("pr_creator",    pr_creator_node)

    # ---- Entry point ----------------------------------------------- #
    graph.set_entry_point("parser")

    # ---- parser: failed → END, else → dedup ----------------------- #
    graph.add_conditional_edges(
        "parser",
        _route_after_parser,
        {"end": END, "continue": "dedup"},
    )

    # ---- dedup: duplicate → END, else → classifier ---------------- #
    graph.add_conditional_edges(
        "dedup",
        _route_after_dedup,
        {"end": END, "continue": "classifier"},
    )

    # ---- classifier: always → context ----------------------------- #
    # The classifier is allowed to default (never fails the pipeline),
    # so there is no conditional edge here.
    graph.add_edge("classifier", "context")

    # ---- context: failed → END, else → root_cause ----------------- #
    graph.add_conditional_edges(
        "context",
        _route_after_context,
        {"end": END, "continue": "root_cause"},
    )

    # ---- root_cause: failed/flag → END, else → fix_generator ------ #
    graph.add_conditional_edges(
        "root_cause",
        _route_after_root_cause,
        {"end": END, "continue": "fix_generator"},
    )

    # ---- fix_generator: failed/flag → END, else → validator ------- #
    graph.add_conditional_edges(
        "fix_generator",
        _route_after_fix_generator,
        {"end": END, "continue": "validator"},
    )

    # ---- validator: failed → END, else → decision ----------------- #
    # Note: validation_passed=False routes to decision (not END) —
    # the decision node converts that into action="flag_for_review".
    graph.add_conditional_edges(
        "validator",
        _route_after_validator,
        {"end": END, "continue": "decision"},
    )

    # ---- decision: always → pr_creator ---------------------------- #
    # The decision node is pure logic and never fails.
    graph.add_edge("decision", "pr_creator")

    # ---- pr_creator: always → END --------------------------------- #
    graph.add_edge("pr_creator", END)

    return graph


# ================================================================== #
# Compiled singleton — import this to invoke the pipeline             #
# ================================================================== #

logger.info("Compiling TrueAI incident pipeline graph...")
incident_graph = _build_graph().compile()
logger.info("Incident pipeline graph compiled and ready.")
