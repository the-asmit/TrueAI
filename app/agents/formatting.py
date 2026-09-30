"""
Prompt formatting shared by all agents.

Everything derived from the incident (messages, stack frames, request data,
breadcrumbs) and from the repository (source code) is untrusted, so each
block is wrapped with ``fence_untrusted``.  Keeping the formatting in one
place means every agent sees evidence in the same layout.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.core.security import fence_untrusted

# Character budgets keep prompts inside small-context models and provider TPM limits.
CODE_BUDGET_CHARS = 24_000
FRAMES_BUDGET_CHARS = 6_000


def format_incident(event: Dict[str, Any]) -> str:
    """Error summary + runtime metadata as a fenced block."""
    lines = [
        f"Error type    : {event.get('error_type') or 'UnknownError'}",
        f"Error message : {event.get('error_message') or '(none)'}",
        f"Level         : {event.get('level') or 'error'}",
        f"Platform      : {event.get('platform') or 'unknown'}",
        f"Environment   : {event.get('environment') or 'unknown'}",
    ]
    for label, key in (("Release", "release"), ("Transaction", "transaction"), ("Culprit", "culprit")):
        if event.get(key):
            lines.append(f"{label:<14}: {event[key]}")
    chain = event.get("exception_chain") or []
    if len(chain) > 1:
        lines.append("Exception chain (outermost → innermost):")
        lines.extend(f"  - {item.get('type')}: {item.get('value')}" for item in chain)
    request = event.get("request") or {}
    if request.get("url") or request.get("method"):
        lines.append(f"Request       : {request.get('method') or ''} {request.get('url') or ''}".rstrip())
        if request.get("data_keys"):
            lines.append(f"Request body keys: {', '.join(request['data_keys'])}")
    contexts = event.get("contexts") or {}
    runtime = contexts.get("runtime") or {}
    if runtime.get("name"):
        lines.append(f"Runtime       : {runtime.get('name')} {runtime.get('version') or ''}".rstrip())
    tags = event.get("tags") or {}
    if tags:
        shown = ", ".join(f"{k}={v}" for k, v in list(tags.items())[:12])
        lines.append(f"Tags          : {shown}")
    return fence_untrusted("sentry_event", "\n".join(lines), max_len=5000)


def format_frames(frames: List[Dict[str, Any]], *, limit: int = 12) -> str:
    """In-app stack frames, innermost (crash site) last, with Sentry's inline context."""
    if not frames:
        return "(no stack frames were captured)"
    selected = frames[-limit:]
    out: List[str] = []
    for index, frame in enumerate(selected, start=1):
        location = frame.get("filename") or frame.get("abs_path") or frame.get("module") or "?"
        marker = "  ← crash site" if index == len(selected) else ""
        out.append(f"#{index} {location}:{frame.get('lineno') or '?'} in {frame.get('function') or '?'}(){marker}")
        for line in (frame.get("pre_context") or [])[-3:]:
            out.append(f"      {line}")
        if frame.get("context_line") is not None:
            out.append(f"    > {frame['context_line']}")
        for line in (frame.get("post_context") or [])[:2]:
            out.append(f"      {line}")
    return fence_untrusted("stack_trace", "\n".join(out), max_len=FRAMES_BUDGET_CHARS)


def format_breadcrumbs(event: Dict[str, Any], *, limit: int = 8) -> Optional[str]:
    crumbs = (event.get("breadcrumbs") or [])[-limit:]
    if not crumbs:
        return None
    lines = [
        f"[{c.get('level') or 'info'}] {c.get('category') or 'event'}: {c.get('message') or ''}".rstrip(": ")
        for c in crumbs
    ]
    return fence_untrusted("breadcrumbs", "\n".join(lines), max_len=2500)


def format_code(code_context: Dict[str, Dict[str, Any]], *, budget: int = CODE_BUDGET_CHARS) -> str:
    """
    Source excerpts with a line-number gutter (``  42 | code``, crash lines
    marked ``> 42 | code``).  Files are included in priority order until the
    character budget is spent.
    """
    if not code_context:
        return "(no source code is available — the repository is not connected or files could not be matched)"
    blocks: List[str] = []
    used = 0
    for path, item in code_context.items():
        excerpt = item.get("excerpt") or ""
        header = (
            f"FILE {path} ({item.get('language', 'text')}, {item.get('total_lines', '?')} lines total"
            f"{', ' + item['reason'] if item.get('reason') else ''})"
        )
        block = fence_untrusted(f"file:{path}", f"{header}\n{excerpt}", max_len=max(2000, budget - used))
        if used + len(block) > budget and blocks:
            blocks.append(f"(omitted {path} — prompt budget reached)")
            continue
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def format_json(label: str, value: Any, *, max_len: int = 3000) -> str:
    return fence_untrusted(label, json.dumps(value, indent=2, default=str), max_len=max_len)
