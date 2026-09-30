"""Re-analysis of an incident whose pull request is already open: the revised fix is pushed to it, never force-pushed."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.github import pr as pr_module


class FakeRef:
    def __init__(self) -> None:
        self.edits: list[tuple[str, bool]] = []

    def edit(self, sha: str, force: bool = False) -> None:
        self.edits.append((sha, force))


class FakeRepo:
    """The slice of PyGithub's Repository that the open-PR path touches."""

    def __init__(self, *, head_tree: str, new_tree: str) -> None:
        self.head_tree = head_tree
        self.new_tree = new_tree
        self.ref = FakeRef()
        self.commits: list[tuple[str, list[str]]] = []

    def get_pulls(self, state: str, head: str):
        return [SimpleNamespace(number=412, html_url="https://github.com/acme/shop/pull/412")]

    def get_branch(self, name: str):
        return SimpleNamespace(commit=SimpleNamespace(sha="head-sha"))

    def get_git_commit(self, sha: str):
        return SimpleNamespace(sha=sha, tree=SimpleNamespace(sha=self.head_tree))

    def create_git_tree(self, elements, base_tree):
        return SimpleNamespace(sha=self.new_tree)

    def create_git_commit(self, message, tree, parents):
        self.commits.append((message, [parent.sha for parent in parents]))
        return SimpleNamespace(sha="new-commit")

    def get_git_ref(self, ref: str) -> FakeRef:
        return self.ref


def _open(monkeypatch, repo: FakeRepo) -> pr_module.PullRequestResult:
    monkeypatch.setattr(pr_module, "get_repository", lambda token, name: repo)
    return pr_module.open_fix_pull_request(
        access_token="token",
        repo_full_name="acme/shop",
        base_branch="main",
        base_sha="base-sha",
        head_branch="trueai/fix-abcd1234",
        files={"shop/views.py": "fixed\n"},
        file_modes={},
        commit_message="Fix discount",
        title="Fix discount",
        body="",
        draft=False,
        label=None,
    )


def test_revised_fix_is_pushed_on_top_of_the_open_pull_request(monkeypatch):
    repo = FakeRepo(head_tree="old-tree", new_tree="new-tree")
    result = _open(monkeypatch, repo)
    assert result.reused and result.updated and result.number == 412
    assert repo.commits == [("Fix discount", ["head-sha"])]  # parented on the branch head
    assert repo.ref.edits == [("new-commit", False)]  # fast-forward, never forced


def test_open_pull_request_left_alone_when_it_already_has_the_fix(monkeypatch):
    repo = FakeRepo(head_tree="same-tree", new_tree="same-tree")
    result = _open(monkeypatch, repo)
    assert result.reused and not result.updated
    assert repo.commits == [] and repo.ref.edits == []
