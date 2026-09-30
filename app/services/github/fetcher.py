"""
Repository snapshot: reads source files from GitHub at one pinned commit.

Why a snapshot
──────────────
Everything the agents see — and every edit the Fix Engineer makes — must
refer to the *same* commit.  ``open_snapshot`` resolves the target branch to
a commit SHA once; every file read afterwards uses that SHA, and the pull
request is later committed on top of it.  A push to the branch mid-analysis
can therefore never make a patch apply to code the agents did not see.

Path resolution
───────────────
Sentry frame paths rarely equal repository paths (``/usr/src/app/app/x.py``,
``webpack:///./src/x.ts``, module ``app.x``).  The snapshot loads the full
git tree once and matches the longest unambiguous path suffix, skipping
vendored directories.  Very large repositories whose tree is truncated fall
back to direct lookups of candidate paths.
"""

from __future__ import annotations

import base64
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from github import GithubException
from github.Repository import Repository

from app.core.config import settings
from app.core.errors import GitHubError
from app.core.logging import get_logger
from app.services import redis as redis_svc
from app.services.github.client import get_repository, to_github_error

logger = get_logger(__name__)

_VENDORED_DIRS = (
    "node_modules/", "vendor/", "dist/", "build/", ".venv/", "venv/", "site-packages/",
    ".git/", "__pycache__/", ".next/", "coverage/", "third_party/",
)
_TREE_CACHE_TTL = 3600
_MAX_CACHED_TREE_ENTRIES = 60_000

LANGUAGE_BY_EXTENSION = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".go": "go", ".rb": "ruby", ".java": "java", ".kt": "kotlin",
    ".php": "php", ".cs": "csharp", ".rs": "rust", ".swift": "swift", ".scala": "scala", ".ex": "elixir",
    ".exs": "elixir", ".json": "json", ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".sql": "sql",
}


@dataclass
class SourceFile:
    path: str
    content: str
    mode: str = "100644"

    @property
    def language(self) -> str:
        return LANGUAGE_BY_EXTENSION.get(posixpath.splitext(self.path)[1].lower(), "text")


@dataclass
class RepoSnapshot:
    repo_full_name: str
    branch: str
    default_branch: str
    sha: str
    paths: List[str] = field(default_factory=list)
    modes: Dict[str, str] = field(default_factory=dict)
    tree_complete: bool = True
    _repo: Optional[Repository] = field(default=None, repr=False)
    _by_basename: Dict[str, List[str]] = field(default_factory=dict, repr=False)

    def index(self) -> None:
        self._by_basename = {}
        for path in self.paths:
            self._by_basename.setdefault(posixpath.basename(path), []).append(path)

    def has_path(self, path: str) -> bool:
        return path in self.modes or path in self._by_basename.get(posixpath.basename(path), [])

    def to_state(self) -> Dict[str, Any]:
        return {
            "full_name": self.repo_full_name,
            "branch": self.branch,
            "default_branch": self.default_branch,
            "sha": self.sha,
        }


# ================================================================== #
# Opening a snapshot                                                   #
# ================================================================== #

def open_snapshot(
    access_token: str,
    repo_full_name: str,
    branch: Optional[str],
    *,
    pinned: Optional[Dict[str, Any]] = None,
) -> RepoSnapshot:
    """
    Resolve *branch* (or the default branch) to a commit and load the tree.

    Falls back to the default branch when the configured branch no longer
    exists.  Pass *pinned* (a ``RepoSnapshot.to_state()`` dict) to reopen a
    snapshot at an already-resolved commit.  Raises GitHubError when the
    repository itself is unreachable.
    """
    repo = get_repository(access_token, repo_full_name)
    if pinned:
        snapshot = RepoSnapshot(
            repo_full_name=repo_full_name,
            branch=pinned["branch"],
            default_branch=pinned["default_branch"],
            sha=pinned["sha"],
            _repo=repo,
        )
        _load_tree(snapshot)
        return snapshot
    try:
        default_branch = repo.default_branch
        target = branch or default_branch
        try:
            head = repo.get_branch(target)
        except GithubException as exc:
            if exc.status == 404 and target != default_branch:
                logger.warning("Branch '%s' not found in %s — using default '%s'.", target, repo_full_name, default_branch)
                target = default_branch
                head = repo.get_branch(target)
            else:
                raise
        sha = head.commit.sha
    except Exception as exc:
        raise to_github_error(exc, f"resolve branch of {repo_full_name}") from exc

    snapshot = RepoSnapshot(repo_full_name=repo_full_name, branch=target, default_branch=default_branch, sha=sha, _repo=repo)
    _load_tree(snapshot)
    return snapshot


