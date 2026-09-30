"""Agents: output parsing, the self-repair turn, per-agent model routing and retry classification."""

from __future__ import annotations

import asyncio

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.agents import FixEngineerAgent, InvestigatorAgent, RemediationAgent, ReviewerAgent, TriageAgent
from app.core import llm
from app.core.config import get_settings
from app.core.errors import AgentOutputError, LLMError

EVENT = {
    "error_type": "KeyError",
    "error_message": "'user_id'",
    "platform": "python",
    "frames": [{"filename": "app/views.py", "lineno": 2, "function": "get", "context_line": "user = s['user_id']"}],
}


@pytest.fixture()
def scripted_llm(monkeypatch):
    """Replace the provider call with scripted replies (everything else runs for real)."""

    def _script(*replies: str) -> FakeListChatModel:
        model = FakeListChatModel(responses=list(replies))
        monkeypatch.setattr(llm, "get_chat_model", lambda spec: model)
        return model

    return _script


def test_triage_parses_and_normalises_choices(scripted_llm):
    scripted_llm(
        "<category>Code Bug</category><severity>HIGH</severity><code_fixable>yes</code_fixable>"
        "<summary>Dashboard crashes for logged-out users.</summary><reasoning>KeyError on session.</reasoning>"
    )
    result = asyncio.run(TriageAgent().run(event=EVENT))
    assert result.output.category == "code_bug"
    assert result.output.severity == "high"
    assert result.output.code_fixable is True
    assert result.attempts == 1
    assert result.spec.label == "groq:openai/gpt-oss-120b"


def test_agent_repairs_a_malformed_reply_once(scripted_llm):
    scripted_llm(
        "Sure! It's a code bug.",  # no tags → repair turn
        "<category>code_bug</category><severity>low</severity><code_fixable>true</code_fixable><summary>s</summary>",
    )
    result = asyncio.run(TriageAgent().run(event=EVENT))
    assert result.attempts == 2 and result.output.category == "code_bug"


def test_agent_gives_up_after_the_repair_turn(scripted_llm):
    scripted_llm("nonsense", "still nonsense")
    with pytest.raises(AgentOutputError, match="Triage Agent returned an unusable response"):
        asyncio.run(TriageAgent().run(event=EVENT))


def test_investigator_parses_file_requests_and_percent_confidence(scripted_llm):
    scripted_llm(
        "<think>let me reason</think><root_cause>Missing guard</root_cause><explanation>Long text</explanation>"
        "<confidence>85%</confidence><code_fixable>true</code_fixable><culprit_file>`app/views.py`</culprit_file>"
        "<culprit_line>line 2</culprit_line><fix_strategy>Use .get()</fix_strategy>"
        "<needs_files><file>app/session.py</file><file>app/models.py:10</file></needs_files>"
    )
    result = asyncio.run(
        InvestigatorAgent().run(event=EVENT, triage=None, code_context={}, round_number=1, max_rounds=2, repo_connected=True)
    )
    out = result.output
    assert out.confidence == pytest.approx(0.85)
    assert out.culprit_file == "app/views.py" and out.culprit_line == 2
    assert out.needs_files == ["app/session.py", "app/models.py:10"]


def test_fix_engineer_parses_edits_and_restores_neutralised_code(scripted_llm):
    scripted_llm(
        "<summary>Handle missing user id</summary><rationale>Guard the lookup.</rationale><risk>low</risk>"
        "<edit><file_path>app/views.py</file_path><find_exact>\nuser = s['user_id']\n</find_exact>"
        "<replace_with>\nuser = s.get('user_id')  # ‹summary› tag in JSX stays intact\n</replace_with></edit>"
    )
    result = asyncio.run(
        FixEngineerAgent().run(
            event=EVENT, investigation={"root_cause": "x", "explanation": "y"}, code_context={},
            attempt=1, max_attempts=3, feedback=[], previous_diff=None,
        )
    )
    edit = result.output.edits[0]
    assert edit.path == "app/views.py"
    assert "user = s['user_id']" in edit.find_exact
    assert "<summary>" in edit.replace_with


def test_fix_engineer_can_decline(scripted_llm):
    scripted_llm("<cannot_fix>The value comes from a missing environment variable.</cannot_fix>")
    result = asyncio.run(
        FixEngineerAgent().run(
            event=EVENT, investigation={}, code_context={}, attempt=1, max_attempts=3, feedback=[], previous_diff=None
        )
    )
    assert result.output.edits == [] and "environment variable" in result.output.cannot_fix


def test_reviewer_requires_instructions_for_revise(scripted_llm):
    scripted_llm(
        "<verdict>revise</verdict><confidence>0.5</confidence><summary>Close.</summary>",
        "<verdict>revise</verdict><confidence>0.5</confidence><summary>Close.</summary>"
        "<issues><issue>Handles None but not empty string</issue></issues>",
    )
    result = asyncio.run(
        ReviewerAgent().run(
            event=EVENT, investigation={}, fix={}, diff="--- a/x\n+++ b/x", code_context={},
            automated_checks=[], attempt=1, max_attempts=3,
        )
    )
    assert result.output.verdict == "revise" and result.output.issues == ["Handles None but not empty string"]


def test_remediation_accepts_numbered_list_fallback(scripted_llm):
    scripted_llm("<summary>DB is down.</summary><steps>\n1. Check RDS status\n2. Fail over\n</steps>")
    result = asyncio.run(
        RemediationAgent().run(event=EVENT, triage=None, investigation=None, flag_reason="infra", suggested_diff=None)
    )
    assert result.output.steps == ["Check RDS status", "Fail over"]


def test_per_agent_model_overrides(monkeypatch):
    monkeypatch.setenv("AGENT_FIX_ENGINEER_PROVIDER", "openai")
    monkeypatch.setenv("AGENT_FIX_ENGINEER_MODEL", "gpt-4.1")
    monkeypatch.setenv("AGENT_REVIEWER_TEMPERATURE", "0")
    get_settings.cache_clear()
    monkeypatch.setattr(llm, "settings", get_settings())
    try:
        assert llm.resolve_model_spec("fix_engineer").label == "openai:gpt-4.1"
        assert llm.resolve_model_spec("reviewer").temperature == 0.0
        assert llm.resolve_model_spec("triage").label == "groq:openai/gpt-oss-120b"
    finally:
        get_settings.cache_clear()


def test_retry_classification():
    class RateLimited(Exception):
        status_code = 429

    class BadRequest(Exception):
        status_code = 400

    assert llm._classify(RateLimited())[0] is True
    assert llm._classify(BadRequest())[0] is False
    assert llm._classify(TimeoutError())[0] is True


def test_transient_failures_are_retried_then_reported_retryable(monkeypatch):
    class Flaky:
        calls = 0

        async def ainvoke(self, messages):
            Flaky.calls += 1
            raise ConnectionError("network down")

    monkeypatch.setattr(llm, "get_chat_model", lambda spec: Flaky())
    monkeypatch.setattr(llm, "_backoff", lambda attempt, hint: 0)
    with pytest.raises(LLMError) as info:
        asyncio.run(llm.invoke_llm(llm.resolve_model_spec("triage"), []))
    assert info.value.retryable is True and Flaky.calls == 2  # LLM_MAX_ATTEMPTS=2 in tests
