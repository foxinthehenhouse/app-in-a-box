"""Static migration guards: run on every PR in milliseconds, no database needed.

The real proof is .github/workflows/db.yml (every migration applied to a fresh
Postgres, then pgTAP RLS tests in supabase/tests/). These catch the cheap, common
mistakes before that job even starts, each with a negative control:

  - duplicate / malformed versions (scripts/check_migration_versions.py)
  - a `create table public.x` with no `enable row level security` anywhere in the
    migrations: with the anon key in every app binary, that table is world-readable
  - a `security definer` function without `set search_path` (search-path hijack;
    Supabase's advisor flags it as function_search_path_mutable)
  - a migration with no rollback note in its header
  - a rollback note that drops the tables but leaves a trigger (and its function)
    pointing at them: after that rollback every sign-up fails inside the trigger
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_migration_versions", ROOT / "scripts" / "check_migration_versions.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


checker = _load_checker()


def _strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", re.sub(r"/\*.*?\*/", "", sql, flags=re.S))


def tables_without_rls(sql_texts: list[str]) -> list[str]:
    sql = "\n".join(_strip_comments(s) for s in sql_texts).lower()
    created = set(
        re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?(\w+)\"?\s*\(", sql)
    )
    enabled = set(
        re.findall(
            r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?\"?(\w+)\"?\s+enable\s+row\s+level\s+security",
            sql,
        )
    )
    return sorted(created - enabled)


def definer_without_search_path(sql: str) -> list[str]:
    bad = []
    body = _strip_comments(sql)
    for m in re.finditer(
        r"create\s+(?:or\s+replace\s+)?function\s+([\w.\"]+)\s*\((.*?)\$\$", body, re.S | re.I
    ):
        header = m.group(0).lower()
        if "security definer" in header and "search_path" not in header:
            bad.append(m.group(1))
    return bad


def _comment_text(sql: str) -> str:
    return "\n".join(m.group(1) for m in re.finditer(r"--([^\n]*)", sql))


def rollback_omissions(sql: str) -> list[str]:
    """Triggers and functions a migration creates that its rollback note never drops,
    plus any trigger its note drops AFTER the function it executes (`drop function`
    fails on a dependent trigger; and the order is what a reader will paste)."""
    body = _strip_comments(sql).lower()
    created = set(
        re.findall(r"create\s+(?:or\s+replace\s+)?(?:function|trigger)\s+(?:public\.)?\"?(\w+)", body)
    )
    note = _comment_text(sql).lower()
    i = note.find("rollback")
    note = note[i:] if i >= 0 else ""

    def dropped_at(name: str) -> int:
        m = re.search(rf"drop\s+(?:function|trigger)\s+(?:if\s+exists\s+)?(?:public\.)?\"?{name}\b", note)
        return m.start() if m else -1

    problems = sorted(n for n in created if dropped_at(n) < 0)
    for trig, fn in re.findall(
        r"create\s+(?:or\s+replace\s+)?trigger\s+\"?(\w+)\"?.*?execute\s+(?:function|procedure)\s+(?:public\.)?\"?(\w+)",
        body,
        re.S,
    ):
        if dropped_at(trig) >= 0 and dropped_at(fn) >= 0 and dropped_at(trig) > dropped_at(fn):
            problems.append(f"{trig} must be dropped before {fn}")
    return problems


def test_there_are_migrations() -> None:
    assert MIGRATIONS, "supabase/migrations/ is empty"


def test_migration_versions_are_unique_and_well_formed() -> None:
    assert checker.check([p.name for p in MIGRATIONS]) == []


def test_every_table_has_rls() -> None:
    missing = tables_without_rls([p.read_text() for p in MIGRATIONS])
    assert not missing, (
        f"tables created without `enable row level security`: {missing}. The anon key "
        "ships in every app binary, so these are readable by anyone. See "
        ".agents/rules/db-migrations.md."
    )


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_security_definer_functions_pin_search_path(path: Path) -> None:
    assert definer_without_search_path(path.read_text()) == []


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_migration_notes_its_rollback(path: Path) -> None:
    head = "\n".join(path.read_text().splitlines()[:15]).lower()
    assert "rollback" in head, f"{path.name}: put the rollback SQL in the header comment"


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_rollback_note_drops_every_trigger_and_function(path: Path) -> None:
    assert rollback_omissions(path.read_text()) == [], (
        f"{path.name}: the rollback note must drop these too (trigger first, then its "
        "function). A trigger left pointing at a dropped table breaks every sign-up."
    )


# ---- negative controls ----------------------------------------------------------

_PLANT = """-- Rollback: {note}
create table public.things (id int);
create or replace function public.do_thing() returns trigger language plpgsql as $$ begin return new; end $$;
create trigger on_thing after insert on public.things for each row execute function public.do_thing();
"""


@pytest.mark.parametrize(
    "note, expect",
    [
        ("drop table public.things;", ["do_thing", "on_thing"]),
        ("drop trigger on_thing on public.things; drop table public.things;", ["do_thing"]),
        ("drop function public.do_thing(); drop trigger on_thing on public.things;", ["on_thing must be dropped before do_thing"]),
        ("drop trigger if exists on_thing on public.things;\n--   drop function if exists public.do_thing();", []),
    ],
    ids=["tables-only", "function-forgotten", "wrong-order", "complete"],
)
def test_rollback_omissions_can_fail(note: str, expect: list[str]) -> None:
    assert rollback_omissions(_PLANT.format(note=note)) == expect


def test_rollback_omissions_ignores_commented_out_sql() -> None:
    """The note itself mentions the names; only real `create` statements count."""
    assert rollback_omissions("-- Rollback: drop function public.x();\n-- create function public.x() ...\n") == []



@pytest.mark.parametrize(
    "names, needle",
    [
        (["20260101000000_a.sql", "20260101000000_b.sql"], "duplicate migration version"),
        (["20260101_a.sql"], "not 14 digits"),
        (["init.sql"], "can't read its version"),
        (["20260101000000-a.sql"], "can't read its version"),
    ],
)
def test_version_rules_can_fail(names: list[str], needle: str) -> None:
    assert any(needle in p for p in checker.check(names))


def test_version_checker_cli(tmp_path: Path) -> None:
    (tmp_path / "20260101000000_a.sql").write_text("")
    assert checker.main(["x", str(tmp_path)]) == 0
    (tmp_path / "20260101000000_b.sql").write_text("")
    assert checker.main(["x", str(tmp_path)]) == 1


def test_missing_rls_is_caught() -> None:
    sql = [
        "create table public.notes (id uuid primary key);",
        "create table if not exists public.tags (id int);\nalter table public.tags enable row level security;",
        "-- alter table public.notes enable row level security;  (commented out)",
    ]
    assert tables_without_rls(sql) == ["notes"]


def test_mutable_search_path_is_caught() -> None:
    bad = "create or replace function public.f() returns trigger language plpgsql security definer as $$ begin end; $$;"
    good = "create function public.g() returns int language sql security definer set search_path = '' as $$ select 1 $$;"
    assert definer_without_search_path(bad) == ["public.f"]
    assert definer_without_search_path(good) == []
