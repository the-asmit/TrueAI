"""Mapping Sentry frame paths to repository files and building prompt excerpts."""

from __future__ import annotations

from app.nodes.context import build_excerpt
from app.services.github.fetcher import RepoSnapshot, SourceFile, frame_path_candidates, normalize_path, resolve_path


def _snapshot(paths):
    snap = RepoSnapshot(repo_full_name="acme/shop", branch="main", default_branch="main", sha="abc123", paths=list(paths))
    snap.modes = {p: "100644" for p in paths}
    snap.index()
    return snap


def test_normalize_path_handles_sentry_path_styles():
    assert normalize_path("webpack:///./src/components/Cart.tsx") == "src/components/Cart.tsx"
    assert normalize_path("app:///dist/main.js?v=3") == "dist/main.js"
    assert normalize_path("/usr/src/app/app/views.py") == "usr/src/app/app/views.py"
    assert normalize_path("C:\\build\\src\\a.py") == "build/src/a.py"
    assert normalize_path("<frozen importlib._bootstrap>") is None
    assert normalize_path("../../etc/passwd") == "etc/passwd"


def test_resolve_prefers_longest_unambiguous_suffix():
    snap = _snapshot(["app/views.py", "admin/views.py", "app/utils.py", "tests/app/utils.py", "node_modules/x/views.py"])
    frame = {"abs_path": "/srv/deploy/current/app/views.py", "filename": "app/views.py"}
    assert resolve_path(snap, frame_path_candidates(frame, "python")) == "app/views.py"


def test_ambiguous_basename_is_not_guessed():
    snap = _snapshot(["a/utils.py", "b/utils.py"])
    assert resolve_path(snap, ["utils.py"]) is None


def test_python_module_fallback():
    snap = _snapshot(["services/billing/invoice.py"])
    frame = {"module": "services.billing.invoice", "filename": None}
    assert resolve_path(snap, frame_path_candidates(frame, "python")) == "services/billing/invoice.py"


def test_excerpt_shows_whole_small_files_and_windows_large_ones():
    small = build_excerpt(SourceFile("a.py", "x = 1\ny = 2\n"), [2], reason="stack trace")
    assert small["excerpt"].splitlines() == ["      1 | x = 1", ">     2 | y = 2"]
    assert small["total_lines"] == 2

    big_source = "\n".join(f"line {i}" for i in range(1, 501))
    big = build_excerpt(SourceFile("b.py", big_source), [300], reason="stack trace")
    lines = big["excerpt"].splitlines()
    assert lines[0].endswith("| line 1")                      # header (imports) always included
    assert any(line.startswith(">   300 | line 300") for line in lines)
    assert "⋮" in big["excerpt"] and not any("| line 400" in line for line in lines)
