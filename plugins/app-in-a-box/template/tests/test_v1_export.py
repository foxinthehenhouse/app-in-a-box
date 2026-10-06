"""GET /api/v1/me/export: "Download my data" (GDPR Art. 15/20).

Uses the filter-honouring fake (tests/test_prod_fakes.py), so a reader that forgets its
user filter returns the other user's rows and these tests fail. The selftest plants
exactly that (drops a `.eq(...)` from backend/routers/export.py) and expects a failure.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import export as export_router
from scripts.schema_sql import all_sql, user_owned_tables
from tests.test_prod_fakes import FakeDB, clear_prod_env, client_for

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)


def _two_users() -> FakeDB:
    """User `a` owns rows marked SECRET-A in every exported table; `b` owns B rows."""
    return FakeDB(
        {
            "profiles": [
                {"id": "a", "display_name": "SECRET-A", "onboarded": True},
                {"id": "b", "display_name": "Bea", "onboarded": False},
            ],
            "push_tokens": [
                {
                    "id": 1,
                    "user_id": "a",
                    "token": "ExponentPushToken[SECRET-A]",
                    "platform": "ios",
                },
                {
                    "id": 2,
                    "user_id": "b",
                    "token": "ExponentPushToken[bbbb]",
                    "platform": "android",
                },
            ],
            "push_tickets": [
                {"ticket_id": "t-SECRET-A", "user_id": "a", "token": "x", "created_at": "1"},
                {"ticket_id": "t-b", "user_id": "b", "token": "y", "created_at": "2"},
            ],
        }
    )


def test_requires_auth() -> None:
    assert TestClient(create_app()).get("/api/v1/me/export").status_code == 401


def test_exports_the_callers_rows_in_every_table() -> None:
    resp = client_for(_two_users(), "b").get("/api/v1/me/export")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"formatVersion", "exportedAt", "userId", "tables"}
    assert body["userId"] == "b"
    assert body["formatVersion"] == export_router.FORMAT_VERSION
    tables = body["tables"]
    assert set(tables) == set(export_router.EXPORTERS)
    assert [r["display_name"] for r in tables["profiles"]] == ["Bea"]
    assert [r["token"] for r in tables["push_tokens"]] == ["ExponentPushToken[bbbb]"]
    assert [r["ticket_id"] for r in tables["push_tickets"]] == ["t-b"]


def test_another_users_data_is_never_included() -> None:
    body = client_for(_two_users(), "b").get("/api/v1/me/export").json()
    dumped = json.dumps(body)
    assert "SECRET-A" not in dumped
    # and the reverse: a's export holds none of b's rows
    other = json.dumps(client_for(_two_users(), "a").get("/api/v1/me/export").json())
    assert "bbbb" not in other and "Bea" not in other and "t-b" not in other


def test_every_read_is_filtered_by_the_caller() -> None:
    db = _two_users()
    client_for(db, "b").get("/api/v1/me/export")
    reads = [(t, f) for t, op, f in db.calls if op == "select" and t in export_router.EXPORTERS]
    assert {t for t, _ in reads} == set(export_router.EXPORTERS)
    for table, filters in reads:
        assert ("eq", "user_id", "b") in filters or ("eq", "id", "b") in filters, (table, filters)


def test_ignores_a_user_id_in_the_query_string() -> None:
    body = client_for(_two_users(), "b").get("/api/v1/me/export?userId=a&user_id=a").json()
    assert body["userId"] == "b"
    assert "SECRET-A" not in json.dumps(body)


def test_empty_account_exports_empty_tables() -> None:
    body = client_for(FakeDB(), "new").get("/api/v1/me/export").json()
    assert body["tables"] == {name: [] for name in export_router.EXPORTERS}


def test_pages_through_large_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_router, "PAGE_SIZE", 3)
    rows = [{"id": i, "user_id": "b", "token": f"ExponentPushToken[{i:04d}]"} for i in range(8)]
    body = client_for(FakeDB({"push_tokens": rows}), "b").get("/api/v1/me/export").json()
    assert len(body["tables"]["push_tokens"]) == 8


class ShuffledHeap(FakeDB):
    """Rows come off the heap in no particular order among ties, as in Postgres: an
    `order by created_at` over rows inserted in one batch (same timestamp) is a
    different permutation on every page, so `.range()` pages overlap and skip."""

    def __init__(self, tables: dict[str, list[dict[str, Any]]], seed: int) -> None:
        super().__init__(tables)
        self._rng = random.Random(seed)

    def table(self, name: str) -> Any:
        self._rng.shuffle(self.tables.setdefault(name, []))
        return super().table(name)


@pytest.mark.parametrize("seed", range(6))
def test_paging_is_stable_when_rows_share_a_timestamp(
    monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    """Every paged reader must order by a unique key (the primary key) as a tiebreaker,
    or a batch of same-second rows is exported with duplicates and holes."""
    monkeypatch.setattr(export_router, "PAGE_SIZE", 3)
    same_second = "2026-09-30T12:00:00+00:00"
    tickets = [
        {"ticket_id": f"t{i}", "user_id": "b", "token": "x", "created_at": same_second}
        for i in range(7)
    ]
    tokens = [
        {"id": i, "user_id": "b", "token": f"ExponentPushToken[{i:04d}]", "created_at": same_second}
        for i in range(7)
    ]
    db = ShuffledHeap({"push_tickets": tickets, "push_tokens": tokens}, seed)
    body = client_for(db, "b").get("/api/v1/me/export").json()
    assert sorted(r["ticket_id"] for r in body["tables"]["push_tickets"]) == [f"t{i}" for i in range(7)]
    assert sorted(r["token"] for r in body["tables"]["push_tokens"]) == sorted(t["token"] for t in tokens)


def test_export_is_rate_limited() -> None:
    client = client_for(FakeDB(), "b")
    codes = [client.get("/api/v1/me/export").status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


# ---- every user-owned table is exported ---------------------------------------------

# The one migration parser (scripts/schema_sql.py), shared with the privacy data map
# guard (scripts/check_data_map.py), so the two can't disagree about what a table is.


def _all_sql() -> str:
    return all_sql(MIGRATIONS)


def test_every_user_owned_table_is_exported() -> None:
    owned = user_owned_tables(_all_sql())
    assert owned, "found no user-owned tables: the migration parser is broken"
    covered = set(export_router.EXPORTERS) | set(export_router.NOT_EXPORTED)
    missing = sorted(owned - covered)
    assert not missing, (
        f"user-owned tables missing from the data export: {missing}. Add a scoped reader to "
        "EXPORTERS in backend/routers/export.py (or NOT_EXPORTED with a reason)."
    )


def test_not_exported_entries_are_justified() -> None:
    assert all(len(reason) > 40 for reason in export_router.NOT_EXPORTED.values())


def test_a_new_user_table_is_caught() -> None:
    planted = _all_sql() + (
        "\ncreate table if not exists public.notes (\n"
        "  id bigint primary key,\n"
        "  user_id uuid not null references auth.users (id) on delete cascade\n);\n"
    )
    assert "notes" in user_owned_tables(planted) - set(export_router.EXPORTERS)


def test_readers_are_scoped_statically() -> None:
    """Belt and braces with tests/test_scoping_static.py: no reader is allowlisted there."""
    from tests.test_scoping_static import ALLOWLIST, find_unscoped

    src = (ROOT / "backend" / "routers" / "export.py").read_text(encoding="utf-8")
    assert find_unscoped(src, "backend/routers/export.py") == []
    assert not [k for k in ALLOWLIST if k.startswith("backend/routers/export.py")]

