"""
Normalisation of Sentry webhook payloads into one predictable shape.

Sentry delivers errors in several formats depending on how the webhook was
configured.  All of them are handled here:

    Legacy "WebHooks" plugin   {"id": <issue id>, "project_slug": ..., "url": ...,
                                "event": {...event...}}
    Integration "error"        {"action": "created", "data": {"error": {...event...}}}
    Integration "event_alert"  {"action": "triggered", "data": {"event": {...event...}}}
    Integration "issue"        {"action": "created", "data": {"issue": {...no stacktrace...}}}
    Raw / test event           {"event_id": ..., "exception": {"values": [...]}}

Events fetched from the Sentry REST API use a different layout again
("entries", camelCase frame keys) and are flattened by ``flatten_api_event``.

Every string that leaves this module has been scrubbed of credentials and
personal data (see ``app.core.security``) — local variables, cookies and
auth headers are dropped entirely.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.security import scrub, scrub_headers, scrub_text, scrub_url

MAX_FRAMES = 40
MAX_BREADCRUMBS = 12
MAX_STORED_PAYLOAD_BYTES = 250_000
# Frames per stack kept in the stored payload. Sentry lists the crash site
# LAST, so long stacks are cut from the front.
MAX_STORED_FRAMES = 60
# Integration webhooks nest frame fields about ten levels deep
# (data.event.exception.values[i].stacktrace.frames[j].pre_context[k]).
STORED_PAYLOAD_MAX_DEPTH = 16

# Resources sent in the ``Sentry-Hook-Resource`` header that carry errors.
_ERROR_RESOURCES = {"error", "event_alert"}

_VENDOR_MARKERS = (
    "site-packages/", "dist-packages/", "node_modules/", "/lib/python", "<frozen ",
    "<string>", "importlib/", "/usr/lib/", "webpack/bootstrap", "(native)", "internal/",
)


# ================================================================== #
# Webhook classification                                               #
# ================================================================== #

def should_process(resource: Optional[str], payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Decide whether a webhook delivery describes a new error worth analysing.

    Returns ``(process, reason)``; *reason* is shown in the 202 response when
    the delivery is acknowledged but skipped.
    """
    resource = (resource or "").strip().lower()
    action = str(payload.get("action") or "").lower()

    if resource in _ERROR_RESOURCES:
        return True, "error event"
    if resource == "issue":
        if action in ("created", ""):
            return True, "new issue"
        return False, f"issue action '{action}' is not analysed"
    if resource:
        return False, f"resource '{resource}' is not analysed"

    # No header: legacy plugin or a hand-crafted test payload.
    if _find_event(payload) is not None or isinstance(_find_issue(payload), dict):
        return True, "event payload"
    return False, "payload does not contain an error event"


# ================================================================== #
# Normalisation                                                        #
# ================================================================== #

