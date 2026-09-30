"""
Deterministic patch application, validation and policy enforcement.

The Fix Engineer agent does not write unified diffs — LLMs routinely get
diff line numbers and hunk counts wrong.  Instead it returns search/replace
edits: an exact excerpt of the current file and its replacement.  This
module applies those edits and produces the real diff itself.

Matching strategy (the excerpt must match exactly ONE location):
    1. exact text
    2. line-by-line ignoring trailing whitespace
    3. line-by-line ignoring indentation (replacement is re-indented)

After applying, every changed file is syntax-checked when a parser is
available (Python, JSON, YAML, TOML), and ``check_policy`` enforces hard
guard-rails no agent can talk its way past: size limits, protected paths
(CI, lockfiles, secrets, infrastructure) and dangerous additions (eval,
shell execution, disabled TLS verification, embedded credentials).
"""

from __future__ import annotations

import ast
import difflib
import fnmatch
import json
import re
import tomllib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import yaml

from app.core.config import settings
from app.core.errors import PatchError

# Line-number gutter used when showing code to agents ("  42 | code" / "> 42 | code").
_GUTTER_RE = re.compile(r"^\s*>?\s*\d+\s?[|│]\s?")


@dataclass
class FileEdit:
    path: str
    search: str
    replace: str


@dataclass
class PatchResult:
    files: Dict[str, str]                      # path → full new content
    diff: str                                  # unified diff of every change
    files_changed: List[str]
    added_lines: int
    removed_lines: int
    added_line_texts: List[str] = field(default_factory=list)

    @property
    def changed_lines(self) -> int:
        return self.added_lines + self.removed_lines


# ================================================================== #
# Applying edits                                                       #
# ================================================================== #

def apply_edits(edits: Sequence[FileEdit], originals: Dict[str, str]) -> PatchResult:
    """
    Apply *edits* to *originals* (path → current content).

    Raises PatchError with a message written for the Fix Engineer (it is fed
    back to the agent so it can correct its edits on the next attempt).
    """
    if not edits:
        raise PatchError("No edits were provided.")

    working: Dict[str, str] = {}
    crlf: Dict[str, bool] = {}
    for number, edit in enumerate(edits, start=1):
        path = edit.path.strip().lstrip("/")
        if path not in originals:
            allowed = ", ".join(sorted(originals)) or "(none)"
            raise PatchError(f"Edit {number} targets '{path}', which is not one of the provided files: {allowed}.")
        if path not in working:
            original = originals[path]
            crlf[path] = "\r\n" in original
            working[path] = original.replace("\r\n", "\n")

        search = _strip_gutter(_normalize_block(edit.search))
        replace = _strip_gutter(_normalize_block(edit.replace))
        if not search.strip():
            raise PatchError(f"Edit {number} for '{path}' has an empty <search> block; it must quote existing code.")
        if search == replace:
            raise PatchError(f"Edit {number} for '{path}' does not change anything.")
        working[path] = _replace_once(working[path], search, replace, path, number)

    files: Dict[str, str] = {}
    diffs: List[str] = []
    added = removed = 0
    added_texts: List[str] = []
    for path, content in working.items():
        original_lf = originals[path].replace("\r\n", "\n")
        if content == original_lf:
            continue
        diff_lines = list(
            difflib.unified_diff(
                original_lf.splitlines(), content.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="", n=3
            )
        )
        for line in diff_lines:
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
                added_texts.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        diffs.append("\n".join(diff_lines))
        files[path] = content.replace("\n", "\r\n") if crlf[path] else content

    if not files:
        raise PatchError("The edits did not change any file.")

    return PatchResult(
        files=files,
        diff="\n".join(diffs) + "\n",
        files_changed=sorted(files),
        added_lines=added,
        removed_lines=removed,
        added_line_texts=added_texts,
    )


def _normalize_block(text: str) -> str:
    """Normalise newlines, drop Markdown fences and one leading/trailing blank line."""
    text = (text or "").replace("\r\n", "\n")
    lines = text.split("\n")
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    text = "\n".join(lines)
    if text.startswith("\n"):
        text = text[1:]
    if text.endswith("\n"):
        text = text[:-1]
    return text


