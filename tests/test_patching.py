"""Patch engine: edit application, formatting preservation, syntax checks and policy guard-rails."""

from __future__ import annotations

import pytest

from app.core.errors import PatchError
from app.services.patching import FileEdit, apply_edits, check_policy, validate_syntax

VIEW = "def get(session):\n    user = session['user_id']\n    return user\n"


def test_exact_edit_and_generated_diff():
    result = apply_edits([FileEdit("app/v.py", "    user = session['user_id']", "    user = session.get('user_id')")], {"app/v.py": VIEW})
    assert result.files["app/v.py"] == VIEW.replace("session['user_id']", "session.get('user_id')")
    assert result.diff.startswith("--- a/app/v.py\n+++ b/app/v.py\n@@")
    assert (result.added_lines, result.removed_lines) == (1, 1)
    assert result.files_changed == ["app/v.py"]


def test_line_number_gutter_and_fences_are_stripped():
    search = "```python\n>    2 | user = session['user_id']\n```"
    replace = "     2 | user = session.get('user_id')"
    result = apply_edits([FileEdit("app/v.py", search, replace)], {"app/v.py": VIEW})
    assert "    user = session.get('user_id')" in result.files["app/v.py"]


def test_indentation_insensitive_match_reindents_replacement():
    source = "class A:\n    def f(self):\n        return self.x['k']\n"
    result = apply_edits([FileEdit("a.py", "return self.x['k']", "return self.x.get('k')")], {"a.py": source})
    assert result.files["a.py"] == "class A:\n    def f(self):\n        return self.x.get('k')\n"


def test_crlf_and_missing_final_newline_are_preserved():
    result = apply_edits([FileEdit("a.py", "x = 1", "x = 2")], {"a.py": "x = 1\r\ny = 2"})
    assert result.files["a.py"] == "x = 2\r\ny = 2"


def test_ambiguous_missing_empty_and_foreign_edits_are_rejected():
    with pytest.raises(PatchError, match="matches 2 places"):
        apply_edits([FileEdit("a.py", "x", "y")], {"a.py": "x\nx\n"})
    with pytest.raises(PatchError, match="was not found"):
        apply_edits([FileEdit("a.py", "zzz", "y")], {"a.py": "x\n"})
    with pytest.raises(PatchError, match="empty"):
        apply_edits([FileEdit("a.py", "   ", "y")], {"a.py": "x\n"})
    with pytest.raises(PatchError, match="not one of the provided files"):
        apply_edits([FileEdit("other.py", "x", "y")], {"a.py": "x\n"})
    with pytest.raises(PatchError, match="does not change"):
        apply_edits([FileEdit("a.py", "x", "x")], {"a.py": "x\n"})


def test_multiple_edits_across_files():
    originals = {"a.py": "a = 1\n", "b.py": "b = 1\n"}
    result = apply_edits([FileEdit("a.py", "a = 1", "a = 2"), FileEdit("b.py", "b = 1", "b = 2")], originals)
    assert result.files_changed == ["a.py", "b.py"]
    assert result.diff.count("--- a/") == 2


def test_syntax_validation_by_file_type():
    assert validate_syntax("a.py", "x = 1\n", "x = (\n") is not None
    assert validate_syntax("a.py", "x = 1\n", "x = 2\n") is None
    assert validate_syntax("a.json", "{}", "{bad") is not None
    assert validate_syntax("a.yaml", "a: 1\n", "a: [1\n") is not None
    assert validate_syntax("a.toml", "a = 1\n", "a = \n") is not None
    assert validate_syntax("a.ts", "let a = 1", "let a = (") is None  # no parser available → not blocked
    assert validate_syntax("a.py", "x = (\n", "y = (\n") is None      # already broken → nothing to compare


def test_policy_blocks_dangerous_additions_but_not_existing_code():
    original = "import subprocess\n\ndef run(cmd):\n    return subprocess.run(cmd)\n"
    patch = apply_edits([FileEdit("a.py", "return subprocess.run(cmd)", "return subprocess.run(cmd, check=True)")], {"a.py": original})
    assert check_policy(patch, {"a.py": original}) == []

    unsafe = apply_edits([FileEdit("a.py", "return subprocess.run(cmd)", "return eval(cmd)")], {"a.py": original})
    assert any("dynamic code execution" in v for v in check_policy(unsafe, {"a.py": original}))

    tls = apply_edits([FileEdit("c.py", "r = get(url)", "r = get(url, verify=False)")], {"c.py": "r = get(url)\n"})
    assert any("TLS" in v for v in check_policy(tls, {"c.py": "r = get(url)\n"}))


def test_policy_blocks_protected_paths_and_mass_deletion():
    workflow = "on: push\njobs: {}\n"
    patch = apply_edits([FileEdit(".github/workflows/ci.yml", "on: push", "on: pull_request")], {".github/workflows/ci.yml": workflow})
    assert any("protected file" in v for v in check_policy(patch, {".github/workflows/ci.yml": workflow}))

    big = "\n".join(f"line_{i} = {i}" for i in range(40)) + "\n"
    shrink = apply_edits([FileEdit("m.py", "\n".join(f"line_{i} = {i}" for i in range(30)), "pass")], {"m.py": big})
    assert any("Removes more than half" in v for v in check_policy(shrink, {"m.py": big}))
