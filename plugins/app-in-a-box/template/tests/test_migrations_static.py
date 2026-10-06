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
  - embedding tables (a `vector(n)` column: users' own text, embedded for retrieval):
    no HNSW index, or a function / view that reads one while bypassing RLS (a
    `security definer` function, a view without `security_invoker`) or without
    filtering on auth.uid(). Retrieval returns whole chunks of someone's notes, so a
    reader that skips the caller's filter is a cross-user leak with a search box.
    Dormant until a migration adds a vector column (the recipe-ai-feature RAG path).
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


_VECTOR_TYPE = r"(?:extensions\.)?(?:vector|halfvec|sparsevec)\s*\(\s*\d+\s*\)"


def _paren_body(sql: str, open_at: int) -> str:
    """The text inside the parenthesis that opens at `open_at` (balanced)."""
    depth = 0
    for i in range(open_at, len(sql)):
        depth += {"(": 1, ")": -1}.get(sql[i], 0)
        if depth == 0:
            return sql[open_at + 1 : i]
    return sql[open_at + 1 :]


def embedding_tables(sql_texts: list[str]) -> set[str]:
    """Tables with a pgvector column, created with it or given one later."""
    sql = "\n".join(_strip_comments(s) for s in sql_texts).lower()
    found = set()
    for m in re.finditer(
        r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?(\w+)\"?\s*\(", sql
    ):
        if re.search(_VECTOR_TYPE, _paren_body(sql, m.end() - 1)):
            found.add(m.group(1))
    found |= set(
        re.findall(
            r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?\"?(\w+)\"?\s+add\s+"
            rf"(?:column\s+)?(?:if\s+not\s+exists\s+)?\"?\w+\"?\s+{_VECTOR_TYPE}",
            sql,
        )
    )
    return found


def embedding_tables_without_hnsw(sql_texts: list[str]) -> list[str]:
    sql = "\n".join(_strip_comments(s) for s in sql_texts).lower()
    indexed = set(
        re.findall(
            r"create\s+index\s+(?:concurrently\s+)?(?:if\s+not\s+exists\s+)?(?:\"?\w+\"?\s+)?"
            r"on\s+(?:only\s+)?(?:public\.)?\"?(\w+)\"?\s+using\s+hnsw",
            sql,
        )
    )
    return sorted(embedding_tables(sql_texts) - indexed)


def unsafe_embedding_readers(sql_texts: list[str]) -> list[str]:
    """Functions and views that read an embedding table without RLS doing the fencing.

    A retrieval function must be `security invoker` (the default) so RLS applies, AND
    filter on auth.uid() itself, so a service-key caller (which bypasses RLS) gets
    nothing back instead of everyone's chunks. A view must set security_invoker.
    """
    tables = embedding_tables(sql_texts)
    if not tables:
        return []
    sql = "\n".join(_strip_comments(s) for s in sql_texts).lower()

    def reads(body: str) -> list[str]:
        return sorted(t for t in tables if re.search(rf"(?<![\w.])(?:public\.)?\"?{t}\"?(?!\w)", body))

    bad = []
    for m in re.finditer(
        r"create\s+(?:or\s+replace\s+)?function\s+([\w.\"]+)(.*?)(\$\w*\$)(.*?)\3([^;]*);", sql, re.S
    ):
        name, attrs, body = m.group(1), m.group(2) + m.group(5), m.group(4)
        for t in reads(body):
            if re.search(r"security\s+definer", attrs):
                bad.append(f"{name} reads {t} as security definer (bypasses RLS)")
            elif not re.search(r"auth\.uid\(\s*\)", body):
                bad.append(f"{name} reads {t} without filtering on auth.uid()")
    for m in re.finditer(r"create\s+(?:or\s+replace\s+)?view\s+([\w.\"]+)([^;]*);", sql, re.S):
        name, stmt = m.group(1), m.group(2)
        head = stmt.split(" as ", 1)[0]
        if reads(stmt) and not re.search(r"security_invoker\s*=\s*(?:true|on)", head):
            bad.append(f"{name} is a view over {', '.join(reads(stmt))} without security_invoker")
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


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: p.name)
def test_rollback_note_drops_every_trigger_and_function(path: Path) -> None:
    assert rollback_omissions(path.read_text()) == [], (
        f"{path.name}: the rollback note must drop these too (trigger first, then its "
        "function). A trigger left pointing at a dropped table breaks every sign-up."
    )


def test_embedding_tables_have_an_hnsw_index() -> None:
    missing = embedding_tables_without_hnsw([p.read_text() for p in MIGRATIONS])
    assert not missing, (
        f"vector tables with no HNSW index: {missing}. Every retrieval would scan the "
        "whole table: `create index ... using hnsw (embedding extensions.vector_cosine_ops)`."
    )


def test_embedding_readers_respect_rls() -> None:
    bad = unsafe_embedding_readers([p.read_text() for p in MIGRATIONS])
    assert not bad, (
        "cross-user leak risk in retrieval: " + "; ".join(bad) + ". Make it `security "
        "invoker`, filter `user_id = (select auth.uid())`, and call it with the caller's "
        "JWT (see the recipe-ai-feature skill)."
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


_RAG = """
create table public.chunks (
  id bigint primary key,
  user_id uuid not null default auth.uid(),
  embedding extensions.vector(1024) not null
);
create index chunks_hnsw on public.chunks using hnsw (embedding extensions.vector_cosine_ops);
create or replace function public.match(p_q extensions.vector(1024)) returns setof public.chunks
language sql stable security invoker set search_path = '' as $$
  select * from public.chunks c where c.user_id = (select auth.uid())
  order by c.embedding operator(extensions.<=>) p_q limit 5;
$$;
"""


def test_embedding_guards_pass_a_safe_retrieval_migration() -> None:
    assert embedding_tables([_RAG]) == {"chunks"}
    assert embedding_tables_without_hnsw([_RAG]) == []
    assert unsafe_embedding_readers([_RAG]) == []


@pytest.mark.parametrize(
    "edit, expect",
    [
        (("security invoker", "security definer"), "public.match reads chunks as security definer"),
        (("where c.user_id = (select auth.uid())", ""), "public.match reads chunks without filtering on auth.uid()"),
        (("$$;\n", "$$;\ncreate view public.all_chunks as select * from public.chunks;\n"), "public.all_chunks is a view over chunks without security_invoker"),
    ],
    ids=["definer", "no-user-filter", "definer-view"],
)
def test_embedding_reader_leaks_are_caught(edit: tuple[str, str], expect: str) -> None:
    planted = _RAG.replace(*edit)
    assert planted != _RAG
    assert any(expect in b for b in unsafe_embedding_readers([planted])), unsafe_embedding_readers([planted])


def test_embedding_guards_see_a_later_column_and_a_missing_index() -> None:
    sql = "create table public.notes (id int);\nalter table public.notes add column embedding vector(384);"
    assert embedding_tables([sql]) == {"notes"}
    assert embedding_tables_without_hnsw([sql]) == ["notes"]
    no_index = _RAG.replace("create index chunks_hnsw", "-- create index chunks_hnsw")
    assert embedding_tables_without_hnsw([no_index]) == ["chunks"]


def test_embedding_guards_allow_an_invoker_view_and_ignore_non_readers() -> None:
    sql = _RAG + (
        "create view public.my_chunks with (security_invoker = true) as select id from public.chunks;\n"
        "create function public.chunks_count_unrelated() returns int language sql as $$ select 1 $$;\n"
    )
    assert unsafe_embedding_readers([sql]) == []
