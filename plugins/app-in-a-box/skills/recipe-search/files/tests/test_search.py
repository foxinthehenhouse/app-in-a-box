"""Search (recipe-search): the route, the cursor, and that the query runs AS THE USER.

The SQL itself (ranking, keyset paging, and that one user can never see another's rows,
even through a planted SECURITY DEFINER rewrite) is proven against real Postgres by
supabase/tests/database/search.test.sql. These tests pin the backend's half: the search
goes through a client carrying the caller's token, never the service key, and the
cursor and paging behave.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from backend.auth import CurrentUser
from backend.config import FEATURE_CONFIG
from backend.main import create_app
from backend.services import search_service as ss
from tests.test_prod_fakes import (
    FakeDB,
    Result,
    clear_prod_env,
    client_for,
    wire_db_env,
)

A, B = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"


def _id(n: int) -> str:
    return f"a0000000-0000-4000-8000-{n:012d}"


class FakeUserDB:
    """Stands in for PostgREST called with one user's token: search_items() sees only
    that user's rows (what RLS + the function's own filter do), ranks a title hit over
    a body hit, and pages by (rank desc, id asc) like the SQL."""

    def __init__(self, uid: str, rows: list[dict[str, Any]]) -> None:
        self.uid, self.rows = uid, rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, fn: str, params: dict[str, Any]) -> Any:
        self.calls.append((fn, dict(params)))
        assert fn == "search_items"
        words = params["p_query"].lower().split()
        hits = []
        for r in self.rows:
            if r["user_id"] != self.uid:
                continue
            title, body = r["title"].lower(), r["body"].lower()
            if all(w in title or w in body for w in words):
                rank = 1.0 if any(w in title for w in words) else 0.4
                hits.append(
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "snippet": r["body"],
                        "rank": rank,
                    }
                )
        hits.sort(key=lambda h: (-h["rank"], h["id"]))
        ar, aid = params["p_after_rank"], params["p_after_id"]
        if ar is not None and aid is not None:
            hits = [h for h in hits if h["rank"] < ar or (h["rank"] == ar and h["id"] > aid)]
        page = hits[: params["p_limit"]]
        return type("Rpc", (), {"execute": lambda self: Result(page)})()


ROWS = [
    {"id": _id(1), "user_id": A, "title": "Tomato plan", "body": "water daily"},
    {"id": _id(2), "user_id": A, "title": "Shopping", "body": "buy tomato paste"},
    {"id": _id(3), "user_id": A, "title": "Shopping", "body": "buy tomato paste"},
    {"id": _id(9), "user_id": B, "title": "Tomato tomato", "body": "tomato secret"},
]


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)
    wire_db_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "sb_publishable_test")


def _client(
    uid: str = A, rows: list[dict[str, Any]] | None = None
) -> tuple[TestClient, FakeDB, FakeUserDB]:
    service, user_db = FakeDB(), FakeUserDB(uid, ROWS if rows is None else rows)
    app = create_app()
    app.dependency_overrides[ss.get_user_db] = lambda: user_db
    return client_for(service, uid, app), service, user_db


def test_requires_auth() -> None:
    assert TestClient(create_app()).get("/api/v1/search", params={"q": "tomato"}).status_code == 401


def test_finds_only_the_callers_rows_best_first() -> None:
    client, _, _ = _client(A)
    body = client.get("/api/v1/search", params={"q": "tomato"}).json()
    assert [h["id"] for h in body["items"]] == [_id(1), _id(2), _id(3)]
    assert body["nextCursor"] is None
    assert set(body["items"][0]) == {"id", "title", "snippet"}  # rank stays server-side


def test_another_users_term_finds_nothing() -> None:
    client, _, _ = _client(A)
    assert client.get("/api/v1/search", params={"q": "secret"}).json()["items"] == []


def test_search_never_uses_the_service_client() -> None:
    """The service key bypasses RLS: only the rate limiter may use it here."""
    client, service, user_db = _client(A)
    client.get("/api/v1/search", params={"q": "tomato"})
    assert [fn for fn, _ in service.rpc_calls] == ["rate_limit_hit"]
    assert [fn for fn, _ in user_db.calls] == ["search_items"]


def test_the_request_cannot_name_whose_rows() -> None:
    """No user id travels to the function at all: whose rows is the token's business."""
    client, _, user_db = _client(A)
    client.get("/api/v1/search", params={"q": "tomato", "userId": B, "user_id": B})
    assert set(user_db.calls[0][1]) == {
        "p_query",
        "p_limit",
        "p_after_rank",
        "p_after_id",
    }