def normalize_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return the normalised event dict for any supported payload shape."""
    event = _find_event(payload) or {}
    if "entries" in event:
        event = flatten_api_event(event)
    issue = _find_issue(payload) or {}
    issue_meta = issue.get("metadata") if isinstance(issue.get("metadata"), dict) else {}

    exception_values = _exception_values(event)
    primary = exception_values[-1] if exception_values else {}

    error_type = _clean(primary.get("type")) or _clean(issue_meta.get("type")) or _clean(
        (event.get("metadata") or {}).get("type") if isinstance(event.get("metadata"), dict) else None
    )
    error_message = _clean(primary.get("value")) or _clean(issue_meta.get("value")) or _message_of(event) or _clean(
        issue.get("title")
    )

    frames, total_frames, in_app_fallback = _collect_frames(event, exception_values)

    project = (
        _clean(payload.get("project_slug"))
        or _clean(_dig(issue, "project", "slug"))
        or _clean(event.get("project_slug"))
        or _project_from_payload(payload)
    )
    issue_id = (
        _clean(issue.get("id"))
        or _clean(event.get("issue_id"))
        or _clean(event.get("groupID"))
        or _clean(event.get("group_id"))
        or (_clean(payload.get("id")) if isinstance(payload.get("event"), dict) else None)
    )
    issue_url = _clean(issue.get("web_url")) or _clean(issue.get("permalink")) or _clean(payload.get("url")) or _clean(
        event.get("web_url")
    )

    request = event.get("request") if isinstance(event.get("request"), dict) else None
    normalized: Dict[str, Any] = {
        "event_id": _clean(event.get("event_id")) or _clean(event.get("eventID")) or _clean(payload.get("event_id")),
        "issue_id": issue_id,
        "issue_url": issue_url if issue_url and issue_url.startswith("https://") else None,
        "project": project,
        "error_type": (error_type or "UnknownError")[:200],
        "error_message": scrub_text(error_message or "", max_len=2000),
        "exception_chain": [
            {"type": _clean(v.get("type")) or "Error", "value": scrub_text(_clean(v.get("value")) or "", max_len=500)}
            for v in exception_values[-5:]
        ],
        "level": (_clean(event.get("level")) or _clean(payload.get("level")) or "error").lower()[:20],
        "platform": (_clean(event.get("platform")) or _clean(issue.get("platform")) or "")[:40] or None,
        "environment": (_clean(event.get("environment")) or _tag(event, "environment") or "")[:100] or None,
        "release": (_release(event) or "")[:200] or None,
        "transaction": scrub_text(_clean(event.get("transaction")) or "", max_len=300) or None,
        "server_name": (_clean(event.get("server_name")) or "")[:200] or None,
        "culprit": scrub_text(
            _clean(event.get("culprit")) or _clean(issue.get("culprit")) or _clean(payload.get("culprit")) or "", max_len=300
        )
        or None,
        "timestamp": _clean(event.get("timestamp")) or _clean(event.get("datetime")),
        "tags": _tags(event),
        "request": _request_summary(request),
        "has_user": bool(event.get("user")),
        "contexts": _contexts(event),
        "breadcrumbs": _breadcrumbs(event),
        "frames": frames,
        "total_frames": total_frames,
        "in_app_fallback": in_app_fallback,
    }
    normalized["fingerprint"] = compute_fingerprint(normalized)
    return normalized


def compute_fingerprint(event: Dict[str, Any]) -> str:
    """
    Stable identity of "the same problem" used to group repeat occurrences.

    Prefers Sentry's own issue grouping; otherwise hashes the error type and
    the innermost in-app frame (messages are excluded because they usually
    embed ids and values that change on every occurrence).
    """
    if event.get("issue_id"):
        return f"sentry:{event.get('project') or '-'}:{event['issue_id']}"[:200]
    frames = event.get("frames") or []
    top = frames[-1] if frames else {}
    location = f"{top.get('filename') or top.get('module') or ''}:{top.get('function') or ''}"
    if location == ":":
        location = re.sub(r"[0-9a-f]{8,}|\d+", "N", (event.get("error_message") or "").lower())[:200]
    basis = "|".join([event.get("platform") or "", event.get("error_type") or "", location])
    return "hash:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:32]


def payload_for_storage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Scrubbed, size-capped copy of the webhook payload for the incidents table."""
    stored = scrub(_trim_stacks(payload), max_depth=STORED_PAYLOAD_MAX_DEPTH, max_items=MAX_STORED_FRAMES, max_str=4000)
    if isinstance(stored, dict):
        if len(repr(stored)) > MAX_STORED_PAYLOAD_BYTES:
            # Drop the bulkiest optional sections first.
            for section in ("breadcrumbs", "extra", "contexts", "modules", "debug_meta", "sdk"):
                for container in (stored, stored.get("event") if isinstance(stored.get("event"), dict) else None):
                    if isinstance(container, dict):
                        container.pop(section, None)
            if len(repr(stored)) > MAX_STORED_PAYLOAD_BYTES:
                return {"truncated": True, "reason": "payload exceeded storage limit"}
    return stored if isinstance(stored, dict) else {}


