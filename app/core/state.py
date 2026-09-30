"""
LangGraph shared state for the TrueAI incident pipeline.

Nodes return *partial* updates (only the keys they produce); LangGraph merges
them into the running state.  Every key is optional (``total=False``) — a key
that is absent simply means "that stage has not produced it yet", so nodes
always read with ``state.get(...)``.

Field groups follow pipeline order and double as documentation of the data
flow between agents and tools.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class IncidentState(TypedDict, total=False):
    # ---- Bootstrap (set by the pipeline runner) ------------------------ #
    incident_id: str
    user_id: str
    run: int                              # analysis run number (re-analysis increments it)
    raw_payload: Dict[str, Any]           # scrubbed Sentry payload as stored on the incident

    # ---- Parse (tool) --------------------------------------------------- #
    event: Dict[str, Any]                 # normalised event (see app.services.sentry_events)

    # ---- Triage Agent --------------------------------------------------- #
    triage: Dict[str, Any]                # category, severity, code_fixable, summary, reasoning

    # ---- Source context (tool) ------------------------------------------ #
    repo: Optional[Dict[str, Any]]        # {full_name, branch, default_branch, sha} or None
    repo_note: str                        # why source code is unavailable, when it is
    can_push: bool                        # token may push to the repository
    source_files: Dict[str, Dict[str, Any]]   # path → {"content", "mode"} (full files, editable)
    code_context: Dict[str, Dict[str, Any]]   # path → {"excerpt", "language", "total_lines", "reason"}
    pending_file_requests: List[str]      # files the Investigator asked for

    # ---- Investigator Agent --------------------------------------------- #
    investigation: Dict[str, Any]         # root_cause, explanation, confidence, fix_strategy, ...
    investigation_rounds: int

    # ---- Fix Engineer Agent + patch engine ------------------------------ #
    fix: Dict[str, Any]                   # summary, rationale, risk, edits | cannot_fix
    fix_attempts: int
    fix_feedback: List[str]               # patch errors / reviewer instructions for the next attempt
    patch: Dict[str, Any]                 # diff, files_changed, files (new contents), added, removed
    last_diff: str                        # most recent diff (kept across revisions, shown if no PR)
    policy_violations: List[str]
    check_notes: List[str]                # automated check results shown to the Reviewer

    # ---- Reviewer Agent -------------------------------------------------- #
    review: Dict[str, Any]                # verdict, confidence, summary, issues, revision_instructions

    # ---- Decision / publish ---------------------------------------------- #
    action: str                           # "create_pr" | "flag_for_review"
    flag_reason: str                      # why a human is needed (shown to user + Remediation Agent)
    pr: Dict[str, Any]                    # {url, number, branch}

    # ---- Remediation Agent ----------------------------------------------- #
    remediation: Dict[str, Any]           # summary, steps, verification, prevention

    # ---- Outcome & accounting -------------------------------------------- #
    status: str                           # processing | pr_open | flagged | failed
    error: str                            # set when status == "failed"
    error_retryable: bool                 # True when a retry may succeed (provider outage, etc.)
    usage: Dict[str, int]                 # accumulated LLM input/output tokens


# Values persisted to incidents.issue_classification.
ISSUE_CLASSIFICATIONS = frozenset({"code_bug", "config_issue", "infrastructure", "data_issue", "dependency"})

# Terminal pipeline statuses written to incidents.status.
FINAL_STATUSES = frozenset({"pr_open", "flagged", "failed"})


def make_initial_state(*, incident_id: str, user_id: str, raw_payload: Dict[str, Any], run: int = 1) -> IncidentState:
    """Minimal bootstrap state; every other key is produced by the nodes."""
    return IncidentState(
        incident_id=incident_id,
        user_id=user_id,
        run=run,
        raw_payload=raw_payload,
        status="processing",
        usage={"input_tokens": 0, "output_tokens": 0},
        investigation_rounds=0,
        fix_attempts=0,
        fix_feedback=[],
        pending_file_requests=[],
    )


def add_usage(state: IncidentState, input_tokens: int, output_tokens: int) -> Dict[str, int]:
    usage = dict(state.get("usage") or {})
    usage["input_tokens"] = int(usage.get("input_tokens", 0)) + int(input_tokens)
    usage["output_tokens"] = int(usage.get("output_tokens", 0)) + int(output_tokens)
    return usage


def failure(message: str, *, retryable: bool = False) -> Dict[str, Any]:
    """Partial update that ends the pipeline as failed."""
    return {"status": "failed", "error": message[:1000], "error_retryable": retryable}
