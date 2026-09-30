"""Sentry payload normalisation: every delivery format, filtering, scrubbing and grouping."""

from __future__ import annotations

import copy

from app.services.sentry_events import (
    compute_fingerprint,
    flatten_api_event,
    normalize_event,
    payload_for_storage,
    should_process,
)

FRAMES = [
    {"filename": "django/core/handlers/base.py", "abs_path": "/usr/lib/python3.12/site-packages/django/core/handlers/base.py",
     "function": "_get_response", "lineno": 197, "in_app": False},
    {"filename": "app/views/dashboard.py", "abs_path": "/srv/app/app/views/dashboard.py", "function": "get_dashboard",
     "lineno": 42, "in_app": True, "context_line": "    user = session['user_id']",
     "pre_context": ["def get_dashboard(request):"], "post_context": ["    return render(user)"],
     "vars": {"password": "hunter2", "session": {"user_id": None}}},
]

RAW_EVENT = {
    "event_id": "ev-123",
    "platform": "python",
    "environment": "production",
    "level": "error",
    "exception": {"values": [{"type": "KeyError", "value": "'user_id'", "stacktrace": {"frames": FRAMES}}]},
    "request": {
        "url": "https://shop.example.com/dashboard?token=abc123&page=2",
        "method": "GET",
        "headers": {"Cookie": "sessionid=secret", "Authorization": "Bearer abcdefghijklmnop", "User-Agent": "curl/8"},
        "data": {"email": "a@b.com", "card_number": "4111111111111111"},
    },
    "user": {"email": "victim@example.com", "ip_address": "10.1.2.3"},
    "tags": [["server_name", "web-1"], ["user.email", "x@y.com"]],
}


def test_raw_event_is_normalised_with_in_app_frames_only():
    event = normalize_event(copy.deepcopy(RAW_EVENT))
    assert event["event_id"] == "ev-123"
    assert event["error_type"] == "KeyError"
    assert [f["filename"] for f in event["frames"]] == ["app/views/dashboard.py"]
    assert event["frames"][-1]["context_line"] == "    user = session['user_id']"
    assert event["in_app_fallback"] is False
    assert event["total_frames"] == 2


def test_sensitive_request_data_never_survives_normalisation():
    event = normalize_event(copy.deepcopy(RAW_EVENT))
    request = event["request"]
    assert "Cookie" not in request["headers"] and "Authorization" not in request["headers"]
    assert request["headers"]["User-Agent"] == "curl/8"
    assert "abc123" not in request["url"] and "page=2" in request["url"]
    assert request["data_keys"] == ["card_number", "email"]  # values are never kept
    assert "user.email" not in event["tags"]
    assert event["has_user"] is True
    assert "victim@example.com" not in str(event)
    assert "hunter2" not in str(event)


def test_stored_payload_drops_local_variables_and_secrets():
    stored = payload_for_storage(copy.deepcopy(RAW_EVENT))
    text = str(stored)
    assert "hunter2" not in text
    assert "sessionid=secret" not in text
    assert "vars" not in str(stored["exception"])


def test_stored_integration_payload_still_has_its_stack_trace():
    # The pipeline re-reads the STORED payload, so the frames must survive storage.
    alert_hook = {"action": "triggered", "data": {"event": copy.deepcopy(RAW_EVENT), "triggered_rule": "r"}}
    event = normalize_event(payload_for_storage(alert_hook))
    assert [f["filename"] for f in event["frames"]] == ["app/views/dashboard.py"]
    assert event["frames"][-1]["context_line"] == "    user = session['user_id']"
    assert event["frames"][-1]["pre_context"] == ["def get_dashboard(request):"]


def test_stored_payload_keeps_the_crash_site_of_a_long_stack():
    deep = [{"filename": f"app/recursion.py", "function": f"step_{i}", "lineno": i, "in_app": True} for i in range(300)]
    raw = copy.deepcopy(RAW_EVENT)
    raw["exception"]["values"][0]["stacktrace"]["frames"] = deep
    event = normalize_event(payload_for_storage({"action": "created", "data": {"error": raw}}))
    assert event["frames"][-1]["function"] == "step_299"


def test_legacy_webhook_plugin_format_uses_issue_id_for_grouping():
    payload = {
        "id": "4242",
        "project_slug": "shop-api",
        "url": "https://acme.sentry.io/issues/4242/",
        "culprit": "app.views.dashboard in get_dashboard",
        "event": copy.deepcopy(RAW_EVENT),
    }
    event = normalize_event(payload)
    assert event["issue_id"] == "4242"
    assert event["project"] == "shop-api"
    assert event["fingerprint"] == "sentry:shop-api:4242"
    assert event["issue_url"] == "https://acme.sentry.io/issues/4242/"


