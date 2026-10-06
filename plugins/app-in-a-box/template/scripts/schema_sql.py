#!/usr/bin/env python3
"""What supabase/migrations/*.sql builds: tables, their columns, and whose data they hold.

One parser, shared: tests/test_v1_export.py asks it which tables are user-owned (every
one must be exported), and scripts/check_data_map.py asks it for every column (every
one must be in privacy/data-map.yaml). Two regexes over the same SQL would drift, and
the guard that drifted would be the one that quietly stopped seeing a table.

It is a static read, not a database: `create table`, then `alter table ... add / drop /
rename column`, `alter table ... rename to` and `drop table`, applied in file order.
That covers what migrations in this repo do (.agents/rules/db-migrations.md: additive,
expand/contract). The pgTAP job in .github/workflows/db.yml is the real proof against
Postgres.

A table is **user-owned** when a column references auth.users: the caller's data, by
definition. It is **deleted with the account** when that reference cascades, because
account deletion (DELETE /api/v1/me) deletes the auth user and lets Postgres cascade.

Usage: python3 scripts/schema_sql.py   (prints the tables it sees). Standard library only.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"

_NAME = r'(?:"?public"?\.)?"?(\w+)"?'
CREATE_TABLE = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?" + _NAME + r"\s*\(", re.I)
ALTER_TABLE = re.compile(
    r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?" + _NAME + r"\s+([^;]*);", re.I | re.S
)
DROP_TABLE = re.compile(r"drop\s+table\s+(?:if\s+exists\s+)?" + _NAME, re.I)
# One action of an `alter table` (they are comma-separated).
ADD_COLUMN = re.compile(
    r'^add\s+(?:column\s+)?(?:if\s+not\s+exists\s+)?"?(\w+)"?(.*)$', re.I | re.S
)
DROP_COLUMN = re.compile(r'^drop\s+(?:column\s+)?(?:if\s+exists\s+)?"?(\w+)"?', re.I)
RENAME_COLUMN = re.compile(r'^rename\s+(?:column\s+)?"?(\w+)"?\s+to\s+"?(\w+)"?', re.I)
RENAME_TABLE = re.compile(r'^rename\s+to\s+"?(\w+)"?', re.I)
# A table-level item in a create-table body, not a column.
_CONSTRAINT = re.compile(
    r"^(constraint|primary\s+key|foreign\s+key|unique|check|exclude|like)\b", re.I
)
_AUTH_REF = re.compile(r"references\s+auth\.users\b", re.I)
_CASCADE = re.compile(r"references\s+auth\.users\b.*?on\s+delete\s+cascade", re.I | re.S)
# `add constraint`, `drop constraint`, `rename constraint`...: not columns.
_KEYWORDS = {"constraint", "primary", "foreign", "unique", "check", "exclude", "index"}


@dataclass
class Table:
    name: str
    columns: list[str] = field(default_factory=list)
    user_owned: bool = False  # a column references auth.users
    deleted_with_account: bool = False  # ...and that reference cascades


def strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", re.sub(r"/\*.*?\*/", "", sql, flags=re.S))


def _split_top_level(body: str) -> list[str]:
    """Split on commas outside parentheses (checks, defaults, type modifiers)."""
    items, depth, buf = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            items.append(buf.strip())
            buf = ""
        else:
            buf += ch
    return [i for i in [*items, buf.strip()] if i]


def _balanced(sql: str, open_at: int) -> str:
    """The text inside the parenthesis that opens at sql[open_at]."""
    depth = 0
    for i in range(open_at, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[open_at + 1 : i]
    return sql[open_at + 1 :]


def _note_auth_ref(t: Table, text: str) -> None:
    if _AUTH_REF.search(text):
        t.user_owned = True
        t.deleted_with_account |= bool(_CASCADE.search(text))


def _rename_column(t: Table, m: re.Match[str]) -> None:
    old, new = m.group(1).lower(), m.group(2).lower()
    if old not in _KEYWORDS and old in t.columns:
        t.columns[t.columns.index(old)] = new


def _add_column(t: Table, m: re.Match[str]) -> None:
    col = m.group(1).lower()
    if col in _KEYWORDS:
        return
    if col not in t.columns:
        t.columns.append(col)
    _note_auth_ref(t, m.group(2))


def _drop_column(t: Table, m: re.Match[str]) -> None:
    col = m.group(1).lower()
    if col not in _KEYWORDS and col in t.columns:
        t.columns.remove(col)


_COLUMN_ACTIONS = (
    (RENAME_COLUMN, _rename_column),
    (ADD_COLUMN, _add_column),
    (DROP_COLUMN, _drop_column),
)


def _alter_columns(t: Table, action: str) -> None:
    """Apply one column action (rename, add, drop); the first pattern that matches wins."""
    for rx, apply in _COLUMN_ACTIONS:
        if m := rx.match(action):
            apply(t, m)
            return


def _alter(tables: dict[str, Table], name: str, actions: str) -> None:
    for action in _split_top_level(actions):
        t = tables.get(name)
        if t is None:
            return
        if m := RENAME_TABLE.match(action):
            t.name = m.group(1).lower()
            tables[t.name] = tables.pop(name)
            name = t.name
        else:
            _alter_columns(t, action)


def parse(sql: str) -> dict[str, Table]:
    """Every table the SQL leaves behind, in statement order. Comments never count."""
    sql = strip_comments(sql)
    events: list[tuple[int, str, re.Match[str]]] = []
    for kind, rx in (("create", CREATE_TABLE), ("alter", ALTER_TABLE), ("drop", DROP_TABLE)):
        events += [(m.start(), kind, m) for m in rx.finditer(sql)]
    tables: dict[str, Table] = {}
    for _, kind, m in sorted(events, key=lambda e: e[0]):
        name = m.group(1).lower()
        if kind == "create":
            if name in tables:
                continue  # `create table if not exists` again: the first one stands
            t = Table(name)
            for item in _split_top_level(_balanced(sql, m.end() - 1)):
                if not _CONSTRAINT.match(item):
                    t.columns.append(item.split()[0].strip('"').lower())
                _note_auth_ref(t, item)
            tables[name] = t
        elif kind == "alter":
            _alter(tables, name, m.group(2))
        else:
            tables.pop(name, None)
    return tables


def all_sql(migrations: Path = MIGRATIONS) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(migrations.glob("*.sql")))


def user_owned_tables(sql: str) -> set[str]:
    """Tables with a column referencing auth.users: the caller's data, by definition."""
    return {name for name, t in parse(sql).items() if t.user_owned}


if __name__ == "__main__":
    for t in parse(all_sql()).values():
        flags = ("user-owned" if t.user_owned else "system") + (
            ", deleted with the account" if t.deleted_with_account else ""
        )
        print(f"{t.name} ({flags}): {', '.join(t.columns)}")
    sys.exit(0)
