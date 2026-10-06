"""Idempotency keys (backend/idempotency.py): a write retried with the same key runs once.

Two halves. Behaviour, through the real app and the filter-honouring fake: a replay
returns the stored response without running the handler, a reused key on a different
request is refused, a failed request frees its key. And a static guard: every POST
under /api declares `Depends(idempotent())`, because the app replays queued writes
after an offline spell and a create without a key creates twice. Each has a negative
control; the selftest also plants a POST without it.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import APIRouter, Depends, FastAPI, Response
from fastapi.dependencies.models import Dependant

from backend import idempotency
from backend.idempotency import Claim, fingerprint, idempotent
from backend.main import create_app
from tests.test_prod_fakes import FakeDB, clear_prod_env, client_for, wire_db_env
from tests.test_wire_contract import _api_routes

KEY = "edit-name-replay-0001"  # any 8-128 of [A-Za-z0-9._:-]; the app sends a UUID


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)


# --- the static guard ----------------------------------------------------------------

# Paths outside /api are machine-to-machine (cron, behind a shared secret) and are
# idempotent by their own claim (`jobs_service.claim_run`), not by a client key.
GUARDED_PREFIX = "/api/"
# "METHOD /path" -> why this POST may run twice. Shrink, don't grow.
NOT_IDEMPOTENT: dict[str, str] = {}


def _has_marker(dep: Dependant) -> bool:
    if getattr(dep.call, idempotency.MARKER, False):
        return True
    return any(_has_marker(d) for d in dep.dependencies)


def posts_without_idempotency(app: FastAPI) -> list[str]:
    missing = []
    for route in _api_routes(app.routes):
        if "POST" not in (route.methods or ()) or not route.path.startswith(GUARDED_PREFIX):
            continue
        if not _has_marker(route.dependant):
            missing.append(f"POST {route.path}")
    return sorted(m for m in missing if m not in NOT_IDEMPOTENT)


def test_every_api_post_takes_an_idempotency_key() -> None:
    missing = posts_without_idempotency(create_app())
    assert not missing, (
        f"POST routes without Depends(idempotent()): {missing}. The app replays queued "
        "writes; without a key a replayed create runs twice. Add it after rate_limit(...), "
        "or list the route in NOT_IDEMPOTENT with the reason it is safe to repeat."
    )


def test_not_idempotent_allowlist_is_live_and_justified() -> None:
    posts = {f"POST {r.path}" for r in _api_routes(create_app().routes) if "POST" in (r.methods or ())}
    for route, reason in NOT_IDEMPOTENT.items():
        assert route in posts, f"{route}: no such route; drop it from NOT_IDEMPOTENT"
        assert len(reason) > 40, route


def test_guard_catches_a_planted_post_without_the_dependency() -> None:
    router = APIRouter(prefix="/api/v1")

    @router.post("/things")
    def create_thing() -> None: ...

    @router.post("/keyed", dependencies=[Depends(idempotent())])
    def create_keyed() -> None: ...

    @router.get("/things")
    def list_things() -> None: ...

    app = FastAPI()
    app.include_router(router)

    @app.post("/internal/cron/x")
    def cron() -> None: ...

    assert posts_without_idempotency(app) == ["POST /api/v1/things"]


def test_guard_finds_the_marker_nested_in_a_sub_dependency() -> None:
    def wrapper(_: None = Depends(idempotent())) -> None: ...

    app = FastAPI()

    @app.post("/api/v1/wrapped", dependencies=[Depends(wrapper)])
    def wrapped() -> None: ...

    assert posts_without_idempotency(app) == []


# --- behaviour -------------------------------------------------------------------------


def _patch(client: Any, body: dict[str, Any], key: str | None = KEY) -> Any:
    headers = {"Idempotency-Key": key} if key else {}
    return client.patch("/api/v1/me", json=body, headers=headers)


def _profile_writes(db: FakeDB) -> int:
    return sum(1 for t, op, _ in db.calls if t == "profiles" and op == "upsert")


def test_a_replay_returns_the_stored_response_without_running_again() -> None:
    db = FakeDB({"profiles": []})
    client = client_for(db, "u1")
    first = _patch(client, {"displayName": "Riley"})
    assert first.status_code == 200
    assert "idempotent-replayed" not in first.headers
    db.tables["profiles"][0]["display_name"] = "Changed elsewhere"
    again = _patch(client, {"displayName": "Riley"})
    assert again.status_code == 200
    assert again.json() == first.json()  # the stored response, not a fresh read
    assert again.headers["idempotent-replayed"] == "true"
    assert again.headers["content-type"] == first.headers["content-type"]
    assert _profile_writes(db) == 1


def test_no_key_means_no_bookkeeping() -> None:
    db = FakeDB({"profiles": []})
    client = client_for(db, "u1")
    for _ in range(2):
        assert _patch(client, {"displayName": "Riley"}, key=None).status_code == 200
    assert _profile_writes(db) == 2
    assert "idempotency_keys" not in db.tables


def test_the_same_key_on_a_different_request_is_refused() -> None:
    db = FakeDB({"profiles": []})
    client = client_for(db, "u1")
    _patch(client, {"displayName": "Riley"})
    resp = _patch(client, {"displayName": "Someone else"})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "idempotency_key_reused"
    assert _profile_writes(db) == 1


def test_a_request_still_running_is_409_with_retry_after() -> None:
    db = FakeDB({"profiles": []})
    body = b'{"displayName":"Riley"}'
    db.tables["idempotency_keys"] = [
        {"user_id": "u1", "key": KEY, "response_status": None,
         "fingerprint": fingerprint("PATCH", "/api/v1/me", body)}
    ]  # fmt: skip
    resp = client_for(db, "u1").patch(
        "/api/v1/me",
        content=body,
        headers={"Idempotency-Key": KEY, "Content-Type": "application/json"},
    )
    assert resp.status_code == 409
    assert resp.headers["retry-after"] == "1"
    assert _profile_writes(db) == 0


def test_keys_are_per_user() -> None:
    db = FakeDB({"profiles": []})
    _patch(client_for(db, "u1"), {"displayName": "Riley"})
    other = _patch(client_for(db, "u2"), {"displayName": "Riley"})
    assert other.status_code == 200
    assert "idempotent-replayed" not in other.headers
    assert other.json()["id"] == "u2"  # never u1's stored response
    assert _profile_writes(db) == 2


def test_a_failed_request_frees_its_key_so_the_retry_runs() -> None:
    db = FakeDB({"profiles": []})
    client = client_for(db, "u1")
    bad = _patch(client, {"displayName": "x" * 81})  # 422 from validation, after the claim
    assert bad.status_code == 422
    assert db.tables.get("idempotency_keys", []) == []
    assert _patch(client, {"displayName": "x" * 81}).status_code == 422  # not "reused"


def test_a_crash_frees_its_key() -> None:
    db = FakeDB({"profiles": []})
    client = client_for(db, "u1")

    def explode(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("handler bug")

    db.table = lambda name: (  # type: ignore[method-assign]
        FakeDB.table(db, name) if name == "idempotency_keys" else explode()
    )
    resp = _patch(client, {"displayName": "Riley"})
    assert resp.status_code == 500
    assert db.tables.get("idempotency_keys", []) == []


def test_a_malformed_key_is_400() -> None:
    resp = _patch(client_for(FakeDB({"profiles": []}), "u1"), {}, key="short")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_idempotency_key"


def test_the_claim_failing_is_503_not_an_unprotected_write() -> None:
    db = FakeDB({"profiles": []})
    db.rpc_error = ConnectionError("db blip")
    import backend.ratelimit

    resp = _patch(client_for(db, "u1"), {"displayName": "Riley"})
    assert backend.ratelimit.FAIL_OPEN  # the limiter let it through; the claim did not
    assert resp.status_code == 503
    assert resp.json()["detail"] == "idempotency_unavailable"
    assert _profile_writes(db) == 0


def test_a_204_replays_as_a_204(monkeypatch: pytest.MonkeyPatch) -> None:
    wire_db_env(monkeypatch)  # push is "configured" once Supabase is
    db = FakeDB({"push_tokens": []})
    client = client_for(db, "u1")
    body = {"token": "ExponentPushToken[abcdefghijklmnop]", "platform": "ios"}
    headers = {"Idempotency-Key": KEY}
    first = client.post("/api/v1/me/push-token", json=body, headers=headers)
    again = client.post("/api/v1/me/push-token", json=body, headers=headers)
    assert (first.status_code, again.status_code) == (204, 204)
    assert again.content == b""
    assert again.headers["idempotent-replayed"] == "true"
    assert [c[0] for c in db.rpc_calls].count("register_push_token") == 1


def test_fingerprint_separates_method_path_and_body() -> None:
    base = fingerprint("POST", "/a", b"{}")
    assert base == fingerprint("post", "/a", b"{}")
    assert len({base, fingerprint("PATCH", "/a", b"{}"), fingerprint("POST", "/b", b"{}"),
                fingerprint("POST", "/a", b"{ }")}) == 4  # fmt: skip
    assert fingerprint("POST", "/ab", b"") != fingerprint("POST", "/a", b"b")


def test_settle_stores_2xx_and_releases_everything_else() -> None:
    db = FakeDB({"idempotency_keys": [{"user_id": "u1", "key": "k", "response_status": None}]})
    idempotency.settle(Claim(db, "u1", "k"), 201, b'{"id":1}', "application/json")
    assert db.tables["idempotency_keys"][0]["response_status"] == 201
    assert db.tables["idempotency_keys"][0]["response_body"] == '{"id":1}'
    db2 = FakeDB({"idempotency_keys": [{"user_id": "u1", "key": "k", "response_status": None}]})
    claim = Claim(db2, "u1", "k")
    idempotency.settle(claim, 503, b"", None)
    idempotency.settle(claim, 200, b"{}", None)  # settled once only
    assert db2.tables["idempotency_keys"] == []


def test_settle_releases_when_the_body_cannot_be_stored() -> None:
    db = FakeDB({"idempotency_keys": [{"user_id": "u1", "key": "k", "response_status": None}]})
    idempotency.settle(Claim(db, "u1", "k"), 200, b"\xff\xfe", "application/octet-stream")
    assert db.tables["idempotency_keys"] == []


def test_release_never_masks_the_original_error() -> None:
    class Down(FakeDB):
        def table(self, name: str):  # type: ignore[override]
            raise ConnectionError("db down")

    idempotency._release(Down(), "u1", "k")  # logs, does not raise


def test_untouched_requests_pass_through_the_middleware() -> None:
    app = FastAPI()

    @app.get("/plain")
    def plain() -> Response:
        return Response("ok")

    app.add_middleware(idempotency.IdempotencyMiddleware)
    from fastapi.testclient import TestClient

    assert TestClient(app).get("/plain").text == "ok"
