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


# ---- negative controls ----------------------------------------------------------


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
