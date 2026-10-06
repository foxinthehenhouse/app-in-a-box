"""Hardening: slashes, request ids, headers, CORS, logging, /health, rate limits,
pinned deps, and the no-in-process-state guard."""

from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import ratelimit
from backend.main import create_app
from backend.observability import JsonFormatter, _RequestIdFilter, request_id_var
from tests.test_prod_fakes import FakeDB, clear_prod_env, client_for, wire_db_env

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_prod_env(monkeypatch)


# --- trailing slashes -------------------------------------------------------------


def test_trailing_slash_is_not_redirected() -> None:
    # A 307 here makes React Native drop the Authorization header -> 401 -> sign-out.
    resp = TestClient(create_app()).get("/api/v1/me/", follow_redirects=False)
    assert resp.status_code == 404
    assert "location" not in resp.headers


# --- request ids ------------------------------------------------------------------


def test_request_id_is_generated_and_echoed() -> None:
    resp = TestClient(create_app()).get("/health")
    assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["x-request-id"])


def test_sane_caller_request_id_is_kept() -> None:
    resp = TestClient(create_app()).get("/health", headers={"X-Request-ID": "client-abc-123"})
    assert resp.headers["x-request-id"] == "client-abc-123"


def test_hostile_caller_request_id_is_replaced() -> None:
    evil = "x\nFAKE LOG LINE " + "a" * 200
    resp = TestClient(create_app()).get("/health", headers={"X-Request-ID": evil[:150]})
    assert resp.headers["x-request-id"] != evil[:150]
    assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["x-request-id"])


def test_500_carries_request_id_in_body_and_header() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    resp = client.get("/debug/sentry", headers={"X-Request-ID": "trace-me-0001"})
    assert resp.status_code == 500
    assert resp.json()["request_id"] == "trace-me-0001"
    assert resp.headers["x-request-id"] == "trace-me-0001"
    assert len(resp.json()["error_id"]) == 36


def test_log_records_carry_request_id_and_json_is_parseable() -> None:
    token = request_id_var.set("rid-12345678")
    try:
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        _RequestIdFilter().filter(record)
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["msg"] == "hello world"
    assert line["request_id"] == "rid-12345678"
    assert line["level"] == "INFO"


def test_log_format_json_switches_the_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FORMAT", "json")
    create_app()
    create_app()  # idempotent: still one handler
    ours = [h for h in logging.getLogger().handlers if getattr(h, "_appbox", False)]
    assert len(ours) == 1
    assert isinstance(ours[0].formatter, JsonFormatter)
    monkeypatch.delenv("LOG_FORMAT")
    create_app()
    assert not isinstance(ours[0].formatter, JsonFormatter)


def test_sentry_scrubber_keeps_request_id_tag_only() -> None:
    from backend.observability import scrub_event

    event = {"tags": {"request_id": "r1", "error_id": "e1", "email": "a@b.c"}, "user": {"id": 1}}
    out = scrub_event(event, {})
    assert out["tags"] == {"error_id": "e1", "request_id": "r1"}
    assert "user" not in out


# --- security headers -------------------------------------------------------------


def test_security_headers_on_every_response() -> None:
    client = TestClient(create_app())
    for path in ("/health", "/api/v1/me"):  # the second is a 401: errors get them too
        h = client.get(path).headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer"
        assert h["content-security-policy"].startswith("default-src 'none'")
        assert "strict-transport-security" not in h  # dev: no HSTS
    assert client.get("/api/v1/me").headers["cache-control"] == "no-store"


def test_production_adds_hsts_and_hides_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    client = TestClient(create_app())
    assert client.get("/health").headers["strict-transport-security"].startswith("max-age=")
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/debug/sentry").status_code == 404


# --- CORS -------------------------------------------------------------------------


def _preflight(client: TestClient, origin: str) -> dict[str, str]:
    return dict(
        client.options(
            "/api/v1/me",
            headers={"Origin": origin, "Access-Control-Request-Method": "PATCH"},
        ).headers
    )


