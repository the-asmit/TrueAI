"""
End-to-end pipeline runs against the real database (PostgREST + Postgres with
the production migration) and Redis.  Only the LLM replies are scripted and
GitHub is an in-memory repository (tests/helpers.py).
"""

from __future__ import annotations

import asyncio
import copy
import uuid

import pytest

from app.pipelines.incident_pipeline import run_incident_pipeline
from app.services.sentry_events import frames_for_storage, normalize_event, payload_for_storage
from tests.helpers import (
    DASHBOARD_SOURCE,
    FIX_GOOD,
    FIX_WRONG_ANCHOR,
    REMEDIATION,
    REVIEW_APPROVE,
    REVIEW_REVISE,
    SENTRY_EVENT,
    TRIAGE_CODE_BUG,
    TRIAGE_CONFIG,
    GitHubDouble,
    investigation,
    script_llm,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def incident(db, make_user, redis_clean):
    """A queued incident exactly as the webhook would store it, with a default repository mapping."""
    user_id = make_user()
    db.save_repo_mapping(user_id, None, "acme/shop", "main")
    payload = copy.deepcopy(SENTRY_EVENT)
    payload["event_id"] = uuid.uuid4().hex
    event = normalize_event(payload)
    incident_id = str(uuid.uuid4())
    db.create_incident(
        {
            "id": incident_id,
            "user_id": user_id,
            "sentry_event_id": event["event_id"],
            "fingerprint": event["fingerprint"],
            "error_type": event["error_type"],
            "error_message": event["error_message"],
            "status": "queued",
            "raw_payload": payload_for_storage(payload),
            "stack_trace": frames_for_storage(event["frames"]),
            "analysis_run": 1,
        }
    )
    return {"id": incident_id, "user_id": user_id}


def _run(incident_id: str) -> dict:
    return asyncio.run(run_incident_pipeline(incident_id))


def test_code_bug_goes_from_webhook_payload_to_reviewed_pull_request(db, incident, monkeypatch):
    github = GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE}).install(monkeypatch)
    script_llm(monkeypatch, TRIAGE_CODE_BUG, investigation(0.9), FIX_GOOD, REVIEW_APPROVE)

    result = _run(incident["id"])

    assert result["status"] == "pr_open"
    row = db.get_incident(incident["id"], incident["user_id"])
    assert row["status"] == "pr_open"
    assert row["issue_classification"] == "code_bug" and row["severity"] == "high"
    assert row["repo_full_name"] == "acme/shop" and row["current_step"] is None
    assert row["confidence"] == pytest.approx(0.9)

    # The PR carries the patch engine's real diff on top of the analysed commit.
    opened = github.opened[0]
    assert opened["base_sha"].startswith("0123456789")
    assert opened["head_branch"] == f"trueai/fix-{incident['id'][:8]}"
    assert "request.session.get('user_id')" in opened["files"]["app/views/dashboard.py"]
    assert "@" not in opened["body"].replace("@​", "")  # no live @mentions in the PR body

    fix = db.get_latest_fix(incident["id"])
    assert fix["status"] == "applied" and fix["validation_passed"] is True
    assert fix["review_verdict"] == "approve" and fix["fix_confidence"] == pytest.approx(0.92)
    assert "+    if user_id is None:" in fix["fix_diff"]
    assert fix["files_changed"] == ["app/views/dashboard.py"]

    pr = db.get_pull_request_for_incident(incident["id"])
    assert pr["pr_number"] == 41 and pr["status"] == "open" and pr["fix_id"] == fix["id"]

    steps = [s["step"] for s in db.list_steps(incident["id"])]
    assert steps == ["parse", "triage", "context", "investigator", "fix_engineer", "patch", "reviewer", "decision", "publish", "complete"]


def test_reviewer_revision_loop_produces_a_second_attempt(db, incident, monkeypatch):
    GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE}).install(monkeypatch)
    script_llm(monkeypatch, TRIAGE_CODE_BUG, investigation(0.9), FIX_GOOD, REVIEW_REVISE, FIX_GOOD, REVIEW_APPROVE)

    assert _run(incident["id"])["status"] == "pr_open"
    agent_steps = [s["step"] for s in db.list_steps(incident["id"]) if s["kind"] == "agent"]
    assert agent_steps.count("fix_engineer") == 2 and agent_steps.count("reviewer") == 2