def _strip_gutter(block: str) -> str:
    """Remove a line-number gutter copied from the prompt, if every line has one."""
    lines = block.split("\n")
    non_empty = [line for line in lines if line.strip()]
    if non_empty and all(_GUTTER_RE.match(line) for line in non_empty):
        return "\n".join(_GUTTER_RE.sub("", line, count=1) for line in lines)
    return block


def _replace_once(content: str, search: str, replace: str, path: str, number: int) -> str:
    # 1. Exact match.
    occurrences = content.count(search)
    if occurrences == 1:
        return content.replace(search, replace, 1)
    if occurrences > 1:
        raise PatchError(
            f"Edit {number}: the <search> block matches {occurrences} places in '{path}'. "
            "Include more surrounding lines so it matches exactly one location."
        )

    lines = content.split("\n")
    search_lines = search.split("\n")
    # Surrounding blank lines in the excerpt must not prevent a line match.
    while search_lines and not search_lines[0].strip():
        search_lines = search_lines[1:]
    while search_lines and not search_lines[-1].strip():
        search_lines = search_lines[:-1]
    replace_lines = replace.split("\n")

    # 2. Ignore trailing whitespace.
    matches = _find_line_matches(lines, search_lines, lambda s: s.rstrip())
    if len(matches) == 1:
        start = matches[0]
        return "\n".join(lines[:start] + replace_lines + lines[start + len(search_lines):])

    # 3. Ignore indentation, then re-indent the replacement by the same offset.
    if not matches:
        matches = _find_line_matches(lines, search_lines, lambda s: s.strip())
        if len(matches) == 1:
            start = matches[0]
            reindented = _reindent(replace_lines, search_lines, lines[start : start + len(search_lines)])
            return "\n".join(lines[:start] + reindented + lines[start + len(search_lines):])

    if len(matches) > 1:
        raise PatchError(
            f"Edit {number}: the <search> block matches {len(matches)} places in '{path}'. "
            "Include more surrounding lines so it matches exactly one location."
        )
    raise PatchError(
        f"Edit {number}: the <search> block was not found in '{path}'. Copy the existing lines exactly "
        "as they appear in the file (without the line-number gutter), including indentation."
    )


def _find_line_matches(lines: List[str], search_lines: List[str], key) -> List[int]:
    wanted = [key(line) for line in search_lines]
    if not wanted:
        return []
    keyed = [key(line) for line in lines]
    size = len(wanted)
    return [i for i in range(len(keyed) - size + 1) if keyed[i : i + size] == wanted]


def _reindent(replace_lines: List[str], search_lines: List[str], matched_lines: List[str]) -> List[str]:
    def indent_of(block: List[str]) -> Optional[str]:
        for line in block:
            if line.strip():
                return line[: len(line) - len(line.lstrip())]
        return None

    search_indent = indent_of(search_lines) or ""
    actual_indent = indent_of(matched_lines) or ""
    result = []
    for line in replace_lines:
        if not line.strip():
            result.append(line)
        elif line.startswith(search_indent):
            result.append(actual_indent + line[len(search_indent):])
        else:
            result.append(actual_indent + line.lstrip())
    return result


# ================================================================== #
# Syntax validation                                                    #
# ================================================================== #

def validate_syntax(path: str, original: str, new_content: str) -> Optional[str]:
    """
    Return an error message when *new_content* is syntactically invalid for
    its file type (and *original* was valid), otherwise None.
    """
    checker = _syntax_checker(path)
    if checker is None:
        return None
    if checker(original) is not None:
        return None  # the file was already unparseable; nothing to compare against
    return checker(new_content)


def _syntax_checker(path: str):
    lowered = path.lower()
    if lowered.endswith(".py"):
        return _check_python
    if lowered.endswith(".json"):
        return _check_json
    if lowered.endswith((".yml", ".yaml")):
        return _check_yaml
    if lowered.endswith(".toml"):
        return _check_toml
    return None


def _check_python(source: str) -> Optional[str]:
    try:
        ast.parse(source)
        return None
    except SyntaxError as exc:
        return f"invalid Python syntax at line {exc.lineno}: {exc.msg}"


