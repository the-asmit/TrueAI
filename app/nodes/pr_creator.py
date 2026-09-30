"""
PR creator node — commits the reviewed patch and opens a GitHub pull request.

Reads:
    incident_id, user_id, repo, patch, source_files, fix, investigation, review, event

Writes (success):
    pr = {url, number, branch}
Writes (failure):
    action = "flag_for_review", flag_reason   (the patch stays on the incident as a suggestion)

The commit is created on top of the exact commit the agents analysed
(``repo.sha``) as a single atomic commit, on the branch
``trueai/fix-<incident id prefix>``.  Retries and re-analysis reuse the same
branch and PR, so an incident never produces duplicate pull requests.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict

from app.core.config import settings
from app.core.errors import GitHubError
from app.core.logging import get_logger
from app.core.security import md_code_block, md_inline, md_paragraph
from app.core.state import IncidentState, failure
from app.pipelines.timeline import record_step, set_current_step
from app.services import supabase as db
from app.services.github.client import load_connection
from app.services.github.pr import PullRequestResult, open_fix_pull_request

logger = get_logger(__name__)

_BRANCH_PREFIX = "trueai/fix-"


async def pr_creator_node(state: IncidentState) -> Dict[str, Any]:
    incident_id = state["incident_id"]
    repo = state.get("repo") or {}
    patch = state.get("patch") or {}
    fix = state.get("fix") or {}
    started = time.perf_counter()
    await set_current_step(state, "Opening the pull request")

    connection = await asyncio.to_thread(load_connection, state["user_id"])
    if connection is None:
        return await _flag(state, "GitHub was disconnected before the pull request could be opened.")

    source_files = state.get("source_files") or {}
    title = _pr_title(fix.get("summary") or f"Fix {state.get('event', {}).get('error_type', 'error')}")
    branch = f"{_BRANCH_PREFIX}{incident_id[:8]}"
    try:
        result = await asyncio.to_thread(
            open_fix_pull_request,
            access_token=connection.token,
            repo_full_name=repo["full_name"],
            base_branch=repo["branch"],
            base_sha=repo["sha"],
            head_branch=branch,
            files=patch["files"],
            file_modes={path: (source_files.get(path) or {}).get("mode", "100644") for path in patch["files"]},
            commit_message=_commit_message(title, state),
            title=title,
            body=_pr_body(state),
            draft=settings.PR_AS_DRAFT,
            label=settings.PR_LABEL or None,
        )
    except GitHubError as exc:
        await record_step(state, step="publish", kind="tool", status="error", summary=str(exc))
        if exc.retryable:
            return failure(f"GitHub was unavailable while opening the pull request: {exc}", retryable=True)
        return await _flag(state, f"The pull request could not be opened: {exc}")

    # ---- Persist (update the existing record on re-analysis) --------- #
    record = {
        "incident_id": incident_id,
        "pr_url": result.url,
        "pr_number": result.number,
        "branch_name": result.branch,
        "repo_full_name": repo["full_name"],
        "title": title,
        "status": "open",
    }
    try:
        existing = await asyncio.to_thread(db.get_pull_request_for_incident, incident_id)
        if existing and existing.get("pr_number") == result.number and existing.get("repo_full_name") in (None, repo["full_name"]):
            await asyncio.to_thread(db.update_pull_request, existing["id"], record)
        else:
            await asyncio.to_thread(db.create_pull_request_record, record)
    except Exception as exc:
        # The PR exists on GitHub; losing the DB row must not hide that from the user.
        logger.error("pr_creator_node: PR record not saved | incident_id=%s | error=%s", incident_id, exc)

    await record_step(
        state,
        step="publish",
        kind="tool",
        status="ok",
        summary=_publish_summary(result, repo["full_name"]),
        detail={"url": result.url, "branch": result.branch},
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return {"pr": {"url": result.url, "number": result.number, "branch": result.branch}}


def _publish_summary(result: PullRequestResult, repo_full_name: str) -> str:
    if not result.reused:
        return f"Opened pull request #{result.number} on {repo_full_name}"
    if result.updated:
        return f"Pushed the revised fix to the open pull request #{result.number} on {repo_full_name}"
    return f"Pull request #{result.number} on {repo_full_name} already contains this fix"


async def _flag(state: IncidentState, reason: str) -> Dict[str, Any]:
    await record_step(state, step="publish", kind="tool", status="warning", summary=reason)
    return {"action": "flag_for_review", "flag_reason": reason + " The patch is attached as a suggestion."}


# ================================================================== #
# Commit & PR text                                                     #
# ================================================================== #

def _pr_title(summary: str) -> str:
    title = re.sub(r"\s+", " ", summary).strip().rstrip(".")
    return (title[:1].upper() + title[1:])[:72] or "Fix production error"


def _commit_message(title: str, state: IncidentState) -> str:
    investigation = state.get("investigation") or {}
    root_cause = re.sub(r"\s+", " ", investigation.get("root_cause") or "").strip()
    return (
        f"{title}\n\n"
        f"Root cause: {root_cause[:500]}\n\n"
        f"Automated fix proposed by TrueAI for incident {state['incident_id']}."
    )


def _pr_body(state: IncidentState) -> str:
    event = state.get("event") or {}
    investigation = state.get("investigation") or {}
    review = state.get("review") or {}
    fix = state.get("fix") or {}
    patch = state.get("patch") or {}
    triage = state.get("triage") or {}
    dashboard_url = f"{settings.FRONTEND_URL}/dashboard/incidents/{state['incident_id']}"

    lines = [
        "## Automated fix proposed by TrueAI",
        "",
        "> [!IMPORTANT]",
        "> This change was written and reviewed by AI agents. Review it like any other contribution before merging.",
        "",
        "| | |",
        "|---|---|",
        f"| **Error** | {md_inline(event.get('error_type') or 'Error', max_len=120)} |",
        f"| **Environment** | {md_inline(event.get('environment') or 'unknown', max_len=60)} |",
        f"| **Category** | {md_inline((triage.get('category') or 'unknown').replace('_', ' '))} · {md_inline(triage.get('severity') or '')} severity |",
        f"| **Root-cause confidence** | {float(investigation.get('confidence') or 0):.0%} |",
        f"| **Review confidence** | {float(review.get('confidence') or 0):.0%} |",
        f"| **Risk (self-assessed)** | {md_inline(fix.get('risk') or 'unknown')} |",
        f"| **Incident** | [{state['incident_id'][:8]}]({dashboard_url}) |",
    ]
    if event.get("issue_url"):
        lines.append(f"| **Sentry issue** | [{md_inline(event.get('issue_id') or 'open', max_len=40)}]({event['issue_url']}) |")
    lines += [
        "",
        "### Error message",
        md_code_block(event.get("error_message") or "(no message)", max_len=1500),
        "",
        "### Root cause",
        md_paragraph(investigation.get("root_cause") or ""),
        "",
        "### Explanation",
        md_paragraph(investigation.get("explanation") or ""),
        "",
        "### What this change does",
        md_paragraph(fix.get("rationale") or fix.get("summary") or ""),
        "",
        "### Automated review",
        md_paragraph(review.get("summary") or ""),
    ]
    if review.get("issues"):
        lines.append("")
        lines += [f"- {md_paragraph(issue, max_len=400)}" for issue in review["issues"][:6]]
    lines += [
        "",
        "### Files changed",
        *[f"- `{md_inline(path, max_len=200)}`" for path in patch.get("files_changed") or []],
        "",
        "---",
        "<sub>Opened by TrueAI. Close this pull request to dismiss the fix; the incident will return to the review queue.</sub>",
    ]
    return "\n".join(lines)[:60_000]
