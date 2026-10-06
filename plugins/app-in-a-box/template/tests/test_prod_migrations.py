"""rpc() error mapping, static migration rules, and (opt-in) the SQL itself against a
real Postgres.

The integration test runs with `-m integration` and DATABASE_URL pointing at a
THROWAWAY Postgres (it creates stub `auth` objects if they're missing, so a bare
Postgres works, and so does `supabase start`). It needs `psql` on PATH.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.config import (
    FEATURE_CONFIG,
    OPTIONAL_FEATURE_CONFIG,
    PRODUCTION_FEATURE_CONFIG,
    check_feature_config,
    feature_missing,
)
from backend.db import rpc
from tests.test_prod_fakes import FakeAPIError, FakeDB

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))


def _sql() -> str:
    return "\n".join(p.read_text() for p in MIGRATIONS)


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


# --- rpc() ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "status"), [("42501", 403), ("P0002", 404), ("23505", 409), ("22023", 422)]
)
def test_rpc_maps_function_errors_to_http(code: str, status: int) -> None:
    db = FakeDB()
    db.rpc_error = FakeAPIError(code, "nope")
    with pytest.raises(HTTPException) as info:
        rpc(db, "anything", {})
    assert info.value.status_code == status


def test_rpc_lets_unknown_errors_become_500s() -> None:
    db = FakeDB()
    db.rpc_error = FakeAPIError("XX000", "internal")
    with pytest.raises(FakeAPIError):
        rpc(db, "anything", {})


def test_rpc_returns_function_result() -> None:
    assert rpc(FakeDB(), "rate_limit_hit", {"p_key": "k", "p_window_seconds": 60}) == 1


# --- feature config ---------------------------------------------------------------


def test_optional_features_are_guarded_by_their_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert feature_missing("scheduled jobs (cron)") == ["CRON_SECRET"]
    assert "scheduled jobs (cron)" not in check_feature_config()
    assert check_feature_config(optional=True) == {"scheduled jobs (cron)": ["CRON_SECRET"]}
    monkeypatch.setenv("CRON_SECRET", "x" * 40)
    assert check_feature_config(optional=True) == {}


def test_feature_names_are_unique_across_registries() -> None:
    names = [*FEATURE_CONFIG, *PRODUCTION_FEATURE_CONFIG, *OPTIONAL_FEATURE_CONFIG]
    assert len(names) == len(set(names))


# --- static migration rules -------------------------------------------------------


def test_every_table_enables_rls() -> None:
    sql = _strip_comments(_sql()).lower()
    tables = set(re.findall(r"create table (?:if not exists )?public\.(\w+)", sql))
    rls = set(re.findall(r"alter table public\.(\w+) enable row level security", sql))
    assert tables
    assert tables <= rls, f"no RLS: {tables - rls}"


def _functions(sql: str) -> list[str]:
    # `or replace` is optional: a plain `create function` is just as callable.
    return re.findall(r"create\s+(?:or\s+replace\s+)?function.*?\$\$;", sql, flags=re.S | re.I)


def unrestricted_definers(sql: str) -> list[str]:
    """Callable SECURITY DEFINER functions without the revoke-from-API-roles + grant-to-
    service_role pair. Trigger functions are skipped: PostgREST can't call them."""
    bad = []
    for fn in _functions(sql):
        low = fn.lower()
        if "security definer" not in low or "returns trigger" in low:
            continue
        m = re.search(r"function\s+public\.(\w+)", low)
        name = m.group(1) if m else f"<unnamed: {low[:60]!r}>"
        revoked = re.search(
            rf"revoke execute on function public\.{name}\([^)]*\)\s+from public, anon, authenticated",
            sql,
            flags=re.I,
        )
        granted = re.search(
            rf"grant execute on function public\.{name}\([^)]*\)\s+to service_role", sql, re.I
        )
        if not (revoked and granted):
            bad.append(name)
    return bad


