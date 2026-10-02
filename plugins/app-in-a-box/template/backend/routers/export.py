"""Download my data (GDPR Art. 15 access / Art. 20 portability).

GET /api/v1/me/export -> 200 DataExport: every row the caller owns, per table, as JSON.

- The owner is ALWAYS the verified caller (`user.id` from the token). There is no
  query parameter or body: nobody can ask for someone else's export.
- One explicitly scoped reader per table in `EXPORTERS`. The service key bypasses RLS,
  so each reader filters by the user id itself (tests/test_scoping_static.py checks
  every chain). `tests/test_v1_export.py` fails when a migration adds a table keyed to
  `auth.users` that isn't exported here (or listed in `NOT_EXPORTED` with a reason).
- Rate limited: an export reads every table, so it is the most expensive GET we serve.
- Read-only handler: plain `def` (runs in the threadpool).

Adding a user-owned table: add `_read_<table>` below and an `EXPORTERS` entry, in the
same PR as the migration.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from backend.auth import CurrentUser, get_current_user
from backend.db import get_db
from backend.ratelimit import rate_limit
from backend.routers.me import Wire

router = APIRouter(prefix="/api/v1/me", tags=["export"])

FORMAT_VERSION = 1
PAGE_SIZE = 1000
MAX_ROWS_PER_TABLE = 50_000


class DataExport(Wire):
    format_version: int
    exported_at: str
    user_id: str
    tables: dict[str, list[dict[str, Any]]]


Reader = Callable[[Any, str, int, int], list[dict[str, Any]]]


def _read_profiles(db: Any, user_id: str, start: int, end: int) -> list[dict[str, Any]]:
    return db.table("profiles").select("*").eq("id", user_id).range(start, end).execute().data or []


def _read_push_tokens(db: Any, user_id: str, start: int, end: int) -> list[dict[str, Any]]:
    return (
        db.table("push_tokens")
        .select("token, platform, created_at, last_seen_at")
        .eq("user_id", user_id)
        .order("id")
        .range(start, end)
        .execute()
        .data
        or []
    )


def _read_push_tickets(db: Any, user_id: str, start: int, end: int) -> list[dict[str, Any]]:
    return (
        db.table("push_tickets")
        .select("ticket_id, token, created_at")
        .eq("user_id", user_id)
        # A batch insert shares one created_at; without a unique tiebreaker Postgres may
        # return the ties in a different order per page, and .range() duplicates/skips.
        .order("created_at")
        .order("ticket_id")
        .range(start, end)
        .execute()
        .data
        or []
    )


# table -> scoped reader. Order is the order tables appear in the file.
EXPORTERS: dict[str, Reader] = {
    "profiles": _read_profiles,
    "push_tokens": _read_push_tokens,
    "push_tickets": _read_push_tickets,
}

# Tables keyed to auth.users that are deliberately NOT exported, with the reason.
NOT_EXPORTED: dict[str, str] = {}


def _read_all(reader: Reader, db: Any, user_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    while len(rows) < MAX_ROWS_PER_TABLE:
        page = reader(db, user_id, len(rows), len(rows) + PAGE_SIZE - 1)
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
    return rows[:MAX_ROWS_PER_TABLE]


@router.get(
    "/export",
    response_model=DataExport,
    response_model_by_alias=True,
    dependencies=[Depends(rate_limit("me.export", 5, 3600))],
)
def export_me(
    user: CurrentUser = Depends(get_current_user), db: Any = Depends(get_db)
) -> DataExport:
    tables = {name: _read_all(reader, db, user.id) for name, reader in EXPORTERS.items()}
    return DataExport(
        format_version=FORMAT_VERSION,
        exported_at=datetime.now(UTC).isoformat(timespec="seconds"),
        user_id=user.id,
        tables=tables,
    )