def _load_tree(snapshot: RepoSnapshot) -> None:
    cache_key = f"tree:{snapshot.repo_full_name}:{snapshot.sha}"
    cached = redis_svc.cache_get(cache_key)
    if isinstance(cached, dict) and isinstance(cached.get("paths"), list):
        snapshot.paths = cached["paths"]
        snapshot.modes = cached.get("modes") or {}
        snapshot.tree_complete = bool(cached.get("complete", True))
        snapshot.index()
        return
    try:
        tree = snapshot._repo.get_git_tree(snapshot.sha, recursive=True)  # type: ignore[union-attr]
        paths: List[str] = []
        modes: Dict[str, str] = {}
        for element in tree.tree:
            if element.type != "blob" or _is_vendored(element.path):
                continue
            paths.append(element.path)
            modes[element.path] = element.mode
        snapshot.paths = paths
        snapshot.modes = modes
        snapshot.tree_complete = not bool(tree.truncated)
    except Exception as exc:
        # Tree listing is an optimisation; direct lookups still work without it.
        logger.warning("Could not load git tree for %s: %s", snapshot.repo_full_name, type(exc).__name__)
        snapshot.paths, snapshot.modes, snapshot.tree_complete = [], {}, False
    snapshot.index()
    if snapshot.paths and len(snapshot.paths) <= _MAX_CACHED_TREE_ENTRIES:
        redis_svc.cache_set(
            cache_key,
            {"paths": snapshot.paths, "modes": snapshot.modes, "complete": snapshot.tree_complete},
            _TREE_CACHE_TTL,
        )


# ================================================================== #
# Path resolution                                                      #
# ================================================================== #

def frame_path_candidates(frame: Dict[str, Any], platform: Optional[str] = None) -> List[str]:
    """Normalised relative-path candidates for a stack frame, most specific first."""
    candidates: List[str] = []
    for raw in (frame.get("abs_path"), frame.get("filename")):
        normalized = normalize_path(raw)
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    module = frame.get("module")
    if module and "/" not in module and "." in module and (platform in (None, "python") or not candidates):
        module_path = module.replace(".", "/") + ".py"
        if module_path not in candidates:
            candidates.append(module_path)
    return candidates


def normalize_path(raw: Optional[str]) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    path = raw.strip().replace("\\", "/")
    path = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:/+", "", path)  # webpack:///, app:///, file:///
    path = re.sub(r"^[A-Za-z]:/", "", path)  # Windows drive letters
    path = path.split("?", 1)[0].split("#", 1)[0]
    while path.startswith(("./", "../", "~/", "/")):
        path = path[1:] if path.startswith("/") else path.split("/", 1)[1] if "/" in path else ""
    path = posixpath.normpath(path) if path else ""
    if not path or path in (".", "..") or path.startswith("../") or path.startswith("<"):
        return None
    return path


def resolve_path(snapshot: RepoSnapshot, candidates: List[str]) -> Optional[str]:
    """
    Map frame path candidates to one repository path.

    For each candidate, tries the longest suffix first and accepts it only
    when exactly one repository file matches — an ambiguous basename-only
    match (e.g. ``utils.py``) is rejected rather than guessed.
    """
    if snapshot.paths:
        for candidate in candidates:
            parts = candidate.split("/")
            for size in range(len(parts), 0, -1):
                suffix = "/".join(parts[-size:])
                matches = [
                    p for p in snapshot._by_basename.get(parts[-1], [])
                    if p == suffix or p.endswith("/" + suffix)
                ]
                if len(matches) == 1:
                    return matches[0]
                if len(matches) > 1:
                    break  # ambiguous at the most specific matching level
        if snapshot.tree_complete:
            return None

    # Truncated/unavailable tree: probe candidate suffixes directly.
    for candidate in candidates:
        parts = candidate.split("/")
        for size in range(min(len(parts), 6), 0, -1):
            suffix = "/".join(parts[-size:])
            if _is_vendored(suffix):
                continue
            if _file_exists(snapshot, suffix):
                return suffix
    return None


def _file_exists(snapshot: RepoSnapshot, path: str) -> bool:
    try:
        content = snapshot._repo.get_contents(path, ref=snapshot.sha)  # type: ignore[union-attr]
        return not isinstance(content, list)
    except GithubException:
        return False


# ================================================================== #
# File reads                                                           #
# ================================================================== #

def read_file(snapshot: RepoSnapshot, path: str) -> Optional[SourceFile]:
    """
    Read *path* at the snapshot commit.  Returns None for missing, binary,
    oversized or non-UTF-8 files (those can be neither analysed nor edited
    safely).  Raises GitHubError for auth / rate-limit failures.
    """
    try:
        content = snapshot._repo.get_contents(path, ref=snapshot.sha)  # type: ignore[union-attr]
    except GithubException as exc:
        if exc.status == 404:
            return None
        raise to_github_error(exc, f"read {path}") from exc
    except Exception as exc:
        raise to_github_error(exc, f"read {path}") from exc

    if isinstance(content, list) or content.type != "file":
        return None
    if (content.size or 0) > settings.MAX_SOURCE_FILE_BYTES:
        logger.info("Skipping %s: %d bytes exceeds MAX_SOURCE_FILE_BYTES.", path, content.size)
        return None
    try:
        raw = content.decoded_content
    except Exception:
        # Files >1 MB have no inline content; fetch the blob directly.
        try:
            blob = snapshot._repo.get_git_blob(content.sha)  # type: ignore[union-attr]
            raw = base64.b64decode(blob.content)
        except Exception as exc:
            raise to_github_error(exc, f"read blob {path}") from exc
    if b"\x00" in raw[:8000]:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return SourceFile(path=path, content=text, mode=snapshot.modes.get(path, "100644"))


def _is_vendored(path: str) -> bool:
    lowered = "/" + path.lower().lstrip("/")
    return any(f"/{marker}" in lowered for marker in _VENDORED_DIRS)


__all__ = [
    "GitHubError",
    "RepoSnapshot",
    "SourceFile",
    "frame_path_candidates",
    "normalize_path",
    "open_snapshot",
    "read_file",
    "resolve_path",
]