def test_security_definer_functions_pin_search_path() -> None:
    for fn in _functions(_strip_comments(_sql())):
        if "security definer" in fn.lower():
            assert "set search_path = ''" in fn, fn.splitlines()[0]


def test_callable_security_definer_functions_are_service_role_only() -> None:
    assert unrestricted_definers(_strip_comments(_sql())) == []


def test_rls_guard_catches_a_planted_table() -> None:
    planted = "create table public.sneaky (id int);"
    tables = set(re.findall(r"create table (?:if not exists )?public\.(\w+)", planted))
    rls = set(re.findall(r"alter table public\.(\w+) enable row level security", planted))
    assert tables - rls == {"sneaky"}


_PLANTED_DEFINER = (
    "create function public.sneaky() returns int language sql "
    "security definer set search_path = '' as $$ select 1 $$;"
)


def test_definer_guard_catches_a_plain_create_function_without_revoke() -> None:
    """`create function` (no `or replace`) with no revoke used to pass unseen."""
    assert _functions(_PLANTED_DEFINER), "the function regex no longer sees a plain `create function`"
    assert unrestricted_definers(_strip_comments(_sql()) + "\n" + _PLANTED_DEFINER) == ["sneaky"]


def test_definer_guard_accepts_the_revoke_grant_pair() -> None:
    fixed = (
        _PLANTED_DEFINER
        + "\nrevoke execute on function public.sneaky() from public, anon, authenticated;"
        + "\ngrant execute on function public.sneaky() to service_role;"
    )
    assert unrestricted_definers(fixed) == []


def test_migrations_have_rollback_notes() -> None:
    for p in MIGRATIONS:
        assert "rollback" in p.read_text().lower(), p.name


# --- the SQL, for real ------------------------------------------------------------

# The same platform stubs the DB gate (scripts/db-test.sh) applies, from the one file
# that defines them: supabase/ci/platform_stubs.sql. A private minimal stub here used to
# leave an `auth.users` without `email` behind, and the DB gate, running next against the
# same throwaway database, took that for a real Supabase stack and skipped its stubs.
PLATFORM_STUBS = ROOT / "supabase" / "ci" / "platform_stubs.sql"