def test_keyset_pages_walk_every_row_once() -> None:
    client, _, user_db = _client(A)
    first = client.get("/api/v1/search", params={"q": "tomato", "limit": 2}).json()
    assert [h["id"] for h in first["items"]] == [_id(1), _id(2)]
    assert user_db.calls[0][1]["p_limit"] == 3  # one extra row says whether there's more
    second = client.get(
        "/api/v1/search",
        params={"q": "tomato", "limit": 2, "cursor": first["nextCursor"]},
    ).json()
    assert [h["id"] for h in second["items"]] == [_id(3)]
    assert second["nextCursor"] is None


@pytest.mark.parametrize("cursor", ["nope", "W10", ss.encode_cursor(0.5, "not-a-uuid")])
def test_a_cursor_this_api_did_not_issue_is_a_422(cursor: str) -> None:
    client, _, user_db = _client(A)
    resp = client.get("/api/v1/search", params={"q": "tomato", "cursor": cursor})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "invalid_cursor"
    assert user_db.calls == []


@pytest.mark.parametrize(
    "params",
    [{}, {"q": ""}, {"q": "x" * 201}, {"q": "a", "limit": 0}, {"q": "a", "limit": 41}],
)
def test_rejects_bad_parameters(params: dict[str, Any]) -> None:
    client, _, _ = _client(A)
    assert client.get("/api/v1/search", params=params).status_code == 422


def test_a_blank_query_is_an_empty_page_not_a_database_call() -> None:
    client, _, user_db = _client(A)
    resp = client.get("/api/v1/search", params={"q": "   "})
    assert resp.status_code == 200 and resp.json() == {"items": [], "nextCursor": None}
    assert user_db.calls == []


def test_503_names_the_feature_when_the_anon_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUPABASE_ANON_KEY")
    resp = client_for(FakeDB(), A).get("/api/v1/search", params={"q": "tomato"})
    assert resp.status_code == 503
    assert ss.FEATURE in resp.json()["detail"]


def test_search_is_registered_so_health_reports_it_unwired() -> None:
    assert FEATURE_CONFIG[ss.FEATURE] == ("SUPABASE_URL", "SUPABASE_ANON_KEY")


def test_user_db_carries_the_callers_token_not_the_service_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_must_not_be_used")
    gen = ss.get_user_db(
        CurrentUser(id=A),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="user.jwt.token"),
    )
    client = next(gen)
    headers = dict(client.session.headers)
    assert headers["authorization"] == "Bearer user.jwt.token"
    assert headers["apikey"] == "sb_publishable_test"
    assert "sb_secret_must_not_be_used" not in str(headers)
    gen.close()


@pytest.mark.parametrize("rank", [0.0, 0.1, 1 / 3, 0.0607927, 1e-30, 123.456])
def test_cursor_round_trips_exactly(rank: float) -> None:
    assert ss.decode_cursor(ss.encode_cursor(rank, _id(7))) == (rank, _id(7))


@pytest.mark.parametrize("rank", [math.nan, math.inf])
def test_cursor_rejects_non_finite_ranks(rank: float) -> None:
    with pytest.raises(ValueError):
        ss.decode_cursor(ss.encode_cursor(rank, _id(7)))