def test_fix_that_cannot_be_applied_is_retried_then_flagged_with_guidance(db, incident, monkeypatch):
    GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE}).install(monkeypatch)
    script_llm(monkeypatch, TRIAGE_CODE_BUG, investigation(0.9), FIX_WRONG_ANCHOR, FIX_WRONG_ANCHOR, FIX_WRONG_ANCHOR, REMEDIATION)

    assert _run(incident["id"])["status"] == "flagged"
    fix = db.get_latest_fix(incident["id"])
    assert fix["status"] == "not_applicable"
    assert "could not produce a change that applies cleanly" in fix["flag_reason"]
    assert fix["remediation"]["steps"][0].startswith("Set DATABASE_URL")


def test_configuration_issue_is_flagged_with_remediation_and_no_patch(db, incident, monkeypatch):
    github = GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE}).install(monkeypatch)
    script_llm(monkeypatch, TRIAGE_CONFIG, investigation(0.85, fixable=False), REMEDIATION)

    assert _run(incident["id"])["status"] == "flagged"
    assert github.opened == []
    row = db.get_incident(incident["id"], incident["user_id"])
    assert row["status"] == "flagged" and row["issue_classification"] == "config_issue"
    fix = db.get_latest_fix(incident["id"])
    assert fix["fix_diff"] == "" and fix["status"] == "not_applicable"
    assert len(fix["remediation"]["steps"]) == 2


def test_low_confidence_patch_is_kept_as_a_suggestion_instead_of_a_pr(db, incident, monkeypatch):
    github = GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE}).install(monkeypatch)
    script_llm(monkeypatch, TRIAGE_CODE_BUG, investigation(0.6), FIX_GOOD, REVIEW_APPROVE, REMEDIATION)

    assert _run(incident["id"])["status"] == "flagged"
    assert github.opened == []
    fix = db.get_latest_fix(incident["id"])
    assert fix["status"] == "pending" and "if user_id is None" in fix["fix_diff"]
    assert "below the 75% auto-PR threshold" in fix["flag_reason"]


def test_read_only_repository_access_never_opens_a_pr(db, incident, monkeypatch):
    github = GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE}, can_push=False).install(monkeypatch)
    script_llm(monkeypatch, TRIAGE_CODE_BUG, investigation(0.95), FIX_GOOD, REVIEW_APPROVE, REMEDIATION)

    assert _run(incident["id"])["status"] == "flagged"
    assert github.opened == []
    assert "cannot push" in db.get_latest_fix(incident["id"])["flag_reason"]


def test_without_github_the_incident_still_gets_a_diagnosis(db, incident, monkeypatch):
    GitHubDouble({}, connected=False).install(monkeypatch)
    script_llm(monkeypatch, TRIAGE_CODE_BUG, investigation(0.7), REMEDIATION)

    assert _run(incident["id"])["status"] == "flagged"
    fix = db.get_latest_fix(incident["id"])
    assert fix["root_cause"].startswith("get_dashboard indexes")
    assert "GitHub is not connected" in fix["flag_reason"]


def test_investigator_file_request_triggers_a_second_round(db, incident, monkeypatch):
    GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE, "app/auth/session.py": "def current_user(r):\n    return None\n"}).install(monkeypatch)
    script_llm(
        monkeypatch,
        TRIAGE_CODE_BUG,
        investigation(0.6, needs="<file>app/auth/session.py</file>"),
        investigation(0.9),
        FIX_GOOD,
        REVIEW_APPROVE,
    )
    assert _run(incident["id"])["status"] == "pr_open"
    steps = db.list_steps(incident["id"])
    assert [s["step"] for s in steps].count("investigator") == 2
    assert any("app/auth/session.py" in (s["summary"] or "") for s in steps if s["step"] == "context")


def test_provider_outage_fails_as_retryable(db, incident, monkeypatch):
    from app.core import llm

    GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE}).install(monkeypatch)

    class Down:
        async def ainvoke(self, messages):
            raise ConnectionError("provider unreachable")

    monkeypatch.setattr(llm, "get_chat_model", lambda spec: Down())
    monkeypatch.setattr(llm, "_backoff", lambda attempt, hint: 0)

    result = _run(incident["id"])
    assert result["status"] == "failed" and result["error_retryable"] is True
    row = db.get_incident(incident["id"], incident["user_id"])
    assert row["status"] == "failed" and "unavailable" in row["pipeline_error"]


def test_duplicate_delivery_of_a_finished_incident_is_skipped(db, incident, monkeypatch):
    GitHubDouble({"app/views/dashboard.py": DASHBOARD_SOURCE}).install(monkeypatch)
    script_llm(monkeypatch, TRIAGE_CODE_BUG, investigation(0.9), FIX_GOOD, REVIEW_APPROVE)
    assert _run(incident["id"])["status"] == "pr_open"
    assert _run(incident["id"])["status"] == "skipped"
