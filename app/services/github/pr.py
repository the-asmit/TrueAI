"""
Pull request creation and status tracking.

``open_fix_pull_request`` commits every changed file in ONE commit using the
Git Data API (tree → commit → ref) on top of the exact commit the agents
analysed, then opens the pull request.  Each incident has one branch:

- no open PR yet → the branch is created (or reset, if a previous attempt left
  one behind) and the PR is opened;
- a PR is already open (re-analysis) → the revised fix is pushed to it as a
  normal new commit on top of the branch, never a force-push, so anything
  already on the branch stays in its history.

``get_pull_request_state`` powers merge tracking — the worker periodically
syncs open PRs so incidents move to ``resolved`` when their fix is merged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from github import GithubException, InputGitTreeElement

from app.core.errors import GitHubError
from app.core.logging import get_logger
from app.services.github.client import get_repository, to_github_error

logger = get_logger(__name__)


@dataclass(frozen=True)
class PullRequestResult:
    url: str
    number: int
    branch: str
    reused: bool  # the incident's PR was already open
    updated: bool = False  # ...and the revised fix was pushed to it


def open_fix_pull_request(
    *,
    access_token: str,
    repo_full_name: str,
    base_branch: str,
    base_sha: str,
    head_branch: str,
    files: Dict[str, str],
    file_modes: Dict[str, str],
    commit_message: str,
    title: str,
    body: str,
    draft: bool,
    label: Optional[str],
) -> PullRequestResult:
    """Commit *files* (path → full new content) on a new branch and open a PR."""
    if not files:
        raise GitHubError("Refusing to open a pull request with no file changes.", status=400)

    repo = get_repository(access_token, repo_full_name)
    owner = repo_full_name.split("/")[0]

    # ---- The incident's PR is already open: push the revised fix to it --- #
    try:
        existing = list(repo.get_pulls(state="open", head=f"{owner}:{head_branch}"))
    except Exception as exc:
        raise to_github_error(exc, "check for an existing pull request") from exc
    if existing:
        pr = existing[0]
        updated = _push_to_open_branch(repo, head_branch, files, file_modes, commit_message)
        logger.info("Existing PR #%d for branch %s | revised fix pushed=%s", pr.number, head_branch, updated)
        return PullRequestResult(url=pr.html_url, number=pr.number, branch=head_branch, reused=True, updated=updated)

    # ---- Single atomic commit on top of the analysed commit ---------- #
    try:
        base_commit = repo.get_git_commit(base_sha)
        elements = [
            InputGitTreeElement(path=path, mode=file_modes.get(path, "100644"), type="blob", content=content)
            for path, content in sorted(files.items())
        ]
        tree = repo.create_git_tree(elements, base_tree=base_commit.tree)
        commit = repo.create_git_commit(commit_message, tree, [base_commit])
    except Exception as exc:
        raise to_github_error(exc, "create the fix commit") from exc

    try:
        repo.create_git_ref(ref=f"refs/heads/{head_branch}", sha=commit.sha)
    except GithubException as exc:
        if exc.status != 422:
            raise to_github_error(exc, "create the fix branch") from exc
        # Branch left over from a previous attempt of this incident: move it.
        try:
            repo.get_git_ref(f"heads/{head_branch}").edit(sha=commit.sha, force=True)
        except Exception as edit_exc:
            raise to_github_error(edit_exc, "update the fix branch") from edit_exc
    except Exception as exc:
        raise to_github_error(exc, "create the fix branch") from exc

    # ---- Pull request ------------------------------------------------ #
    pr = None
    try:
        pr = repo.create_pull(
            base=base_branch, head=head_branch, title=title, body=body, draft=draft, maintainer_can_modify=True
        )
    except GithubException as exc:
        message = str(exc.data.get("message") if isinstance(exc.data, dict) else exc.data or "")
        errors = str(exc.data.get("errors") if isinstance(exc.data, dict) else "")
        if exc.status == 422 and "already exists" in (message + errors):
            found = list(repo.get_pulls(state="open", head=f"{owner}:{head_branch}"))
            if found:
                pr = found[0]
        elif exc.status == 422 and draft and "draft" in (message + errors).lower():
            # Draft PRs are not available on every plan — fall back to a normal PR.
            try:
                pr = repo.create_pull(base=base_branch, head=head_branch, title=title, body=body, maintainer_can_modify=True)
            except Exception as retry_exc:
                raise to_github_error(retry_exc, "open the pull request") from retry_exc
        if pr is None:
            raise to_github_error(exc, "open the pull request") from exc
    except Exception as exc:
        raise to_github_error(exc, "open the pull request") from exc

    if label:
        try:
            pr.add_to_labels(label)
        except Exception as exc:  # labels are cosmetic
            logger.info("Could not label PR #%d: %s", pr.number, type(exc).__name__)

    logger.info("Opened PR #%d on %s (branch %s).", pr.number, repo_full_name, head_branch)
    return PullRequestResult(url=pr.html_url, number=pr.number, branch=head_branch, reused=False)


def _push_to_open_branch(repo, head_branch: str, files: Dict[str, str], file_modes: Dict[str, str], commit_message: str) -> bool:
    """
    Commit *files* on top of the branch's current head (a fast-forward, no
    force).  Returns False when the branch already has exactly these contents.
    """
    try:
        head = repo.get_git_commit(repo.get_branch(head_branch).commit.sha)
        elements = [
            InputGitTreeElement(path=path, mode=file_modes.get(path, "100644"), type="blob", content=content)
            for path, content in sorted(files.items())
        ]
        tree = repo.create_git_tree(elements, base_tree=head.tree)
        if tree.sha == head.tree.sha:
            return False
        commit = repo.create_git_commit(commit_message, tree, [head])
        repo.get_git_ref(f"heads/{head_branch}").edit(sha=commit.sha, force=False)
        return True
    except Exception as exc:
        raise to_github_error(exc, "push the revised fix to the open pull request") from exc


def get_pull_request_state(access_token: str, repo_full_name: str, number: int) -> Dict[str, Optional[str]]:
    """Return ``{"status": open|merged|closed, "merged_at": iso|None, "closed_at": iso|None}``."""
    repo = get_repository(access_token, repo_full_name)
    try:
        pr = repo.get_pull(number)
    except Exception as exc:
        raise to_github_error(exc, f"read pull request #{number}") from exc
    if pr.merged:
        status = "merged"
    elif pr.state == "closed":
        status = "closed"
    else:
        status = "open"
    return {
        "status": status,
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
        "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
    }
