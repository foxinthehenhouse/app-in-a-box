from typing import Any

from fastapi.testclient import TestClient

from backend.auth import CurrentUser, get_current_user
from backend.db import get_db
from backend.main import create_app


class FakeQuery:
    """Filter-honouring fake: a handler that forgets .eq("id", ...) sees everyone's rows."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self._filtered = list(rows)
        self._upsert: dict[str, Any] | None = None

    def select(self, *_: Any) -> "FakeQuery":
        return self

    def eq(self, col: str, val: Any) -> "FakeQuery":
        self._filtered = [r for r in self._filtered if r.get(col) == val]
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._filtered = self._filtered[:n]
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str) -> "FakeQuery":
        self._upsert = row
        return self

    def execute(self) -> Any:
        if self._upsert is not None:
            row = self._upsert
            existing = next((r for r in self.rows if r["id"] == row["id"]), None)
            if existing:
                existing.update(row)
            else:
                self.rows.append(dict(row))
            data = [next(r for r in self.rows if r["id"] == row["id"])]
        else:
            data = self._filtered
        return type("Result", (), {"data": data})()


class FakeDB:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def table(self, _name: str) -> FakeQuery:
        return FakeQuery(self.rows)


def _client(user_id: str, rows: list[dict[str, Any]]) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user_id)
    app.dependency_overrides[get_db] = lambda: FakeDB(rows)
    return TestClient(app)


def test_me_requires_auth() -> None:
    assert TestClient(create_app()).get("/api/v1/me").status_code == 401


def test_me_returns_only_the_callers_row() -> None:
    rows = [
        {"id": "a", "display_name": "Ann", "onboarded": True},
        {"id": "b", "display_name": "Bob", "onboarded": False},
    ]
    body = _client("b", rows).get("/api/v1/me").json()
    assert body == {"id": "b", "displayName": "Bob", "onboarded": False}


def test_patch_writes_the_callers_row_only() -> None:
    rows = [{"id": "a", "display_name": "Ann", "onboarded": True}]
    resp = _client("b", rows).patch("/api/v1/me", json={"displayName": "Bea"})
    assert resp.status_code == 200
    assert resp.json() == {"id": "b", "displayName": "Bea", "onboarded": False}
    assert rows[0]["display_name"] == "Ann"


def test_patch_cannot_write_someone_elses_row() -> None:
    """A body-supplied id is REJECTED (422), not silently dropped: a client that sends
    one is either an attacker or a drifted build, and both should hear about it."""
    rows = [{"id": "a", "display_name": "Ann", "onboarded": True}]
    resp = _client("b", rows).patch("/api/v1/me", json={"id": "a", "displayName": "pwned"})
    assert resp.status_code == 422
    assert rows == [{"id": "a", "display_name": "Ann", "onboarded": True}]
