"""Keyset pagination (backend/pagination.py): `Page[T]`, the cursor, and the query.

Walks a real (fake) table page by page, including rows that share the first order
value (the tie a timestamp-only cursor would skip or repeat), and rows inserted between
page loads (which an offset would shift). Also proves a `Page[Thing]` response pairs with
a `ThingPageWire` interface under the wire-contract guard, so the first list endpoint
someone adds is guarded like every other.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.auth import CurrentUser, get_current_user
from backend.db import get_db
from backend.pagination import (
    Cursor,
    Limit,
    Page,
    after_filter,
    decode_cursor,
    encode_cursor,
    keyset,
    page,
)
from backend.routers.me import Wire
from tests.test_prod_fakes import FakeDB
from tests.test_wire_contract import compare, ts_interface

ORDER = ("created_at", "id")


class Thing(Wire):
    id: str
    created_at: str


def _db() -> FakeDB:
    rows = [
        # Three rows share a created_at: the cursor's tiebreaker (id) must order them.
        {"id": f"t{i:02d}", "user_id": "u1", "created_at": f"2026-01-0{1 + i // 3}T00:00:00+00:00"}
        for i in range(10)
    ]
    rows.append({"id": "other", "user_id": "u2", "created_at": "2026-01-01T00:00:00+00:00"})
    return FakeDB({"things": rows})


def _app(db: FakeDB) -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/things", response_model=Page[Thing], response_model_by_alias=True)
    def list_things(
        cursor: Cursor = None,
        limit: Limit = 4,
        user: CurrentUser = Depends(get_current_user),
        db: Any = Depends(get_db),
    ) -> Page[Thing]:
        query = db.table("things").select("*").eq("user_id", user.id)
        rows = keyset(query, ORDER, cursor=cursor, limit=limit).execute().data or []
        return page(rows, ORDER, limit, Thing)

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="u1")
    app.dependency_overrides[get_db] = lambda: db
    return app


def _walk(client: TestClient, limit: int = 4) -> list[str]:
    seen: list[str] = []
    cursor = None
    for _ in range(20):
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        body = client.get("/api/v1/things", params=params).json()
        assert set(body) == {"items", "nextCursor"}
        seen += [t["id"] for t in body["items"]]
        cursor = body["nextCursor"]
        if cursor is None:
            return seen
    raise AssertionError("pagination never ended")


def test_walks_every_row_once_in_order_and_only_the_callers() -> None:
    assert _walk(TestClient(_app(_db()))) == [f"t{i:02d}" for i in range(10)]


@pytest.mark.parametrize("limit", [1, 3, 10, 11])
def test_page_size_never_drops_or_repeats_a_tie(limit: int) -> None:
    assert _walk(TestClient(_app(_db())), limit) == [f"t{i:02d}" for i in range(10)]


def test_an_exact_last_page_has_no_cursor() -> None:
    body = TestClient(_app(_db())).get("/api/v1/things", params={"limit": 10}).json()
    assert len(body["items"]) == 10
    assert body["nextCursor"] is None


def test_rows_inserted_before_the_cursor_do_not_shift_the_next_page() -> None:
    db = _db()
    client = TestClient(_app(db))
    first = client.get("/api/v1/things", params={"limit": 4}).json()
    db.tables["things"].insert(0, {"id": "t00a", "user_id": "u1", "created_at": "2025-12-31"})
    second = client.get("/api/v1/things", params={"limit": 4, "cursor": first["nextCursor"]})
    assert [t["id"] for t in second.json()["items"]] == ["t04", "t05", "t06", "t07"]


@pytest.mark.parametrize("cursor", ["!!!", "bm90IGpzb24", encode_cursor({"a": 1}, ["a"])])
def test_a_garbage_cursor_is_400(cursor: str) -> None:
    resp = TestClient(_app(_db())).get("/api/v1/things", params={"cursor": cursor})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_cursor"


def test_limit_is_bounded() -> None:
    client = TestClient(_app(_db()))
    assert client.get("/api/v1/things", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/things", params={"limit": 101}).status_code == 422


def test_cursor_round_trips_and_rejects_shapes_it_never_makes() -> None:
    row = {"created_at": "2026-01-01T00:00:00+00:00", "id": 7}
    assert decode_cursor(encode_cursor(row, ORDER), ORDER) == ["2026-01-01T00:00:00+00:00", 7]
    for bad in ([None, 1], [{"x": 1}, 1]):
        import base64
        import json

        raw = base64.urlsafe_b64encode(json.dumps(bad).encode()).decode()
        with pytest.raises(HTTPException):
            decode_cursor(raw, ORDER)


def test_after_filter_quotes_values_and_expands_the_tuple_comparison() -> None:
    expr = after_filter(ORDER, ["2026-01-01T00:00:00+00:00", "a,b"])
    assert expr == (
        'created_at.gt."2026-01-01T00:00:00+00:00",'
        'and(created_at.eq."2026-01-01T00:00:00+00:00",id.gt."a,b")'
    )
    assert after_filter(["n"], [5], desc=True) == 'n.lt."5"'
    assert after_filter(["s"], ['say "hi"\\']) == 's.gt."say \\"hi\\"\\\\"'


def test_keyset_needs_an_order() -> None:
    with pytest.raises(ValueError, match="at least one order column"):
        keyset(FakeDB().table("x").select("*"), (), cursor=None, limit=1)


def test_descending_pages_newest_first() -> None:
    db = _db()
    q = db.table("things").select("*").eq("user_id", "u1")
    rows = keyset(q, ORDER, cursor=None, limit=2, desc=True).execute().data
    first = page(rows, ORDER, 2, Thing)
    assert [t.id for t in first.items] == ["t09", "t08"]
    q = db.table("things").select("*").eq("user_id", "u1")
    rows = keyset(q, ORDER, cursor=first.next_cursor, limit=2, desc=True).execute().data
    assert [t.id for t in page(rows, ORDER, 2, Thing).items] == ["t07", "t06"]


def test_a_page_model_pairs_with_its_wire_interface() -> None:
    ts = """
    export interface ThingWire { id: string; createdAt: string; }
    export interface ThingPageWire { items: ThingWire[]; nextCursor: string | null; }
    """
    pairs = {Thing: "ThingWire", Page[Thing]: "ThingPageWire"}
    assert compare(Page[Thing], ts_interface(ts, "ThingPageWire"), pairs) == []
    drifted = ts.replace("nextCursor: string | null", "cursor: string")
    assert compare(Page[Thing], ts_interface(drifted, "ThingPageWire"), pairs)
