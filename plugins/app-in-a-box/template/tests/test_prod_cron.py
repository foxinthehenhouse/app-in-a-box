"""/internal/cron/*: fail-closed shared secret, idempotent jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.services import jobs_service
from backend.services import push_service as ps
from tests.test_prod_fakes import FakeDB, clear_prod_env, client_for, wire_db_env

SECRET = "s" * 40
JOBS = (
    "/internal/cron/weekly-digest",
    "/internal/cron/push-receipts",
    "/internal/cron/prune-rate-limits",
)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)
    wire_db_env(monkeypatch)


def _cron(db: FakeDB | None = None) -> TestClient:
    return client_for(db or FakeDB(), user_id=None)


@pytest.mark.parametrize("path", JOBS)
def test_unset_secret_fails_closed_with_503(path: str) -> None:
    resp = _cron().post(path, headers={"X-Cron-Secret": "anything"})
    assert resp.status_code == 503
    assert "scheduled jobs (cron)" in resp.json()["detail"]


def test_short_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRON_SECRET", "short")
    resp = _cron().post(JOBS[0], headers={"X-Cron-Secret": "short"})
    assert resp.status_code == 503


@pytest.mark.parametrize("path", JOBS)
@pytest.mark.parametrize("header", [None, "", "wrong", SECRET[:-1], SECRET + "x"])
def test_wrong_or_missing_secret_is_401(
    monkeypatch: pytest.MonkeyPatch, path: str, header: str | None
) -> None:
    monkeypatch.setenv("CRON_SECRET", SECRET)
    headers = {} if header is None else {"X-Cron-Secret": header}
    assert _cron().post(path, headers=headers).status_code == 401


def test_secret_is_checked_before_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRON_SECRET", SECRET)
    monkeypatch.delenv("SUPABASE_URL")
    client = TestClient(create_app())  # no DB override: get_db would 503
    assert client.post(JOBS[0], headers={"X-Cron-Secret": "wrong"}).status_code == 401


def test_cron_routes_are_not_in_the_public_schema() -> None:
    paths = TestClient(create_app()).get("/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/internal")]


def test_cron_secret_uses_constant_time_compare() -> None:
    import inspect

    from backend.routers import internal

    src = inspect.getsource(internal.require_cron_secret)
    assert "hmac.compare_digest" in src
    assert "==" not in src


_RealClient = ps.ExpoPushClient


def _expo_ok() -> ps.ExpoPushClient:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        msgs = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"status": "ok", "id": m["to"]} for m in msgs]})

    return _RealClient(transport=httpx.MockTransport(handler))


def test_weekly_digest_endpoint_runs_once_per_week(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRON_SECRET", SECRET)
    monkeypatch.setattr(ps, "ExpoPushClient", lambda: _expo_ok())
    db = FakeDB(
        {
            "profiles": [{"id": "u1", "onboarded": True}, {"id": "u2", "onboarded": False}],
            "push_tokens": [
                {"user_id": "u1", "token": "ExponentPushToken[u1aaaaaaaaaaaa]"},
                {"user_id": "u2", "token": "ExponentPushToken[u2aaaaaaaaaaaa]"},
            ],
        }
    )
    client = _cron(db)
    first = client.post(JOBS[0], headers={"X-Cron-Secret": SECRET})
    assert first.status_code == 200
    body = first.json()
    assert body["skipped"] is False
    assert body["users"] == 1
    assert body["sent"] == 1
    second = client.post(JOBS[0], headers={"X-Cron-Secret": SECRET}).json()
    assert second["skipped"] is True  # a retried/overlapping cron call sends nothing twice
    assert len(db.tables["push_tickets"]) == 1
    assert db.tables["job_runs"][0]["stats"] == {"users": 1, "sent": 1, "failed": 0}


def test_weekly_digest_pages_through_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs_service, "PAGE_SIZE", 2)
    db = FakeDB({"profiles": [{"id": f"u{i}", "onboarded": True} for i in range(5)]})
    out = jobs_service.weekly_digest(db, now=datetime(2026, 9, 30, tzinfo=UTC), client=_expo_ok())
    assert out["users"] == 5
    assert out["run_key"] == "2026-W40"


def test_a_crash_mid_run_releases_the_claim_so_the_retry_runs() -> None:
    """One DB error mustn't turn the whole week into a silent `skipped` (review #5)."""
    when = datetime(2026, 9, 30, tzinfo=UTC)
    calls = {"n": 0}

    class FlakyProfiles(FakeDB):
        def table(self, name: str):  # type: ignore[override]
            if name == "profiles":
                calls["n"] += 1
                if calls["n"] == 1:
                    raise ConnectionError("db blip")
            return super().table(name)

    db = FlakyProfiles({"profiles": [{"id": "u1", "onboarded": True}]})
    with pytest.raises(ConnectionError):
        jobs_service.weekly_digest(db, now=when, client=_expo_ok())
    assert db.tables.get("job_runs", []) == [], "the crashed run must give its claim back"
    retry = jobs_service.weekly_digest(db, now=when, client=_expo_ok())
    assert retry["skipped"] is False
    assert retry["users"] == 1
    again = jobs_service.weekly_digest(db, now=when, client=_expo_ok())
    assert again["skipped"] is True, "a finished run still holds the week"


