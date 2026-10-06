"""Account deletion reaches Storage, PostHog and Sentry (backend/services/erasure_service.py).

Never real network: the vendors are httpx.MockTransport fakes that record each request,
and with the vendor unconfigured the transport fails the test on ANY request, which is
what "a no-op when unset" means. Storage is the FakeStorage on tests/test_prod_fakes.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from backend.services import erasure_service as es
from tests.test_prod_fakes import FakeDB, clear_prod_env, client_for

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)


def _posthog_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTHOG_ERASURE_KEY", "phx_test")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "4242")
    monkeypatch.setenv("POSTHOG_API_HOST", "https://eu.posthog.com/")


def _sentry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_ERASURE_TOKEN", "sntrys_test")
    monkeypatch.setenv("SENTRY_ORG", "acme")
    monkeypatch.setenv("SENTRY_PROJECTS", "penny-api, penny-app")


class Vendor:
    """A fake vendor API: records requests, answers with `respond(request)`."""

    def __init__(self, respond: Callable[[httpx.Request], httpx.Response]) -> None:
        self.respond = respond
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.respond(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def _no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"unconfigured erasure made a request: {request.method} {request.url}")


# ---- PostHog ------------------------------------------------------------------------


def test_posthog_unconfigured_is_a_no_op() -> None:
    assert es.delete_posthog_person("u1", transport=httpx.MockTransport(_no_network)) is False


def test_posthog_deletes_the_person_and_their_events(monkeypatch: pytest.MonkeyPatch) -> None:
    _posthog_env(monkeypatch)
    vendor = Vendor(lambda r: httpx.Response(202))
    assert es.delete_posthog_person("u1", transport=vendor.transport) is True
    (req,) = vendor.requests
    assert req.method == "POST"
    assert str(req.url) == "https://eu.posthog.com/api/projects/4242/persons/bulk_delete/"
    assert req.headers["Authorization"] == "Bearer phx_test"
    assert json.loads(req.content) == {"distinct_ids": ["u1"], "delete_events": True}


def test_posthog_person_already_gone_is_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _posthog_env(monkeypatch)
    assert es.delete_posthog_person("u1", transport=Vendor(lambda r: httpx.Response(404)).transport)


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_posthog_refusal_raises_without_the_body(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    _posthog_env(monkeypatch)
    vendor = Vendor(lambda r: httpx.Response(status, text="u1 is not allowed"))
    with pytest.raises(es.ErasureError, match=f"PostHog answered HTTP {status}") as exc:
        es.delete_posthog_person("u1", transport=vendor.transport)
    assert "u1" not in str(exc.value)


def test_posthog_unreachable_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _posthog_env(monkeypatch)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(es.ErasureError, match="PostHog unreachable"):
        es.delete_posthog_person("u1", transport=httpx.MockTransport(down))


def test_posthog_5xx_is_retried_because_the_delete_is_safe_to_repeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _posthog_env(monkeypatch)
    answers = iter([502, 202])
    vendor = Vendor(lambda r: httpx.Response(next(answers)))
    assert es.delete_posthog_person("u1", transport=vendor.transport) is True
    assert [r.method for r in vendor.requests] == ["POST", "POST"]


# ---- Sentry -------------------------------------------------------------------------


class SentryAPI:
    """Issues per project, each tagged with a user id. Search filters by `user.id:`,
    pages at `page` issues, and DELETE ?id=... removes them."""

    def __init__(self, issues: dict[str, list[tuple[str, str]]], page: int = 100) -> None:
        self.issues = issues  # project -> [(issue id, user id)]
        self.page = page
        self.vendor = Vendor(self.respond)

    def respond(self, request: httpx.Request) -> httpx.Response:
        m = re.fullmatch(r"/api/0/projects/acme/([\w-]+)/issues/", request.url.path)
        assert m, request.url.path
        project = m.group(1)
        if request.method == "GET":
            assert request.url.params["statsPeriod"] == ""  # all time, not the last 24 h
            user = request.url.params["query"].removeprefix("user.id:")
            hits = [{"id": i} for i, u in self.issues.get(project, []) if u == user]
            return httpx.Response(200, json=hits[: self.page])
        if request.method == "DELETE":
            ids = set(request.url.params.get_list("id"))
            self.issues[project] = [(i, u) for i, u in self.issues[project] if i not in ids]
            return httpx.Response(204)
        raise AssertionError(request.method)


def test_sentry_unconfigured_is_a_no_op() -> None:
    assert es.purge_sentry_user("u1", transport=httpx.MockTransport(_no_network)) is None


def test_sentry_deletes_only_the_users_issues_in_every_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _sentry_env(monkeypatch)
    api = SentryAPI({"penny-api": [("1", "u1"), ("2", "u2")], "penny-app": [("3", "u1")]})
    assert es.purge_sentry_user("u1", transport=api.vendor.transport) == 2
    assert api.issues == {"penny-api": [("2", "u2")], "penny-app": []}
    assert all(r.headers["Authorization"] == "Bearer sntrys_test" for r in api.vendor.requests)
    assert str(api.vendor.requests[0].url).startswith("https://sentry.io/api/0/")


def test_sentry_pages_until_nothing_is_left(monkeypatch: pytest.MonkeyPatch) -> None:
    _sentry_env(monkeypatch)
    monkeypatch.setenv("SENTRY_PROJECTS", "penny-api")
    api = SentryAPI({"penny-api": [(str(i), "u1") for i in range(7)]}, page=3)
    assert es.purge_sentry_user("u1", transport=api.vendor.transport) == 7
    assert api.issues["penny-api"] == []


def test_sentry_issues_still_listed_after_delete_are_not_deleted_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sentry deletes asynchronously: an accepted issue can show up in the next search."""
    _sentry_env(monkeypatch)
    monkeypatch.setenv("SENTRY_PROJECTS", "penny-api")
    pending = Vendor(
        lambda r: (
            httpx.Response(200, json=[{"id": "1"}]) if r.method == "GET" else httpx.Response(202)
        )
    )
    assert es.purge_sentry_user("u1", transport=pending.transport) == 1
    assert [r.method for r in pending.requests] == ["GET", "DELETE", "GET"]