def test_cors_rejects_unknown_origins() -> None:
    h = _preflight(TestClient(create_app()), "https://evil.example")
    assert "access-control-allow-origin" not in h


def test_cors_allows_configured_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, https://admin.example.com/")
    client = TestClient(create_app())
    assert _preflight(client, "https://admin.example.com")["access-control-allow-origin"] == (
        "https://admin.example.com"
    )
    assert "access-control-allow-origin" not in _preflight(client, "https://evil.example")


def test_cors_production_default_is_mobile_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    h = _preflight(TestClient(create_app()), "http://localhost:8081")
    assert "access-control-allow-origin" not in h


# --- /health ----------------------------------------------------------------------


def test_health_reports_version_when_deployed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123def")
    assert TestClient(create_app()).get("/health").json()["version"] == "abc123def"


def test_health_deep_pings_db_and_lists_optional_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire_db_env(monkeypatch)
    monkeypatch.setenv("SENTRY_DSN", "x")
    import backend.db

    monkeypatch.setattr(backend.db, "_client", lambda: FakeDB({"keep_alive": [{"id": 1}]}))
    shallow = TestClient(create_app()).get("/health").json()
    assert "db" not in shallow and shallow["status"] == "ok"
    deep = TestClient(create_app()).get("/health?deep=1").json()
    assert deep["db"] == "ok"
    assert deep["status"] == "ok"
    assert deep["features_optional_unconfigured"] == {
        "scheduled jobs (cron)": ["CRON_SECRET"],
        "feature flags (PostHog)": ["POSTHOG_API_KEY"],
    }


def test_health_deep_degrades_when_db_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    wire_db_env(monkeypatch)
    monkeypatch.setenv("SENTRY_DSN", "x")
    import backend.db

    def broken() -> FakeDB:
        raise ConnectionError("db down")

    monkeypatch.setattr(backend.db, "_client", broken)
    deep = TestClient(create_app()).get("/health?deep=1").json()
    assert deep == {**deep, "db": "error", "status": "degraded"}


def test_health_deep_without_db_config_says_unconfigured() -> None:
    assert TestClient(create_app()).get("/health?deep=1").json()["db"] == "unconfigured"


# --- rate limiting ----------------------------------------------------------------


def test_rate_limit_allows_up_to_the_limit() -> None:
    db = FakeDB({"profiles": []})
    client = client_for(db, "u1")
    codes = [client.patch("/api/v1/me", json={"displayName": "A"}).status_code for _ in range(30)]
    assert codes == [200] * 30


def test_rate_limit_blocks_past_the_limit_with_retry_after() -> None:
    db = FakeDB({"profiles": []})
    client = client_for(db, "u1")
    for _ in range(30):
        client.patch("/api/v1/me", json={"displayName": "A"})
    resp = client.patch("/api/v1/me", json={"displayName": "A"})
    assert resp.status_code == 429
    assert 1 <= int(resp.headers["retry-after"]) <= 60


def test_rate_limit_is_per_user() -> None:
    db = FakeDB({"profiles": []})
    for _ in range(31):
        client_for(db, "u1").patch("/api/v1/me", json={"displayName": "A"})
    assert client_for(db, "u2").patch("/api/v1/me", json={"displayName": "B"}).status_code == 200
    assert db.rpc_calls[-1][1]["p_key"] == "me.update:u2"


def test_rate_limit_holds_across_workers() -> None:
    # Two app instances = two uvicorn workers. The count lives in the (shared) DB, so
    # the limit holds across them. An in-process counter would allow 2x.
    db = FakeDB({"profiles": []})
    workers = [client_for(db, "u1"), client_for(db, "u1")]
    codes = [workers[i % 2].patch("/api/v1/me", json={}).status_code for i in range(31)]
    assert codes[-1] == 429