def test_integration_error_and_event_alert_formats():
    error_hook = {"action": "created", "data": {"error": copy.deepcopy(RAW_EVENT)}}
    alert_hook = {"action": "triggered", "data": {"event": copy.deepcopy(RAW_EVENT), "triggered_rule": "r"}}
    for payload in (error_hook, alert_hook):
        event = normalize_event(payload)
        assert event["error_type"] == "KeyError"
        assert len(event["frames"]) == 1


def test_integration_issue_format_without_stack_trace():
    payload = {
        "action": "created",
        "data": {
            "issue": {
                "id": "77",
                "title": "ZeroDivisionError: division by zero",
                "culprit": "billing.invoice in total",
                "metadata": {"type": "ZeroDivisionError", "value": "division by zero"},
                "project": {"slug": "billing"},
                "web_url": "https://acme.sentry.io/issues/77/",
            }
        },
    }
    assert should_process("issue", payload) == (True, "new issue")
    event = normalize_event(payload)
    assert event["error_type"] == "ZeroDivisionError"
    assert event["error_message"] == "division by zero"
    assert event["frames"] == []
    assert event["fingerprint"] == "sentry:billing:77"


def test_chained_exceptions_put_primary_frames_last():
    payload = {
        "event_id": "e",
        "exception": {
            "values": [
                {"type": "KeyError", "value": "cause", "stacktrace": {"frames": [{"filename": "app/a.py", "lineno": 1, "in_app": True}]}},
                {"type": "RuntimeError", "value": "wrapper", "stacktrace": {"frames": [{"filename": "app/b.py", "lineno": 9, "in_app": True}]}},
            ]
        },
    }
    event = normalize_event(payload)
    assert event["error_type"] == "RuntimeError"
    assert event["frames"][-1]["filename"] == "app/b.py"
    assert [c["type"] for c in event["exception_chain"]] == ["KeyError", "RuntimeError"]


def test_thread_stacktrace_fallback_and_vendor_heuristic():
    payload = {
        "event_id": "t",
        "message": "worker crashed",
        "threads": {"values": [{"crashed": True, "stacktrace": {"frames": [
            {"filename": "node_modules/express/router.js", "lineno": 3},
            {"filename": "src/server.ts", "lineno": 88, "function": "handle"},
        ]}}]},
    }
    event = normalize_event(payload)
    assert event["error_message"] == "worker crashed"
    assert [f["filename"] for f in event["frames"]] == ["src/server.ts"]


def test_rest_api_event_is_flattened():
    api_event = {
        "eventID": "api-1",
        "platform": "python",
        "entries": [
            {"type": "exception", "data": {"values": [{"type": "ValueError", "value": "bad", "stacktrace": {"frames": [
                {"filename": "app/x.py", "lineNo": 10, "inApp": True, "function": "f",
                 "context": [[9, "a = 1"], [10, "raise ValueError('bad')"], [11, "b = 2"]]}
            ]}}]}},
            {"type": "request", "data": {"url": "https://x.io/a", "method": "POST"}},
        ],
        "tags": [{"key": "environment", "value": "staging"}],
    }
    event = normalize_event({"event": flatten_api_event(api_event)})
    frame = event["frames"][-1]
    assert event["event_id"] == "api-1"
    assert frame["lineno"] == 10 and frame["context_line"] == "raise ValueError('bad')"
    assert frame["pre_context"] == ["a = 1"] and frame["post_context"] == ["b = 2"]
    assert event["environment"] == "staging"


def test_fingerprint_ignores_changing_message_values():
    a = normalize_event({"event_id": "1", "platform": "python", "exception": {"values": [
        {"type": "KeyError", "value": "order 1001 missing", "stacktrace": {"frames": [{"filename": "app/o.py", "function": "load", "lineno": 5}]}}]}})
    b = normalize_event({"event_id": "2", "platform": "python", "exception": {"values": [
        {"type": "KeyError", "value": "order 2002 missing", "stacktrace": {"frames": [{"filename": "app/o.py", "function": "load", "lineno": 6}]}}]}})
    assert compute_fingerprint(a) == compute_fingerprint(b)


def test_webhook_resource_filter():
    assert should_process("error", {})[0] is True
    assert should_process("event_alert", {})[0] is True
    assert should_process("issue", {"action": "resolved"})[0] is False
    assert should_process("installation", {"action": "created"})[0] is False
    assert should_process("metric_alert", {})[0] is False
    assert should_process(None, RAW_EVENT)[0] is True
    assert should_process(None, {"hello": "world"})[0] is False
