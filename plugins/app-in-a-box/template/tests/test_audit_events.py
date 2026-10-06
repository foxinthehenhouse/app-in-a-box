"""The audit trail: sensitive endpoints write their row, and fail closed without it.

The table itself (append-only, service role only) is proven against a real Postgres by
supabase/tests/database/audit_events.test.sql. These tests prove the API side with the
filter-honouring fake: account deletion and the data export each append exactly one
row, carrying the verified caller and the request id, and neither goes ahead when the
row can't be written.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.services import audit_service
from tests.test_prod_fakes import FakeAPIError, FakeDB, FakeQuery, clear_prod_env, client_for


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)


def _rows(db: FakeDB) -> list[dict[str, Any]]:
    return db.tables.get("audit_events", [])


class AuditDown(FakeDB):
    """Every write to audit_events fails, the way a broken table or grant would."""

    def table(self, name: str) -> FakeQuery:
        query = super().table(name)
        if name == "audit_events":
            original = query.execute

            def execute() -> Any:
                if query.op == "insert":
                    raise FakeAPIError("42501", "permission denied for table audit_events")
                return original()

            query.execute = execute  # type: ignore[method-assign]
        return query


# ---- account deletion ---------------------------------------------------------------


def test_account_delete_is_audited_with_the_caller_and_request_id() -> None:
    db = FakeDB()
    resp = client_for(db, "b").request(
        "DELETE", "/api/v1/me", json={"confirm": "DELETE"}, headers={"X-Request-ID": "req-12345678"}
    )
    assert resp.status_code == 204
    assert _rows(db) == [
        {"actor_id": "b", "action": "account.delete", "target": None, "request_id": "req-12345678"}
    ]


def test_account_delete_does_not_happen_without_its_audit_row() -> None:
    db = AuditDown()
    resp = client_for(db, "b").request("DELETE", "/api/v1/me", json={"confirm": "DELETE"})
    assert resp.status_code == 500
    assert db.auth.admin.deleted == []


def test_account_delete_audit_row_survives_a_failed_auth_delete() -> None:
    """Written BEFORE the irreversible step: a failed attempt is on the record too."""
    db = FakeDB()
    db.auth.admin.error = RuntimeError("auth down")
    client_for(db, "b").request("DELETE", "/api/v1/me", json={"confirm": "DELETE"})
    assert [r["action"] for r in _rows(db)] == ["account.delete"]


# ---- data export --------------------------------------------------------------------


def test_export_is_audited() -> None:
    db = FakeDB()
    resp = client_for(db, "b").get("/api/v1/me/export", headers={"X-Request-ID": "req-export-1"})
    assert resp.status_code == 200
    assert _rows(db) == [
        {"actor_id": "b", "action": "data.export", "target": None, "request_id": "req-export-1"}
    ]


def test_export_lists_the_callers_earlier_exports() -> None:
    db = FakeDB()
    client = client_for(db, "b")
    client.get("/api/v1/me/export")
    second = client.get("/api/v1/me/export").json()["tables"]["audit_events"]
    assert [r["action"] for r in second] == ["data.export"]


def test_no_export_leaves_without_its_audit_row() -> None:
    db = AuditDown({"profiles": [{"id": "b", "display_name": "SECRET-B"}]})
    resp = client_for(db, "b").get("/api/v1/me/export")
    assert resp.status_code == 500
    assert "SECRET-B" not in resp.text


# ---- the service --------------------------------------------------------------------


def test_unknown_action_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown audit action"):
        audit_service.record(FakeDB(), "b", "account.delte")


def test_role_change_is_a_known_action() -> None:
    """No endpoint changes roles yet; the action is ready for the first one that does."""
    db = FakeDB()
    audit_service.record(db, "admin", "role.change", target="member")
    assert _rows(db)[0]["target"] == "member"


def test_outside_a_request_the_request_id_is_null() -> None:
    db = FakeDB()
    audit_service.record(db, None, "account.erasure_failed", target="sentry")
    assert _rows(db) == [
        {
            "actor_id": None,
            "action": "account.erasure_failed",
            "target": "sentry",
            "request_id": None,
        }
    ]


def test_actions_fit_the_tables_check_constraint() -> None:
    """The migration's `noun.verb` check, in Python: a new action that breaks it would
    only fail in production, as a 500 on the endpoint that records it."""
    import re

    for action in audit_service.ACTIONS:
        assert re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", action), action