def test_sentry_search_that_never_runs_dry_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    _sentry_env(monkeypatch)
    monkeypatch.setenv("SENTRY_PROJECTS", "penny-api")
    fresh = iter(range(10_000))
    endless = Vendor(
        lambda r: (
            httpx.Response(200, json=[{"id": str(next(fresh))}])
            if r.method == "GET"
            else httpx.Response(202)
        )
    )
    with pytest.raises(es.ErasureError, match="still lists issues"):
        es.purge_sentry_user("u1", transport=endless.transport)
    assert len(endless.requests) == 2 * es.SENTRY_MAX_PAGES


def test_sentry_delete_5xx_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    _sentry_env(monkeypatch)
    monkeypatch.setenv("SENTRY_PROJECTS", "penny-api")
    api = SentryAPI({"penny-api": [("1", "u1")]})
    failed: list[bool] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE" and not failed:
            failed.append(True)
            return httpx.Response(503)
        return api.respond(request)

    vendor = Vendor(flaky)
    assert es.purge_sentry_user("u1", transport=vendor.transport) == 1
    assert [r.method for r in vendor.requests] == ["GET", "DELETE", "DELETE", "GET"]
    assert api.issues["penny-api"] == []


def test_sentry_region_url_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    _sentry_env(monkeypatch)
    monkeypatch.setenv("SENTRY_API_URL", "https://de.sentry.io")
    api = SentryAPI({})
    es.purge_sentry_user("u1", transport=api.vendor.transport)
    assert str(api.vendor.requests[0].url).startswith("https://de.sentry.io/api/0/")


def test_sentry_refusal_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _sentry_env(monkeypatch)
    with pytest.raises(es.ErasureError, match="Sentry answered HTTP 403"):
        es.purge_sentry_user("u1", transport=Vendor(lambda r: httpx.Response(403)).transport)


# ---- Storage ------------------------------------------------------------------------


def _files(*paths: str) -> dict[str, dict[str, int]]:
    return {p: {"size": 1} for p in paths}


@pytest.fixture
def buckets(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeDB]:
    monkeypatch.setattr(es, "USER_FILE_BUCKETS", ("avatars", "uploads"))
    db = FakeDB()
    db.storage.objects = {
        "avatars": _files("u1/me.png", "u2/me.png", "u10/me.png"),
        "uploads": _files("u1/a.pdf", "u1/2026/b.pdf", "u1/2026/09/c.pdf", "u2/z.pdf"),
        "public-assets": _files("u1/not-ours-to-touch.png"),
    }
    yield db


def _paths(db: FakeDB) -> dict[str, set[str]]:
    return {bucket: set(objects) for bucket, objects in db.storage.objects.items()}


def test_storage_removes_every_file_of_the_user_and_nothing_else(buckets: FakeDB) -> None:
    assert es.purge_storage(buckets, "u1") == 4
    assert _paths(buckets) == {
        "avatars": {"u2/me.png", "u10/me.png"},
        "uploads": {"u2/z.pdf"},
        "public-assets": {"u1/not-ours-to-touch.png"},  # not a user bucket
    }


