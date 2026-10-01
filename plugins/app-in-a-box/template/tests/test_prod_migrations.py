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
    assert not set(FEATURE_CONFIG) & set(OPTIONAL_FEATURE_CONFIG)


# --- static migration rules -------------------------------------------------------


def test_every_table_enables_rls() -> None:
    sql = _strip_comments(_sql()).lower()
    tables = set(re.findall(r"create table (?:if not exists )?public\.(\w+)", sql))
    rls = set(re.findall(r"alter table public\.(\w+) enable row level security", sql))
    assert tables and tables <= rls, f"no RLS: {tables - rls}"


def _functions(sql: str) -> list[str]:
    return re.findall(r"create or replace function.*?\$\$;", sql, flags=re.S | re.I)


def test_security_definer_functions_pin_search_path() -> None:
    for fn in _functions(_strip_comments(_sql())):
        if "security definer" in fn.lower():
            assert "set search_path = ''" in fn, fn.splitlines()[0]


def test_callable_security_definer_functions_are_service_role_only() -> None:
    sql = _strip_comments(_sql())
    for fn in _functions(sql):
        low = fn.lower()
        if "security definer" not in low or "returns trigger" in low:
            continue  # trigger functions can't be called over the API
        m = re.search(r"function public\.(\w+)", low)
        assert m, f"security definer function without a public name: {low[:80]}"
        name = m.group(1)
        assert re.search(
            rf"revoke execute on function public\.{name}\([^)]*\)\s+from public, anon, authenticated",
            sql,
            flags=re.I,
        ), f"{name} is callable by anon/authenticated"
        assert re.search(
            rf"grant execute on function public\.{name}\([^)]*\)\s+to service_role", sql, re.I
        )


def test_rls_guard_catches_a_planted_table() -> None:
    planted = "create table public.sneaky (id int);"
    tables = set(re.findall(r"create table (?:if not exists )?public\.(\w+)", planted))
    rls = set(re.findall(r"alter table public\.(\w+) enable row level security", planted))
    assert tables - rls == {"sneaky"}


def test_migrations_have_rollback_notes() -> None:
    for p in MIGRATIONS:
        assert "rollback" in p.read_text().lower(), p.name


# --- the SQL, for real ------------------------------------------------------------

AUTH_STUB = """
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role; end if;
end $$;
create schema if not exists auth;
create table if not exists auth.users (id uuid primary key);
create or replace function auth.uid() returns uuid language sql stable as
  $f$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $f$;
"""


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
    schema_sql = AUTH_STUB + "\n".join(p.read_text() for p in MIGRATIONS)
    _psql(url, schema_sql)
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
    for fn in ("register_push_token(uuid, text, text, integer)", "rate_limit_hit(text, integer)"):
        for role in ("anon", "authenticated"):
            ok = _psql(url, f"select has_function_privilege('{role}', 'public.{fn}', 'execute');")
            assert ok == "f", (role, fn)
    # Rate limit counter increments atomically within a window.
    key = f"test:{uuid.uuid4()}"
    counts = [_psql(url, f"select public.rate_limit_hit('{key}', 3600);") for _ in range(3)]
    assert counts == ["1", "2", "3"]
    # Cascade: deleting the auth user removes their tokens (account deletion).
    _psql(url, f"delete from auth.users where id = '{a}';")
    assert _psql(url, f"select count(*) from public.push_tokens where user_id = '{a}'") == "0"
    # job_runs primary key is the idempotency guard.
    job = f"j-{uuid.uuid4()}"
    _psql(url, f"insert into public.job_runs (job, run_key) values ('{job}', 'w1');")
    with pytest.raises(AssertionError, match="duplicate key"):
        _psql(url, f"insert into public.job_runs (job, run_key) values ('{job}', 'w1');")
