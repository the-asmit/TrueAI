"""
HTTP API tests through the real FastAPI app, database (PostgREST + Postgres)
and Redis.  Celery publishing is captured instead of sent to a worker.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import time
import uuid

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from tests.conftest import user_jwt
from tests.helpers import SENTRY_EVENT

pytestmark = pytest.mark.integration


@pytest.fixture()
def client(redis_clean, monkeypatch):
    import main
    from app.workers import tasks

    queued: list[str] = []

    class _Result:
        def __init__(self, incident_id: str) -> None:
            self.id = f"task-{incident_id[:8]}"

    def _delay(incident_id: str):
        queued.append(incident_id)
        return _Result(incident_id)

    monkeypatch.setattr(tasks.process_incident, "delay", _delay)
    with TestClient(main.app) as test_client:
        test_client.queued = queued  # type: ignore[attr-defined]
        yield test_client


@pytest.fixture()
def user(make_user):
    user_id = make_user()
    return {"id": user_id, "headers": {"Authorization": f"Bearer {user_jwt(user_id)}"}}


def _new_key(client, user) -> dict:
    response = client.post("/auth/api-keys", json={"name": "Sentry prod"}, headers=user["headers"])
    assert response.status_code == 201, response.text
    return response.json()


def _event(event_id: str | None = None, issue: str | None = None) -> dict:
    payload = copy.deepcopy(SENTRY_EVENT)
    payload["event_id"] = event_id or uuid.uuid4().hex
    if issue:
        return {"id": issue, "project_slug": "shop", "url": f"https://acme.sentry.io/issues/{issue}/", "event": payload}
    return payload


# ================================================================== #
# Authentication                                                       #
# ================================================================== #

def test_protected_routes_require_a_valid_session(client, user):
    assert client.get("/incidents").status_code == 401
    assert client.get("/incidents", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    expired = user_jwt(user["id"], expires_in=-120)
    assert client.get("/incidents", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    anon = user_jwt(user["id"], role="anon")
    assert client.get("/incidents", headers={"Authorization": f"Bearer {anon}"}).status_code == 401
    assert client.get("/incidents", headers=user["headers"]).status_code == 200


def test_es256_tokens_are_verified_against_the_jwks(user, monkeypatch):
    from app.auth import jwt as jwt_module
    from app.core.config import settings

    private_key = ec.generate_private_key(ec.SECP256R1())
    token = pyjwt.encode(
        {"sub": user["id"], "role": "authenticated", "aud": "authenticated", "iss": f"{settings.SUPABASE_URL}/auth/v1",
         "iat": int(time.time()), "exp": int(time.time()) + 300},
        private_key, algorithm="ES256", headers={"kid": "k1"},
    )

    class _JWKS:
        def get_signing_key_from_jwt(self, token):
            return type("Key", (), {"key": private_key.public_key()})()

    monkeypatch.setattr(jwt_module, "_jwks_client", lambda: _JWKS())
    assert jwt_module.get_user_id_from_token(token) == user["id"]

    forged = pyjwt.encode({"sub": user["id"], "role": "authenticated"}, "", algorithm="none")
    with pytest.raises(Exception):
        jwt_module.get_user_id_from_token(forged)


def test_api_keys_cannot_perform_account_actions(client, user):
    key = _new_key(client, user)
    api_headers = {"X-API-Key": key["raw_key"]}
    assert client.get("/incidents", headers=api_headers).status_code == 200
    assert client.post("/auth/api-keys", headers=api_headers).status_code == 401
    assert client.delete("/auth/account", headers=api_headers).status_code == 401


def test_api_key_lifecycle_never_exposes_secrets(client, user):
    created = _new_key(client, user)
    assert created["raw_key"].startswith("tai_")
    assert created["webhook_url"] == f"http://testserver/webhook/sentry?key={created['raw_key']}"

    listed = client.get("/auth/api-keys", headers=user["headers"]).json()
    assert listed[0]["key_prefix"] == created["key_prefix"] and "api_key" not in listed[0] and "raw_key" not in listed[0]

    assert client.delete(f"/auth/api-keys/{created['id']}", headers=user["headers"]).status_code == 204
    response = client.post(f"/webhook/sentry?key={created['raw_key']}", json=_event())
    assert response.status_code == 401


# ================================================================== #
# Webhook                                                              #
# ================================================================== #

def test_webhook_rejects_bad_requests(client, user):
    key = _new_key(client, user)["raw_key"]
    assert client.post("/webhook/sentry", json=_event()).status_code == 401
    assert client.post("/webhook/sentry?key=tai_wrongwrongwrongwrongwrong", json=_event()).status_code == 401
    assert client.post(f"/webhook/sentry?key={key}", content=b"{not json", headers={"Content-Type": "application/json"}).status_code == 400
    huge = b'{"x": "' + b"a" * (2 * 1024 * 1024 + 10) + b'"}'
    assert client.post(f"/webhook/sentry?key={key}", content=huge, headers={"Content-Type": "application/json"}).status_code == 413


def test_webhook_accepts_stores_scrubbed_payload_and_queues(client, user, db):
    key = _new_key(client, user)["raw_key"]
    payload = _event()
    payload["request"] = {"url": "https://shop/x", "headers": {"Cookie": "sid=supersecret"}}
    response = client.post(f"/webhook/sentry?key={key}", json=payload)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["processed"] is True and body["queued"] is True
    assert client.queued == [body["incident_id"]]  # type: ignore[attr-defined]

    row = db.get_incident_for_worker(body["incident_id"])
    assert row["status"] == "queued" and row["error_type"] == "KeyError"
    assert "supersecret" not in json.dumps(row["raw_payload"])


def test_duplicate_deliveries_and_repeat_occurrences_are_grouped(client, user, db):
    key = _new_key(client, user)["raw_key"]
    first = client.post(f"/webhook/sentry?key={key}", json=_event("same-event", issue="9001")).json()
    duplicate = client.post(f"/webhook/sentry?key={key}", json=_event("same-event", issue="9001")).json()
    repeat = client.post(f"/webhook/sentry?key={key}", json=_event("next-event", issue="9001")).json()

    assert duplicate == {"accepted": True, "processed": False, "reason": "duplicate event", "event_id": "same-event"}
    assert repeat["grouped"] is True and repeat["incident_id"] == first["incident_id"]
    assert db.get_incident(first["incident_id"], user["id"])["occurrence_count"] == 2
    assert len(client.queued) == 1  # type: ignore[attr-defined]


def test_non_error_hooks_are_acknowledged_without_processing(client, user):
    key = _new_key(client, user)["raw_key"]
    response = client.post(
        f"/webhook/sentry?key={key}", json={"action": "resolved", "data": {"issue": {"id": "1"}}},
        headers={"sentry-hook-resource": "issue"},
    )
    assert response.status_code == 202 and response.json()["processed"] is False


def test_signature_is_enforced_once_the_user_saves_a_secret(client, user):
    key = _new_key(client, user)["raw_key"]
    saved = client.put("/integrations/sentry", json={"webhook_secret": "whsec-test"}, headers=user["headers"])
    assert saved.status_code == 200 and saved.json()["has_webhook_secret"] is True

    body = json.dumps(_event()).encode()
    unsigned = client.post(f"/webhook/sentry?key={key}", content=body, headers={"Content-Type": "application/json"})
    assert unsigned.status_code == 401
    signature = hmac.new(b"whsec-test", body, hashlib.sha256).hexdigest()
    signed = client.post(
        f"/webhook/sentry?key={key}", content=body,
        headers={"Content-Type": "application/json", "sentry-hook-signature": signature},
    )
    assert signed.status_code == 202


def test_webhook_rate_limit_per_key(client, user, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 3)
    key = _new_key(client, user)["raw_key"]
    codes = [client.post(f"/webhook/sentry?key={key}", json=_event()).status_code for _ in range(4)]
    assert codes[:3] == [202, 202, 202] and codes[3] == 429


# ================================================================== #
# Incidents                                                            #
# ================================================================== #

def test_users_cannot_read_tables_directly(client, user):
    # A signed-in user's own token reaches nothing through the database's public API:
    # what they see comes only from the TrueAI API (no run record, models or token usage).
    import httpx

    from tests.conftest import INTEGRATION_URL

    key = _new_key(client, user)
    client.post(f"/webhook/sentry?key={key['raw_key']}", json=_event())
    rest_headers = {"Authorization": user["headers"]["Authorization"], "apikey": user_jwt(user["id"], role="anon")}
    for table in ("pipeline_steps", "incidents", "fixes", "pull_requests", "api_keys", "github_tokens"):
        response = httpx.get(f"{INTEGRATION_URL}/rest/v1/{table}?select=*", headers=rest_headers, timeout=10)
        assert response.status_code in (401, 403), (table, response.status_code, response.text[:200])


def test_tenants_cannot_see_each_others_incidents(client, user, make_user):
    key = _new_key(client, user)["raw_key"]
    incident_id = client.post(f"/webhook/sentry?key={key}", json=_event()).json()["incident_id"]

    other_id = make_user()
    other = {"Authorization": f"Bearer {user_jwt(other_id)}"}
    assert client.get(f"/incidents/{incident_id}", headers=other).status_code == 404
    assert client.get("/incidents", headers=other).json()["total"] == 0
    assert client.patch(f"/incidents/{incident_id}", json={"status": "ignored"}, headers=other).status_code == 404
    assert client.delete(f"/incidents/{incident_id}", headers=other).status_code == 404


def test_list_filters_search_stats_and_detail(client, user, db):
    key = _new_key(client, user)["raw_key"]
    ids = [client.post(f"/webhook/sentry?key={key}", json=_event(issue=str(n))).json()["incident_id"] for n in (1, 2)]
    db.update_incident(ids[1], {"status": "flagged", "error_type": "ValueError"})

    listing = client.get("/incidents?status=flagged", headers=user["headers"]).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == ids[1]
    assert client.get("/incidents?q=ValueError", headers=user["headers"]).json()["total"] == 1
    assert client.get("/incidents?q=%27%29%2C(injection", headers=user["headers"]).status_code == 200

    stats = client.get("/incidents/stats", headers=user["headers"]).json()
    assert stats["by_status"] == {"queued": 1, "flagged": 1} and stats["total"] == 2

    detail = client.get(f"/incidents/{ids[0]}", headers=user["headers"]).json()
    assert detail["status"] == "queued" and detail["analysis"] is None
    # The internal run record (timeline, models, token usage, attempts) is never sent to users.
    assert not {"steps", "attempts", "llm_input_tokens", "llm_output_tokens", "started_at"} & set(detail)
    assert detail["created_at"].endswith("Z") or "+" in detail["created_at"]
    assert client.get(f"/incidents/{uuid.uuid4()}", headers=user["headers"]).status_code == 404


def test_triage_actions_and_reanalysis(client, user, db):
    key = _new_key(client, user)["raw_key"]
    incident_id = client.post(f"/webhook/sentry?key={key}", json=_event()).json()["incident_id"]

    assert client.patch(f"/incidents/{incident_id}", json={"status": "resolved"}, headers=user["headers"]).status_code == 409
    assert client.post(f"/incidents/{incident_id}/reanalyze", headers=user["headers"]).status_code == 409

    db.update_incident(incident_id, {"status": "failed"})
    assert client.patch(f"/incidents/{incident_id}", json={"status": "processing"}, headers=user["headers"]).status_code == 422
    assert client.patch(f"/incidents/{incident_id}", json={"status": "ignored"}, headers=user["headers"]).json()["status"] == "ignored"

    response = client.post(f"/incidents/{incident_id}/reanalyze", headers=user["headers"])
    assert response.status_code == 200 and response.json() == {"status": "queued"}
    row = db.get_incident(incident_id, user["id"], columns="status,analysis_run")
    assert row["status"] == "queued" and row["analysis_run"] == 2
    assert client.queued[-1] == incident_id  # type: ignore[attr-defined]


# ================================================================== #
# GitHub OAuth hand-off                                                #
# ================================================================== #

def test_github_oauth_binds_the_token_to_the_user_who_started_it(client, user, make_user, monkeypatch, db):
    from urllib.parse import parse_qs, urlsplit

    from app.api.routes import github as github_routes

    async def _exchange(code):
        return "gho_" + "x" * 36, "repo,read:user"

    async def _profile(token):
        return "alice", 42

    monkeypatch.setattr(github_routes, "_exchange_code", _exchange)
    monkeypatch.setattr(github_routes, "_fetch_github_user", _profile)

    auth_url = client.get("/auth/github/authorize?return_to=/onboarding", headers=user["headers"]).json()["auth_url"]
    state = parse_qs(urlsplit(auth_url).query)["state"][0]

    # A tampered state is rejected and bounced back to the dashboard.
    bad = client.get(f"/auth/github/callback?code=c&state={state[:-2]}xx", follow_redirects=False)
    assert bad.status_code == 303 and "github_error=invalid_state" in bad.headers["location"]

    ok = client.get(f"/auth/github/callback?code=c&state={state}", follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"].startswith("http://localhost:3000/github/complete?handoff=")
    handoff = parse_qs(urlsplit(ok.headers["location"]).query)["handoff"][0]

    # The same state cannot be replayed (single-use nonce).
    replay = client.get(f"/auth/github/callback?code=c&state={state}", follow_redirects=False)
    assert "github_error=invalid_state" in replay.headers["location"]

    # Another signed-in account cannot claim the hand-off …
    attacker = {"Authorization": f"Bearer {user_jwt(make_user())}"}
    assert client.post("/auth/github/complete", json={"handoff": handoff}, headers=attacker).status_code == 403
    # … and the hand-off is single-use, so even the right user must restart after that attempt.
    assert client.post("/auth/github/complete", json={"handoff": handoff}, headers=user["headers"]).status_code == 400

    auth_url = client.get("/auth/github/authorize?return_to=/onboarding", headers=user["headers"]).json()["auth_url"]
    state = parse_qs(urlsplit(auth_url).query)["state"][0]
    handoff = parse_qs(urlsplit(client.get(f"/auth/github/callback?code=c&state={state}", follow_redirects=False).headers["location"]).query)["handoff"][0]
    completed = client.post("/auth/github/complete", json={"handoff": handoff}, headers=user["headers"])
    assert completed.status_code == 200 and completed.json() == {"github_username": "alice", "return_to": "/onboarding"}

    row = db.get_github_row(user["id"])
    assert row["github_username"] == "alice" and not row["access_token"].startswith("gho_")  # encrypted at rest
    me = client.get("/auth/me", headers=user["headers"]).json()
    assert me["github_connected"] is True and "agents" not in me


def test_account_deletion_removes_every_row(client, user, db, monkeypatch):
    from app.services import supabase

    key = _new_key(client, user)["raw_key"]
    client.post(f"/webhook/sentry?key={key}", json=_event())
    client.post("/auth/profile", json={"full_name": "Alice"}, headers=user["headers"])

    deleted_auth_users: list[str] = []
    monkeypatch.setattr(supabase, "delete_auth_user", lambda uid: deleted_auth_users.append(uid))
    assert client.delete("/auth/account", headers=user["headers"]).status_code == 204
    assert deleted_auth_users == [user["id"]]
    assert db.list_incidents(user["id"], page=1, page_size=10)[1] == 0
    assert db.list_api_keys(user["id"]) == [] and db.get_profile(user["id"]) is None