def test_storage_pages_through_large_folders(
    buckets: FakeDB, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(es, "STORAGE_PAGE", 2)
    buckets.storage.objects["uploads"].update(_files(*(f"u1/f{i}.txt" for i in range(5))))
    assert es.purge_storage(buckets, "u1") == 9
    assert _paths(buckets)["uploads"] == {"u2/z.pdf"}


def test_storage_no_buckets_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(es, "USER_FILE_BUCKETS", ())
    db = FakeDB()
    db.storage.error = AssertionError("listed a bucket while USER_FILE_BUCKETS is empty")
    assert es.purge_storage(db, "u1") == 0


@pytest.mark.parametrize("bad", ["", "u1/..", "../u2"])
def test_storage_refuses_anything_but_a_bare_user_id(buckets: FakeDB, bad: str) -> None:
    with pytest.raises(ValueError):
        es.purge_storage(buckets, bad)


# ---- through DELETE /api/v1/me --------------------------------------------------------


def _wire_vendors(monkeypatch: pytest.MonkeyPatch, transport: httpx.BaseTransport) -> None:
    """Route the service's real HTTP client to a fake transport."""
    real = es._client
    monkeypatch.setattr(
        es, "_client", lambda _t, name, base, token: real(transport, name, base, token)
    )


def _delete(db: FakeDB, user: str = "u1") -> httpx.Response:
    return client_for(db, user).request("DELETE", "/api/v1/me", json={"confirm": "DELETE"})


def test_delete_erases_storage_posthog_and_sentry(
    buckets: FakeDB, monkeypatch: pytest.MonkeyPatch
) -> None:
    _posthog_env(monkeypatch)
    _sentry_env(monkeypatch)
    sentry = SentryAPI({"penny-api": [("1", "u1"), ("2", "u2")], "penny-app": []})

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.host == "eu.posthog.com":
            return httpx.Response(202)
        return sentry.respond(request)

    vendor = Vendor(route)
    _wire_vendors(monkeypatch, vendor.transport)
    assert _delete(buckets).status_code == 204
    assert buckets.auth.admin.deleted == ["u1"]
    assert not any(p.startswith("u1/") for p in buckets.storage.objects["uploads"])
    assert any("persons/bulk_delete" in str(r.url) for r in vendor.requests)
    assert sentry.issues["penny-api"] == [("2", "u2")]
    assert [r["action"] for r in buckets.tables["audit_events"]] == ["account.delete"]


def test_delete_with_no_vendors_configured_touches_no_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_vendors(monkeypatch, httpx.MockTransport(_no_network))
    db = FakeDB()
    assert _delete(db).status_code == 204
    assert db.auth.admin.deleted == ["u1"]


def test_a_vendor_outage_does_not_block_deletion_and_is_audited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _posthog_env(monkeypatch)
    _sentry_env(monkeypatch)
    _wire_vendors(monkeypatch, Vendor(lambda r: httpx.Response(503)).transport)
    db = FakeDB()
    assert _delete(db).status_code == 204
    assert db.auth.admin.deleted == ["u1"]
    rows = [(r["action"], r["target"]) for r in db.tables["audit_events"]]
    assert rows == [
        ("account.delete", None),
        ("account.erasure_failed", "posthog"),
        ("account.erasure_failed", "sentry"),
    ]


def test_a_storage_failure_stops_before_the_auth_user_goes(buckets: FakeDB) -> None:
    buckets.storage.error = RuntimeError("storage down")
    resp = _delete(buckets)
    assert resp.status_code == 500 and resp.json()["error_id"]
    assert buckets.auth.admin.deleted == []


def test_a_retry_after_a_partial_failure_finishes_the_job(buckets: FakeDB) -> None:
    buckets.auth.admin.error = RuntimeError("auth down")
    assert _delete(buckets).status_code == 500
    buckets.auth.admin.error = None
    assert _delete(buckets).status_code == 204
    assert buckets.auth.admin.deleted == ["u1"]


# ---- every bucket a migration creates is accounted for -------------------------------

_BUCKET = re.compile(
    r"insert\s+into\s+storage\.buckets\s*(?:\([^)]*\))?\s*values\s*(.*?);", re.I | re.S
)
_FIRST_LITERAL = re.compile(r"\(\s*'([^']+)'")


def buckets_created(sql: str) -> set[str]:
    """Bucket ids a migration inserts into storage.buckets (the id is the first value)."""
    sql = re.sub(r"--[^\n]*", "", sql)
    return {b for values in _BUCKET.findall(sql) for b in _FIRST_LITERAL.findall(values)}


def _all_sql() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(MIGRATIONS.glob("*.sql")))


def test_every_bucket_is_purged_on_deletion_or_explained() -> None:
    covered = set(es.USER_FILE_BUCKETS) | set(es.NOT_USER_FILE_BUCKETS)
    missing = sorted(buckets_created(_all_sql()) - covered)
    assert not missing, (
        f"storage buckets that account deletion doesn't empty: {missing}. Add each to "
        "USER_FILE_BUCKETS in backend/services/erasure_service.py (files under "
        "`<user id>/`), or to NOT_USER_FILE_BUCKETS with the reason it holds no user files."
    )


def test_not_user_file_buckets_are_justified() -> None:
    assert all(len(reason) > 40 for reason in es.NOT_USER_FILE_BUCKETS.values())


@pytest.mark.parametrize(
    "planted",
    [
        "insert into storage.buckets (id, name, public) values ('avatars', 'avatars', false);",
        "insert into storage.buckets (id, name)\n  values ('docs', 'docs')\n  on conflict do nothing;",
        "INSERT INTO storage.buckets VALUES ('scans', 'scans');",
    ],
    ids=["columns", "multiline-on-conflict", "upper-no-columns"],
)
def test_the_bucket_scan_sees_a_planted_bucket(planted: str) -> None:
    found = buckets_created(planted)
    assert len(found) == 1


def test_the_bucket_scan_ignores_commented_sql() -> None:
    assert buckets_created("-- insert into storage.buckets (id) values ('x');") == set()