def frames_for_storage(frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact frame list stored on the incident for the dashboard stack view."""
    return [
        {
            "filename": f.get("filename"),
            "function": f.get("function"),
            "lineno": f.get("lineno"),
            "context_line": f.get("context_line"),
            "in_app": f.get("in_app"),
        }
        for f in frames[-25:]
    ]


def flatten_api_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Sentry REST API event (``entries`` layout) to the webhook layout."""
    flat = {k: v for k, v in event.items() if k != "entries"}
    for entry in event.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        entry_type, data = entry.get("type"), entry.get("data")
        if entry_type == "exception" and isinstance(data, dict):
            flat["exception"] = data
        elif entry_type == "request" and isinstance(data, dict):
            flat["request"] = data
        elif entry_type == "breadcrumbs" and isinstance(data, dict):
            flat["breadcrumbs"] = data
        elif entry_type == "stacktrace" and isinstance(data, dict):
            flat["stacktrace"] = data
        elif entry_type == "threads" and isinstance(data, dict):
            flat["threads"] = data
        elif entry_type == "message" and isinstance(data, dict):
            flat.setdefault("message", data.get("formatted") or data.get("message"))
    if isinstance(event.get("tags"), list):
        flat["tags"] = event["tags"]
    flat.setdefault("event_id", event.get("eventID") or event.get("id"))
    return flat


# ================================================================== #
# Internal helpers                                                     #
# ================================================================== #

def _find_event(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for candidate in (data.get("error"), data.get("event"), payload.get("event")):
        if isinstance(candidate, dict) and candidate:
            return candidate
    if any(k in payload for k in ("exception", "stacktrace", "threads", "entries", "event_id", "logentry")):
        return payload
    return None


def _find_issue(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    issue = data.get("issue")
    return issue if isinstance(issue, dict) else None


def _project_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    project = payload.get("project")
    if isinstance(project, dict):
        return _clean(project.get("slug"))
    if isinstance(project, str) and not project.isdigit():
        return project
    return None


def _exception_values(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    exception = event.get("exception") or event.get("sentry.interfaces.Exception")
    if isinstance(exception, dict):
        values = exception.get("values")
    elif isinstance(exception, list):
        values = exception
    else:
        values = None
    return [v for v in (values or []) if isinstance(v, dict)]


def _collect_frames(event: Dict[str, Any], exception_values: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int, bool]:
    """
    Return ``(frames, total, in_app_fallback)``.  Frames of the primary
    (innermost) exception come last so that ``frames[-1]`` is the crash site.
    """
    raw_frames: List[Dict[str, Any]] = []
    for value in exception_values:
        raw_frames.extend(_frames_of(value.get("stacktrace")))
    if not raw_frames:
        raw_frames = _frames_of(event.get("stacktrace"))
    if not raw_frames:
        threads = event.get("threads")
        thread_values = threads.get("values") if isinstance(threads, dict) else threads
        if isinstance(thread_values, list):
            chosen = next((t for t in thread_values if isinstance(t, dict) and t.get("crashed")), None) or next(
                (t for t in thread_values if isinstance(t, dict) and t.get("current")), None
            )
            if chosen:
                raw_frames = _frames_of(chosen.get("stacktrace"))

    frames = [_normalize_frame(f) for f in raw_frames if isinstance(f, dict)]
    frames = [f for f in frames if f.get("filename") or f.get("module") or f.get("function")]
    total = len(frames)
    in_app = [f for f in frames if f["in_app"]]
    in_app_fallback = False
    if not in_app and frames:
        in_app = [f for f in frames if not _looks_vendored(f)]
        in_app_fallback = True
    return in_app[-MAX_FRAMES:], total, in_app_fallback


def _frames_of(stacktrace: Any) -> List[Dict[str, Any]]:
    if isinstance(stacktrace, dict) and isinstance(stacktrace.get("frames"), list):
        return stacktrace["frames"]
    return []


def _normalize_frame(frame: Dict[str, Any]) -> Dict[str, Any]:
    context_line = frame.get("context_line")
    pre = frame.get("pre_context")
    post = frame.get("post_context")
    lineno = _to_int(frame.get("lineno", frame.get("lineNo")))
    # REST API frames carry context as [[lineno, "code"], ...].
    if context_line is None and isinstance(frame.get("context"), list) and lineno is not None:
        pre, post = [], []
        for item in frame["context"]:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                number, code = _to_int(item[0]), str(item[1])
                if number == lineno:
                    context_line = code
                elif number is not None and number < lineno:
                    pre.append(code)
                elif number is not None:
                    post.append(code)

    in_app_flag = frame.get("in_app", frame.get("inApp"))
    normalized = {
        "filename": _clean(frame.get("filename")),
        "abs_path": _clean(frame.get("abs_path", frame.get("absPath"))),
        "module": _clean(frame.get("module")),
        "function": _clean(frame.get("function")),
        "lineno": lineno,
        "colno": _to_int(frame.get("colno", frame.get("colNo"))),
        "context_line": scrub_text(str(context_line), max_len=500) if context_line is not None else None,
        "pre_context": [scrub_text(str(line), max_len=500) for line in (pre or [])[-5:]],
        "post_context": [scrub_text(str(line), max_len=500) for line in (post or [])[:5]],
        "in_app": bool(in_app_flag) if in_app_flag is not None else None,
    }
    if normalized["in_app"] is None:
        normalized["in_app"] = not _looks_vendored(normalized)
    return normalized


def _looks_vendored(frame: Dict[str, Any]) -> bool:
    path = (frame.get("abs_path") or frame.get("filename") or frame.get("module") or "").replace("\\", "/")
    return any(marker in path for marker in _VENDOR_MARKERS)


def _message_of(event: Dict[str, Any]) -> Optional[str]:
    logentry = event.get("logentry") or event.get("sentry.interfaces.Message")
    if isinstance(logentry, dict):
        return _clean(logentry.get("formatted")) or _clean(logentry.get("message"))
    message = event.get("message")
    if isinstance(message, dict):
        return _clean(message.get("formatted")) or _clean(message.get("message"))
    return _clean(message) or _clean(event.get("title"))


def _release(event: Dict[str, Any]) -> Optional[str]:
    release = event.get("release")
    if isinstance(release, dict):
        return _clean(release.get("version")) or _clean(release.get("shortVersion"))
    return _clean(release)


def _tags(event: Dict[str, Any]) -> Dict[str, str]:
    tags = event.get("tags")
    result: Dict[str, str] = {}
    if isinstance(tags, dict):
        items = tags.items()
    elif isinstance(tags, list):
        items = []
        for item in tags:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                items.append((item[0], item[1]))
            elif isinstance(item, dict) and "key" in item:
                items.append((item.get("key"), item.get("value")))
    else:
        return result
    for key, value in list(items)[:30]:
        key_str = str(key)[:64]
        if any(part in key_str.lower() for part in ("user", "email", "ip", "token", "session")):
            continue
        result[key_str] = scrub_text(str(value), max_len=200)
    return result


def _tag(event: Dict[str, Any], name: str) -> Optional[str]:
    return _tags(event).get(name)


def _request_summary(request: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not request:
        return None
    url = _clean(request.get("url"))
    return {
        "method": (_clean(request.get("method")) or "")[:10] or None,
        "url": scrub_url(url) if url else None,
        "headers": scrub_headers(request.get("headers")),
        # Request bodies can contain anything; keep only their shape.
        "data_keys": sorted(str(k) for k in request["data"].keys())[:30] if isinstance(request.get("data"), dict) else None,
    }


def _contexts(event: Dict[str, Any]) -> Dict[str, Any]:
    contexts = event.get("contexts")
    if not isinstance(contexts, dict):
        return {}
    keep = {}
    for name in ("runtime", "os", "browser", "device", "app", "trace"):
        value = contexts.get(name)
        if isinstance(value, dict):
            keep[name] = {
                k: scrub_text(str(v), max_len=120)
                for k, v in value.items()
                if k in ("name", "version", "type", "op", "status", "app_version", "build")
            }
    return keep


def _breadcrumbs(event: Dict[str, Any]) -> List[Dict[str, Any]]:
    crumbs = event.get("breadcrumbs")
    values = crumbs.get("values") if isinstance(crumbs, dict) else crumbs
    if not isinstance(values, list):
        return []
    result = []
    for crumb in values[-MAX_BREADCRUMBS:]:
        if not isinstance(crumb, dict):
            continue
        result.append(
            {
                "category": (_clean(crumb.get("category")) or "")[:60] or None,
                "level": (_clean(crumb.get("level")) or "")[:20] or None,
                "message": scrub_text(_clean(crumb.get("message")) or "", max_len=300) or None,
                "timestamp": _clean(crumb.get("timestamp")),
            }
        )
    return result


def _trim_stacks(value: Any, depth: int = 0) -> Any:
    """
    Copy of ``value`` without captured local variables (they often hold
    secrets) and with every frame list cut to its last MAX_STORED_FRAMES
    entries, so the crash site survives the size caps applied afterwards.
    """
    if depth > STORED_PAYLOAD_MAX_DEPTH:
        return value  # scrub() replaces anything this deep
    if isinstance(value, dict):
        trimmed: Dict[str, Any] = {}
        for key, item in value.items():
            if key == "vars":
                continue
            if key == "frames" and isinstance(item, list):
                item = item[-MAX_STORED_FRAMES:]
            trimmed[key] = _trim_stacks(item, depth + 1)
        return trimmed
    if isinstance(value, list):
        return [_trim_stacks(item, depth + 1) for item in value]
    return value


def _dig(value: Any, *keys: str) -> Any:
    for k in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(k)
    return value


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _to_int(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