def test_one_users_unexpected_error_is_counted_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise ValueError("bad json from a proxy")

    monkeypatch.setattr(ps, "send_to_user", boom)
    db = FakeDB({"profiles": [{"id": "u1", "onboarded": True}, {"id": "u2", "onboarded": True}]})
    out = jobs_service.weekly_digest(db, now=datetime(2026, 9, 30, tzinfo=UTC), client=_expo_ok())
    assert out["failed"] == 2
    assert out["skipped"] is False


NOW = datetime(2026, 9, 30, 12, tzinfo=UTC)


def _claim(started_hours_ago: float, finished: bool) -> dict[str, object]:
    return {
        "job": "j",
        "run_key": "k",
        "started_at": (NOW - timedelta(hours=started_hours_ago)).isoformat(),
        "finished_at": NOW.isoformat() if finished else None,
    }


def test_a_stale_unfinished_claim_is_reclaimed() -> None:
    """release_run() only runs for a Python exception. A worker killed mid-run (deploy,
    OOM, SIGKILL) leaves its claim behind, and without this the period would report
    `skipped` forever. After STALE_RUN_HOURS an unfinished claim is taken over."""
    db = FakeDB({"job_runs": [_claim(jobs_service.STALE_RUN_HOURS + 1, finished=False)]})
    assert jobs_service.claim_run(db, "j", "k", now=NOW) is True
    assert db.tables["job_runs"] == [{"job": "j", "run_key": "k"}], "a fresh claim replaces it"


def test_a_recent_unfinished_claim_is_still_running_not_stale() -> None:
    db = FakeDB({"job_runs": [_claim(0.2, finished=False)]})
    assert jobs_service.claim_run(db, "j", "k", now=NOW) is False
    assert db.tables["job_runs"] == [_claim(0.2, finished=False)]


def test_a_finished_run_is_never_reclaimed_however_old() -> None:
    db = FakeDB({"job_runs": [_claim(400, finished=True)]})
    assert jobs_service.claim_run(db, "j", "k", now=NOW) is False
    assert db.tables["job_runs"] == [_claim(400, finished=True)]


def test_weekly_digest_reruns_after_a_killed_worker() -> None:
    stale = {**_claim(jobs_service.STALE_RUN_HOURS + 1, finished=False), "job": "weekly_digest",
             "run_key": jobs_service.iso_week(NOW)}
    db = FakeDB({"job_runs": [stale], "profiles": [{"id": "u1", "onboarded": True}]})
    out = jobs_service.weekly_digest(db, now=NOW, client=_expo_ok())
    assert out["skipped"] is False
    assert out["users"] == 1


def test_claim_run_propagates_unexpected_errors() -> None:
    class Broken(FakeDB):
        def table(self, name: str):  # type: ignore[override]
            raise ConnectionError("db down")

    with pytest.raises(ConnectionError):
        jobs_service.claim_run(Broken(), "j", "k")


def test_prune_rate_limits_deletes_only_old_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRON_SECRET", SECRET)
    db = FakeDB(
        {
            "rate_limits": [
                {"key": "a", "window_start": "2020-01-01T00:00:00+00:00", "count": 1},
                {"key": "b", "window_start": "2999-01-01T00:00:00+00:00", "count": 1},
            ]
        }
    )
    assert _cron(db).post(JOBS[2], headers={"X-Cron-Secret": SECRET}).status_code == 200
    assert [r["key"] for r in db.tables["rate_limits"]] == ["b"]