def _check_json(source: str) -> Optional[str]:
    try:
        json.loads(source)
        return None
    except json.JSONDecodeError as exc:
        return f"invalid JSON at line {exc.lineno}: {exc.msg}"


def _check_yaml(source: str) -> Optional[str]:
    try:
        list(yaml.safe_load_all(source))
        return None
    except yaml.YAMLError as exc:
        return f"invalid YAML: {str(exc).splitlines()[0]}"


def _check_toml(source: str) -> Optional[str]:
    try:
        tomllib.loads(source)
        return None
    except tomllib.TOMLDecodeError as exc:
        return f"invalid TOML: {exc}"


# ================================================================== #
# Policy guard-rails                                                   #
# ================================================================== #

PROTECTED_PATH_PATTERNS: tuple[str, ...] = (
    ".github/*", ".gitlab-ci.yml", ".circleci/*", "Jenkinsfile", "azure-pipelines.yml", ".travis.yml",
    "Dockerfile", "*/Dockerfile", "Dockerfile.*", "docker-compose*.yml", "docker-compose*.yaml",
    "*.lock", "package-lock.json", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    ".env", ".env.*", "*/.env", "*/.env.*", "*.pem", "*.key", "*.p12", "*.crt", "*secret*", "*credential*",
    "*.tf", "*.tfvars", "CODEOWNERS", ".github/CODEOWNERS", ".gitmodules", ".npmrc", ".pypirc",
)

_DANGEROUS_ADDITIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dynamic code execution (eval/exec)", re.compile(r"(?<![\w.])(eval|exec)\s*\(")),
    ("shell command execution", re.compile(r"\b(os\.system|os\.popen|subprocess\.|child_process|execSync|spawnSync|Runtime\.getRuntime\(\)\.exec|shell_exec|popen\()")),
    ("unsafe deserialisation", re.compile(r"\b(pickle\.loads?|marshal\.loads|yaml\.load\((?![^)]*SafeLoader)|unserialize\()")),
    ("disabled TLS verification", re.compile(r"(verify\s*=\s*False|rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED|InsecureSkipVerify\s*:\s*true|CERT_NONE)")),
    ("download-and-execute", re.compile(r"(curl|wget)[^\n|]*\|\s*(ba|z)?sh")),
    ("embedded credential", re.compile(r"(AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})")),
    ("disabled authentication/authorisation check", re.compile(r"(?i)(auth(entication|orization)?_?(required|enabled)\s*=\s*False|@csrf_exempt|permission_classes\s*=\s*\[\s*AllowAny)")),
)


def check_policy(result: PatchResult, originals: Dict[str, str]) -> List[str]:
    """Return human-readable policy violations; an empty list means the patch may be auto-PR'd."""
    violations: List[str] = []

    if len(result.files_changed) > settings.MAX_PATCH_FILES:
        violations.append(
            f"Changes {len(result.files_changed)} files; the limit for automatic PRs is {settings.MAX_PATCH_FILES}."
        )
    if result.changed_lines > settings.MAX_PATCH_CHANGED_LINES:
        violations.append(
            f"Changes {result.changed_lines} lines; the limit for automatic PRs is {settings.MAX_PATCH_CHANGED_LINES}."
        )

    for path in result.files_changed:
        name = path.split("/")[-1]
        if any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(name, pattern) for pattern in PROTECTED_PATH_PATTERNS):
            violations.append(f"Modifies a protected file ({path}); CI, lockfiles, secrets and infrastructure need human changes.")
        original_lines = len(originals.get(path, "").splitlines())
        new_lines = len(result.files[path].splitlines())
        if original_lines >= 10 and new_lines < original_lines * 0.5:
            violations.append(f"Removes more than half of {path} ({original_lines} → {new_lines} lines).")

    existing_text = "\n".join(originals.get(p, "") for p in result.files_changed)
    for label, pattern in _DANGEROUS_ADDITIONS:
        for line in result.added_line_texts:
            if pattern.search(line) and not pattern.search(existing_text):
                violations.append(f"Introduces {label}: `{line.strip()[:120]}`")
                break
    return violations