def _psql(url: str, sql: str) -> str:
    out = subprocess.run(
        ["psql", url, "-v", "ON_ERROR_STOP=1", "-qtAX"],
        input=sql,
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return out.stdout.strip()


@pytest.mark.integration
def test_migrations_apply_and_functions_behave() -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url or not shutil.which("psql"):
        pytest.skip("needs DATABASE_URL (throwaway Postgres) and psql")
    if _psql(url, "select to_regclass('auth.users') is null;") == "t":
        _psql(url, PLATFORM_STUBS.read_text())  # plain Postgres: stub what GoTrue would own
    _psql(url, "\n".join(p.read_text() for p in MIGRATIONS))
    _psql(url, "\n".join(p.read_text() for p in MIGRATIONS[1:]))  # re-runnable
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    _psql(url, f"insert into auth.users (id) values ('{a}'), ('{b}');")

    def token(i: int) -> str:
        return f"ExponentPushToken[{a[:8]}{i:06d}]"

    # Cap: 12 registrations, newest 3 kept (one transaction each).
    for i in range(12):
        _psql(url, f"select public.register_push_token('{a}', '{token(i)}', 'ios', 3);")
    kept = _psql(url, f"select token from public.push_tokens where user_id = '{a}' order by token")
    assert kept.splitlines() == [token(9), token(10), token(11)]
    # Hand-over: the same device token moves to b, atomically.
    _psql(url, f"select public.register_push_token('{b}', '{token(11)}', null, 3);")
    owner = _psql(url, f"select user_id from public.push_tokens where token = '{token(11)}'")
    assert owner == b
    # Ownership: acting as a with a user JWT for b is refused.
    with pytest.raises(AssertionError, match="not your account"):
        _psql(
            url,
            f"set request.jwt.claim.sub = '{a}';"
            f"select public.register_push_token('{b}', '{token(99)}', null, 3);",
        )
    # Unknown users are refused; malformed tokens violate the check constraint.
    with pytest.raises(AssertionError, match="unknown user"):
        _psql(url, f"select public.register_push_token('{uuid.uuid4()}', '{token(98)}');")
    with pytest.raises(AssertionError, match="check constraint"):
        _psql(url, f"select public.register_push_token('{a}', 'nope');")
    # Least privilege: anon/authenticated can't execute the functions.
    for fn in (
        "register_push_token(uuid, text, text, integer)",
        "rate_limit_hit(text, integer)",
        "idempotency_claim(uuid, text, text, integer, integer)",
    ):
        for role in ("anon", "authenticated"):
            ok = _psql(url, f"select has_function_privilege('{role}', 'public.{fn}', 'execute');")
            assert ok == "f", (role, fn)
    # Rate limit counter increments atomically within a window.
    key = f"test:{uuid.uuid4()}"
    counts = [_psql(url, f"select public.rate_limit_hit('{key}', 3600);") for _ in range(3)]
    assert counts == ["1", "2", "3"]
    # Idempotency: the first claim owns the key; a repeat sees the claim, then the stored
    # response; a claim past its TTL (or abandoned past stale) is taken over.
    fp1, fp2 = "a" * 64, "b" * 64

    def claim(key: str, fp: str, stale: int = 120, ttl: int = 86400) -> str:
        return _psql(
            url,
            f"select claimed, stored_fingerprint, stored_status, stored_body from "
            f"public.idempotency_claim('{a}', '{key}', '{fp}', {stale}, {ttl});",
        )

    assert claim("key-00000001", fp1) == f"t|{fp1}||"
    assert claim("key-00000001", fp1) == f"f|{fp1}||"  # still running
    assert claim("key-00000001", fp2) == f"f|{fp1}||"  # a different request can't take it
    _psql(
        url,
        f"update public.idempotency_keys set response_status = 201, response_body = '{{}}' "
        f"where user_id = '{a}' and key = 'key-00000001';",
    )
    assert claim("key-00000001", fp1) == f"f|{fp1}|201|{{}}"
    _psql(
        url,
        f"update public.idempotency_keys set created_at = now() - interval '2 days' "
        f"where user_id = '{a}' and key = 'key-00000001';",
    )
    assert claim("key-00000001", fp2) == f"t|{fp2}||"  # expired: a new request owns it
    _psql(
        url,
        f"update public.idempotency_keys set created_at = now() - interval '10 minutes' "
        f"where user_id = '{a}' and key = 'key-00000001';",
    )
    assert claim("key-00000001", fp1) == f"t|{fp1}||"  # abandoned claim taken over
    assert claim("key-00000002", fp1).startswith("t|")  # keys are per (user, key)
    with pytest.raises(AssertionError, match="not your account"):
        _psql(
            url,
            f"set request.jwt.claim.sub = '{b}';"
            f"select * from public.idempotency_claim('{a}', 'key-00000003', '{fp1}', 120, 86400);",
        )
    with pytest.raises(AssertionError, match="check constraint"):
        claim("short", fp1)
    # Cascade: deleting the auth user removes their tokens and keys (account deletion).
    _psql(url, f"delete from auth.users where id = '{a}';")
    assert _psql(url, f"select count(*) from public.push_tokens where user_id = '{a}'") == "0"
    assert _psql(url, f"select count(*) from public.idempotency_keys where user_id = '{a}'") == "0"
    # job_runs primary key is the idempotency guard.
    job = f"j-{uuid.uuid4()}"
    _psql(url, f"insert into public.job_runs (job, run_key) values ('{job}', 'w1');")
    with pytest.raises(AssertionError, match="duplicate key"):
        _psql(url, f"insert into public.job_runs (job, run_key) values ('{job}', 'w1');")
