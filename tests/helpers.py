"""
Test doubles for the two external network boundaries: the LLM provider and GitHub.

Everything else in the integration tests is real (Supabase client →
PostgREST → Postgres with the production migration, Redis, the LangGraph
pipeline, the patch engine and the API).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Dict, List, Optional

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.core import llm
from app.services.github.client import GitHubConnection
from app.services.github.fetcher import RepoSnapshot, SourceFile
from app.services.github.pr import PullRequestResult


def script_llm(monkeypatch, *replies: str) -> FakeListChatModel:
    """Every agent call returns the next scripted reply, in order."""
    model = FakeListChatModel(responses=list(replies))
    monkeypatch.setattr(llm, "get_chat_model", lambda spec: model)
    return model


@dataclass
class GitHubDouble:
    files: Dict[str, str]
    can_push: bool = True
    connected: bool = True
    opened: List[dict] = field(default_factory=list)
    pr_number: int = 41

    def install(self, monkeypatch) -> "GitHubDouble":
        import app.nodes.context as context_node
        import app.nodes.pr_creator as pr_node

        def load_connection(user_id: str) -> Optional[GitHubConnection]:
            return GitHubConnection(token="gho_test_token", username="alice") if self.connected else None

        def open_snapshot(token, repo_full_name, branch, *, pinned=None):
            snapshot = RepoSnapshot(
                repo_full_name=repo_full_name, branch=branch or "main", default_branch="main",
                sha="0123456789abcdef0123456789abcdef01234567", paths=sorted(self.files),
            )
            snapshot.modes = {path: "100644" for path in self.files}
            snapshot._repo = SimpleNamespace(permissions=SimpleNamespace(push=self.can_push, admin=False))
            snapshot.index()
            return snapshot

        def read_file(snapshot, path):
            return SourceFile(path=path, content=self.files[path]) if path in self.files else None

        def open_fix_pull_request(**kwargs) -> PullRequestResult:
            self.opened.append(kwargs)
            return PullRequestResult(
                url=f"https://github.com/{kwargs['repo_full_name']}/pull/{self.pr_number}",
                number=self.pr_number,
                branch=kwargs["head_branch"],
                reused=False,
            )

        for module in (context_node, pr_node):
            monkeypatch.setattr(module, "load_connection", load_connection)
        monkeypatch.setattr(context_node, "open_snapshot", open_snapshot)
        monkeypatch.setattr(context_node, "read_file", read_file)
        monkeypatch.setattr(pr_node, "open_fix_pull_request", open_fix_pull_request)
        return self


# ------------------------------------------------------------------ #
# Scripted agent replies                                               #
# ------------------------------------------------------------------ #

TRIAGE_CODE_BUG = (
    "<category>code_bug</category><severity>high</severity><code_fixable>true</code_fixable>"
    "<summary>Dashboard crashes when the session has no user id.</summary><reasoning>KeyError on session lookup.</reasoning>"
)
TRIAGE_CONFIG = (
    "<category>config_issue</category><severity>critical</severity><code_fixable>false</code_fixable>"
    "<summary>DATABASE_URL is missing in production.</summary><reasoning>KeyError on os.environ.</reasoning>"
)


def investigation(confidence: float = 0.9, fixable: bool = True, needs: str = "") -> str:
    return (
        "<root_cause>get_dashboard indexes session['user_id'] without checking the user is signed in.</root_cause>"
        "<explanation>Anonymous requests reach get_dashboard; the session has no user_id key, so the lookup raises KeyError.</explanation>"
        f"<confidence>{confidence}</confidence><code_fixable>{str(fixable).lower()}</code_fixable>"
        "<culprit_file>app/views/dashboard.py</culprit_file><culprit_line>5</culprit_line>"
        "<fix_strategy>Return a redirect to login when user_id is absent.</fix_strategy>"
        f"<needs_files>{needs}</needs_files>"
    )


FIX_GOOD = (
    "<summary>Redirect anonymous users away from the dashboard</summary>"
    "<rationale>Guards the session lookup so anonymous requests are redirected instead of crashing.</rationale>"
    "<risk>low</risk>"
    "<edit><file_path>app/views/dashboard.py</file_path>\n<find_exact>\n    user_id = request.session['user_id']\n</find_exact>\n"
    "<replace_with>\n    user_id = request.session.get('user_id')\n    if user_id is None:\n        return redirect('/login')\n</replace_with></edit>"
)
FIX_WRONG_ANCHOR = (
    "<summary>Guard session</summary><rationale>r</rationale><risk>low</risk>"
    "<edit><file_path>app/views/dashboard.py</file_path><find_exact>this line does not exist</find_exact>"
    "<replace_with>x = 1</replace_with></edit>"
)
REVIEW_APPROVE = (
    "<verdict>approve</verdict><confidence>0.92</confidence>"
    "<summary>Correct, minimal guard; anonymous users are redirected.</summary><issues></issues>"
)
REVIEW_REVISE = (
    "<verdict>revise</verdict><confidence>0.6</confidence><summary>Also handle an empty user id.</summary>"
    "<issues><issue>An empty string user id still reaches the query.</issue></issues>"
    "<revision_instructions>Treat falsy user ids like missing ones.</revision_instructions>"
)
REMEDIATION = (
    "<summary>Production is missing DATABASE_URL.</summary>"
    "<steps><step>Set DATABASE_URL in the production environment.</step><step>Redeploy the web service.</step></steps>"
    "<verification>Load /dashboard in production.</verification><prevention>Validate settings at start-up.</prevention>"
)

DASHBOARD_SOURCE = (
    "from django.shortcuts import redirect, render\n"
    "\n"
    "\n"
    "def get_dashboard(request):\n"
    "    user_id = request.session['user_id']\n"
    "    return render(request, 'dashboard.html', {'user_id': user_id})\n"
)

SENTRY_EVENT = {
    "event_id": "5f1c0a5b2c7e4a9d8e7f6a5b4c3d2e1f",
    "platform": "python",
    "environment": "production",
    "level": "error",
    "culprit": "app.views.dashboard in get_dashboard",
    "exception": {
        "values": [
            {
                "type": "KeyError",
                "value": "'user_id'",
                "stacktrace": {
                    "frames": [
                        {"filename": "django/core/handlers/base.py", "lineno": 197, "function": "_get_response", "in_app": False},
                        {
                            "filename": "app/views/dashboard.py",
                            "abs_path": "/srv/app/app/views/dashboard.py",
                            "lineno": 5,
                            "function": "get_dashboard",
                            "in_app": True,
                            "context_line": "    user_id = request.session['user_id']",
                        },
                    ]
                },
            }
        ]
    },
}