def test_rate_limiter_fails_open_when_counter_errors() -> None:
    db = FakeDB({"profiles": []})
    db.rpc_error = ConnectionError("db blip")
    assert client_for(db).patch("/api/v1/me", json={}).status_code == 200


def test_rate_limiter_can_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ratelimit, "FAIL_OPEN", False)
    db = FakeDB({"profiles": []})
    db.rpc_error = ConnectionError("db blip")
    assert client_for(db).patch("/api/v1/me", json={}).status_code == 503


def test_429_carries_ratelimit_and_policy_headers() -> None:
    db = FakeDB({"profiles": []})
    client = client_for(db, "u1")
    ok = client.patch("/api/v1/me", json={})
    assert "ratelimit" not in ok.headers  # only on the 429
    for _ in range(30):
        client.patch("/api/v1/me", json={})
    h = client.patch("/api/v1/me", json={}).headers
    assert h["ratelimit-policy"] == '"me.update";q=30;w=60'
    m = re.fullmatch(r'"me\.update";r=0;t=(\d+)', h["ratelimit"])
    assert m and m.group(1) == h["retry-after"]


def test_ratelimit_header_names_are_structured_field_strings() -> None:
    h = ratelimit.limit_headers('we"ird\\name', 5, 3600, 12)
    assert h == {
        "Retry-After": "12",
        "RateLimit-Policy": '"we\\"ird\\\\name";q=5;w=3600',
        "RateLimit": '"we\\"ird\\\\name";r=0;t=12',
    }


def test_cors_lets_a_browser_client_send_and_read_the_reliability_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    client = TestClient(create_app())
    pre = client.options(
        "/api/v1/me",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "idempotency-key",
        },
    )
    assert pre.status_code == 200, pre.text
    exposed = client.get("/health", headers={"Origin": "https://app.example.com"}).headers
    for name in ("RateLimit", "RateLimit-Policy", "Retry-After", "Idempotent-Replayed"):
        assert name in exposed["access-control-expose-headers"], name


def test_retry_after_counts_to_window_end() -> None:
    assert ratelimit.retry_after(60, now=120.0) == 60
    assert ratelimit.retry_after(60, now=179.5) == 1
    assert ratelimit.retry_after(3600, now=3600 * 5 + 600) == 3000


# --- dependencies + process model -------------------------------------------------


