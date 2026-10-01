"""Push: token endpoints (scoped, validated, atomic) and the Expo send/receipt service
against a fake HTTP transport."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import push_service as ps
from tests.test_prod_fakes import FakeDB, clear_prod_env, client_for, wire_db_env

TOK = "ExponentPushToken[aaaaaaaaaaaaaaaaaaaa]"


def tok(i: int) -> str:
    return f"ExponentPushToken[device{i:014d}]"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)
    wire_db_env(monkeypatch)


# --- endpoints --------------------------------------------------------------------


def test_register_uses_the_verified_user_not_the_body() -> None:
    db = FakeDB()
    resp = client_for(db, "me").post(
        "/api/v1/me/push-token", json={"token": TOK, "platform": "ios", "userId": "victim"}
    )
    assert resp.status_code == 204
    fn, params = db.rpc_calls[-1]
    assert fn == "register_push_token"
    assert params["p_user_id"] == "me"
    assert db.tables["push_tokens"][0]["user_id"] == "me"


def test_register_is_one_atomic_rpc_not_separate_writes() -> None:
    db = FakeDB()
    client_for(db, "me").post("/api/v1/me/push-token", json={"token": TOK})
    writes = [c for c in db.calls if c[0] == "push_tokens"]
    assert writes == []  # everything happened inside register_push_token()


def test_register_caps_tokens_per_user() -> None:
    db = FakeDB()
    client = client_for(db, "me")
    for i in range(12):
        assert client.post("/api/v1/me/push-token", json={"token": tok(i)}).status_code == 204
    mine = [r["token"] for r in db.tables["push_tokens"] if r["user_id"] == "me"]
    assert len(mine) == 10 and tok(0) not in mine and tok(11) in mine


@pytest.mark.parametrize(
    "token", ["", "not-a-token", "ExponentPushToken[]", "ExponentPushToken[" + "a" * 300 + "]"]
)
def test_register_rejects_malformed_tokens(token: str) -> None:
    db = FakeDB()
    resp = client_for(db).post("/api/v1/me/push-token", json={"token": token})
    assert resp.status_code == 422
    assert db.rpc_calls == [] or db.rpc_calls[-1][0] != "register_push_token"


def test_register_requires_auth() -> None:
    assert (
        TestClient(create_app()).post("/api/v1/me/push-token", json={"token": TOK}).status_code
        == 401
    )


def test_push_endpoints_503_with_their_own_feature_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL")
    resp = client_for(FakeDB()).post("/api/v1/me/push-token", json={"token": TOK})
    assert resp.status_code == 503
    assert "push (Expo)" in resp.json()["detail"]


def test_unregister_only_removes_the_callers_token() -> None:
    db = FakeDB({"push_tokens": [{"user_id": "victim", "token": TOK}]})
    resp = client_for(db, "attacker").request(
        "DELETE", "/api/v1/me/push-token", json={"token": TOK}
    )
    assert resp.status_code == 204  # no oracle: same answer either way
    assert db.tables["push_tokens"] == [{"user_id": "victim", "token": TOK}]
    client_for(db, "victim").request("DELETE", "/api/v1/me/push-token", json={"token": TOK})
    assert db.tables["push_tokens"] == []


# --- pure helpers -----------------------------------------------------------------


def test_chunks_respect_batch_size() -> None:
    assert [len(c) for c in ps.chunks(list(range(250)), 100)] == [100, 100, 50]
    with pytest.raises(ValueError):
        list(ps.chunks([1], 0))


def test_parse_tickets_maps_errors_to_tokens() -> None:
    body = {
        "data": [
            {"status": "ok", "id": "t1"},
            {"status": "error", "message": "x", "details": {"error": "DeviceNotRegistered"}},
            {"status": "error", "details": {"error": "MessageRateExceeded"}},
        ]
    }
    res = ps.parse_tickets(["A", "B", "C"], body)
    assert res.sent == 1 and res.tickets == [("t1", "A")]
    assert res.dead_tokens == ["B"]
    assert res.errors == ["DeviceNotRegistered", "MessageRateExceeded"]


def test_parse_tickets_rejects_request_level_errors_and_mismatches() -> None:
    with pytest.raises(ps.PushError):
        ps.parse_tickets(["A"], {"errors": [{"code": "PUSH_TOO_MANY_EXPERIENCE_IDS"}]})
    with pytest.raises(ps.PushError):
        ps.parse_tickets(["A", "B"], {"data": [{"status": "ok", "id": "t"}]})


def test_parse_receipts() -> None:
    done, dead = ps.parse_receipts(
        {
            "data": {
                "t1": {"status": "ok"},
                "t2": {"status": "error", "details": {"error": "DeviceNotRegistered"}},
                "t3": {"status": "error", "details": {"error": "MessageTooBig"}},
            }
        }
    )
    assert done == {"t1", "t2", "t3"} and dead == {"t2"}


# --- HTTP client + service with a fake transport ----------------------------------


class FakeExpo:
    def __init__(self, dead: set[str] | None = None, dead_receipts: set[str] | None = None):
        self.requests: list[tuple[str, Any, dict[str, str]]] = []
        self.dead = dead or set()
        self.dead_receipts = dead_receipts or set()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((request.url.path, body, dict(request.headers)))
        if request.url.path.endswith("/send"):
            data = [
                (
                    {"status": "error", "details": {"error": "DeviceNotRegistered"}}
                    if m["to"] in self.dead
                    else {"status": "ok", "id": "ticket-" + m["to"]}
                )
                for m in body
            ]
            return httpx.Response(200, json={"data": data})
        receipts = {
            i: (
                {"status": "error", "details": {"error": "DeviceNotRegistered"}}
                if i in self.dead_receipts
                else {"status": "ok"}
            )
            for i in body["ids"]
        }
        return httpx.Response(200, json={"data": receipts})

    def client(self) -> ps.ExpoPushClient:
        return ps.ExpoPushClient(transport=httpx.MockTransport(self))


def test_send_batches_at_100_and_sends_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPO_ACCESS_TOKEN", "expo-secret")
    expo = FakeExpo()
    res = expo.client().send([ps.PushMessage(tok(i), "t", "b") for i in range(250)])
    assert [len(r[1]) for r in expo.requests] == [100, 100, 50]
    assert res.sent == 250
    assert expo.requests[0][2]["authorization"] == "Bearer expo-secret"


def test_send_without_access_token_sends_no_auth_header() -> None:
    expo = FakeExpo()
    expo.client().send([ps.PushMessage(TOK, "t", "b")])
    assert "authorization" not in expo.requests[0][2]


def test_http_errors_raise_push_error() -> None:
    client = ps.ExpoPushClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(ps.PushError):
        client.send([ps.PushMessage(TOK, "t", "b")])


def test_send_to_user_is_scoped_records_tickets_and_prunes_dead_tokens() -> None:
    db = FakeDB(
        {
            "push_tokens": [
                {"user_id": "u1", "token": tok(1)},
                {"user_id": "u1", "token": tok(2)},
                {"user_id": "u2", "token": tok(3)},
                {"user_id": "u2", "token": tok(2) + "x"},
            ]
        }
    )
    expo = FakeExpo(dead={tok(2)})
    res = ps.send_to_user(db, "u1", "Hi", "There", client=expo.client())
    sent_to = [m["to"] for m in expo.requests[0][1]]
    assert sent_to == [tok(1), tok(2)]  # never u2's devices
    assert res.dead_tokens == [tok(2)]
    remaining = {(r["user_id"], r["token"]) for r in db.tables["push_tokens"]}
    assert remaining == {("u1", tok(1)), ("u2", tok(3)), ("u2", tok(2) + "x")}
    assert db.tables["push_tickets"] == [
        {"ticket_id": "ticket-" + tok(1), "user_id": "u1", "token": tok(1)}
    ]


def test_send_to_user_with_no_devices_makes_no_http_call() -> None:
    expo = FakeExpo()
    assert ps.send_to_user(FakeDB(), "u1", "t", "b", client=expo.client()).sent == 0
    assert expo.requests == []


def test_check_receipts_prunes_dead_devices_for_their_owner_only() -> None:
    now = datetime(2026, 9, 30, 12, tzinfo=UTC)
    old = (now - timedelta(minutes=30)).isoformat()
    fresh = (now - timedelta(minutes=1)).isoformat()
    ancient = (now - timedelta(hours=30)).isoformat()
    db = FakeDB(
        {
            "push_tokens": [
                {"user_id": "u1", "token": tok(1)},
                {"user_id": "u2", "token": tok(1) + "b"},
            ],
            "push_tickets": [
                {"ticket_id": "dead", "user_id": "u1", "token": tok(1), "created_at": old},
                {"ticket_id": "fine", "user_id": "u2", "token": tok(9), "created_at": old},
                {"ticket_id": "young", "user_id": "u2", "token": tok(9), "created_at": fresh},
                {"ticket_id": "lost", "user_id": "u2", "token": tok(8), "created_at": ancient},
            ],
        }
    )

    class NoReceiptFor(FakeExpo):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            resp = super().__call__(request)
            data = resp.json()["data"]
            data.pop("lost", None)  # Expo already dropped it
            return httpx.Response(200, json={"data": data})

    expo = NoReceiptFor(dead_receipts={"dead"})
    out = ps.check_receipts(db, client=expo.client(), now=now)
    assert expo.requests[0][1]["ids"] == ["lost", "dead", "fine"]  # oldest first, not "young"
    assert out == {"checked": 3, "pruned": 1, "settled": 3}
    assert db.tables["push_tokens"] == [{"user_id": "u2", "token": tok(1) + "b"}]
    assert [t["ticket_id"] for t in db.tables["push_tickets"]] == ["young"]
