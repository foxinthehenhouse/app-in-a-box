"""DELETE /api/v1/me: App Store guideline 5.1.1(v) account deletion."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.test_prod_fakes import FakeDB, clear_prod_env, client_for


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)


def _delete(client: TestClient, body: object | None) -> httpx.Response:
    return client.request("DELETE", "/api/v1/me", json=body)


def test_requires_auth() -> None:
    resp = TestClient(create_app()).request("DELETE", "/api/v1/me", json={"confirm": "DELETE"})
    assert resp.status_code == 401


def test_deletes_the_caller_only() -> None:
    db = FakeDB()
    resp = _delete(client_for(db, "b"), {"confirm": "DELETE"})
    assert resp.status_code == 204
    assert db.auth.admin.deleted == ["b"]


def test_cannot_delete_someone_else_by_naming_them() -> None:
    db = FakeDB()
    for body in ({"confirm": "DELETE", "userId": "a"}, {"confirm": "DELETE", "id": "a"}):
        resp = _delete(client_for(db, "b"), body)
        assert resp.status_code == 422
    assert db.auth.admin.deleted == []


@pytest.mark.parametrize("body", [None, {}, {"confirm": "yes"}, {"confirm": "delete"}])
def test_requires_explicit_confirmation(body: object) -> None:
    db = FakeDB()
    assert _delete(client_for(db, "b"), body).status_code == 422
    assert db.auth.admin.deleted == []


def test_already_deleted_user_is_idempotent() -> None:
    db = FakeDB()
    err = Exception("User not found")
    err.status = 404  # type: ignore[attr-defined]
    db.auth.admin.error = err
    assert _delete(client_for(db, "b"), {"confirm": "DELETE"}).status_code == 204


def test_admin_api_failure_is_a_500_with_error_id() -> None:
    db = FakeDB()
    db.auth.admin.error = RuntimeError("auth down")
    resp = _delete(client_for(db, "b"), {"confirm": "DELETE"})
    assert resp.status_code == 500
    assert resp.json()["error_id"]


def test_deletion_is_rate_limited() -> None:
    db = FakeDB()
    db.auth.admin.error = RuntimeError("keep failing so we can retry")
    client = client_for(db, "b")
    codes = [_delete(client, {"confirm": "DELETE"}).status_code for _ in range(4)]
    assert codes == [500, 500, 500, 429]