def test_every_requirement_has_an_upper_bound() -> None:
    # A floating major (anthropic>=0.39) once let prod install a breaking 1.x.
    lines = [
        ln.strip()
        for ln in (ROOT / "requirements.txt").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    assert lines
    for line in lines:
        assert ">=" in line and "<" in line.replace("<=", ""), f"unbounded: {line}"
        upper = line.split("<", 1)[1]
        if line.split(">=", 1)[1].startswith("0."):
            assert upper.startswith("0."), f"0.x package capped at a major: {line}"


def _module_level_mutables(source: str) -> list[str]:
    """Lower-case module-level names bound to mutable containers, and `global` use."""
    tree = ast.parse(source)
    found: list[str] = []
    mutable_calls = {"dict", "list", "set", "defaultdict", "OrderedDict", "deque", "Counter"}
    for node in tree.body:
        targets: list[ast.expr] = []  # Assign.targets or [AnnAssign.target]
        value = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value  # type: ignore[list-item]
        is_mutable = isinstance(value, ast.Dict | ast.List | ast.Set) or (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in mutable_calls
        )
        for t in targets:
            if isinstance(t, ast.Name) and is_mutable and not t.id.isupper():
                found.append(t.id)
    found += [f"global {n}" for x in ast.walk(tree) if isinstance(x, ast.Global) for n in x.names]
    return found


_CACHE_DECORATORS = {"lru_cache", "cache"}
# A memoized function IS a module-level dict with a nicer syntax. One named like
# cross-request state is state, full stop; anything else cached must be listed here
# with the reason it is a per-process singleton and not data about a request.
_STATE_NAME = re.compile(r"state|cache|store|pending|session|nonce|token", re.I)
CACHED_SINGLETONS: dict[str, str] = {
    "backend/auth.py:_jwks_client": (
        "one PyJWKClient per worker: it holds Supabase's PUBLIC signing keys, identical for "
        "every user and every worker; a cold worker just fetches them again"
    ),
    "backend/db.py:_client": (
        "one Supabase client per worker: a connection object carrying the service key and "
        "nothing about any request or user"
    ),
    "backend/http.py:_breaker": (
        "one circuit breaker per upstream per worker: it counts this process's recent "
        "failures calling that host and nothing about any user or request; a worker that "
        "hasn't seen the failures learns them itself within FAILURE_THRESHOLD calls"
    ),
}


def _cached_functions(source: str) -> list[str]:
    """Names of functions decorated with @cache / @lru_cache (bare, called, or qualified)."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for d in node.decorator_list:
            target = d.func if isinstance(d, ast.Call) else d
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
            if name in _CACHE_DECORATORS:
                found.append(node.name)
    return found


def _in_process_state(rel: str, source: str) -> list[str]:
    hits = _module_level_mutables(source)
    for fn in _cached_functions(source):
        if _STATE_NAME.search(fn):
            hits.append(f"cached {fn}: named like cross-request state; put it in Postgres")
        elif f"{rel}:{fn}" not in CACHED_SINGLETONS:
            hits.append(f"cached {fn}: allowlist in CACHED_SINGLETONS with a reason, or drop the cache")
    return hits


def test_backend_keeps_no_in_process_state() -> None:
    # railway.json runs several workers: a module-level dict is per-process state
    # that silently diverges. Constants are UPPER_CASE; state goes in Postgres.
    offenders = {
        rel: hits
        for p in (ROOT / "backend").rglob("*.py")
        if (hits := _in_process_state(rel := str(p.relative_to(ROOT)), p.read_text()))
    }
    assert offenders == {}


def test_cached_singleton_allowlist_is_live_and_justified() -> None:
    for key, reason in CACHED_SINGLETONS.items():
        rel, fn = key.split(":")
        assert fn in _cached_functions((ROOT / rel).read_text()), f"{key}: no longer cached; drop it"
        assert len(reason) > 40, key


def test_in_process_state_guard_catches_a_planted_memo() -> None:
    assert _cached_functions("@lru_cache(maxsize=1)\ndef _pending_tokens():\n    pass\n") == ["_pending_tokens"]
    assert _cached_functions("@cache\ndef x():\n    pass\n") == ["x"]
    assert _cached_functions("@functools.lru_cache\nasync def y():\n    pass\n") == ["y"]
    assert _cached_functions("@router.get('/x')\ndef z():\n    pass\n") == []
    state = _in_process_state("backend/x.py", "@lru_cache\ndef _session_store():\n    pass\n")
    assert state and "named like cross-request state" in state[0]
    unlisted = _in_process_state("backend/x.py", "@lru_cache\ndef _settings():\n    pass\n")
    assert unlisted and "allowlist" in unlisted[0]
    assert _in_process_state("backend/db.py", "@lru_cache(maxsize=1)\ndef _client():\n    pass\n") == []


def test_in_process_state_guard_catches_a_planted_cache() -> None:
    assert _module_level_mutables("_pending = {}\n") == ["_pending"]
    assert _module_level_mutables("seen: set[str] = set()\n") == ["seen"]
    assert _module_level_mutables("def f():\n    global x\n") == ["global x"]
    assert _module_level_mutables("LIMITS = {'a': 1}\n") == []


def test_railway_runs_multiple_workers_behind_the_healthcheck() -> None:
    cfg = json.loads((ROOT / "railway.json").read_text())["deploy"]
    m = re.search(r"--workers (\d+)", cfg["startCommand"])
    assert m, "railway.json startCommand must set --workers"
    workers = int(m.group(1))
    assert workers >= 2  # the reason the no-in-process-state guard exists
    assert cfg["healthcheckPath"] == "/health"
