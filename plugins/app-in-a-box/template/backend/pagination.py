"""Keyset pagination: `Page[T]` on the wire, and a helper that builds the query.

    @router.get("/things", response_model=Page[Thing], response_model_by_alias=True)
    def list_things(
        cursor: Cursor = None, limit: Limit = 20,
        user: CurrentUser = Depends(get_current_user), db: Any = Depends(get_db),
    ) -> Page[Thing]:
        query = db.table("things").select("*").eq("user_id", user.id)
        rows = keyset(query, ORDER, cursor=cursor, limit=limit).execute().data or []
        return page(rows, ORDER, limit, Thing)

    ORDER = ("created_at", "id")   # newest-last; the LAST column must be unique

Why keyset, not `.range(offset, ...)`: an offset counts rows, so a row inserted or
deleted between two page loads shifts every later page (the user sees an item twice,
or never), and page 500 costs Postgres 500 pages of reading. A keyset cursor says
"after this row": stable under writes, and an index on the order columns makes every
page the same cost. Add `create index on things (user_id, created_at, id)`.

The cursor is opaque to the client (base64 JSON of the last row's order values): it
passes `nextCursor` back verbatim and stops when it is null. The mobile side is
`usePagedQuery()` in mobile/lib/query.ts. A cursor is not a secret and grants nothing:
the query is still scoped by the caller's user id.

Mirror each `Page[Thing]` in mobile/lib/api.ts as `ThingPageWire { items: ThingWire[];
nextCursor: string | null }` and pair it in tests/test_wire_contract.py.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Any

from fastapi import HTTPException, Query, status

from backend.routers.me import Wire

MAX_LIMIT = 100
MAX_CURSOR_LENGTH = 1024

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
Cursor = Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)]


class Page[T](Wire):
    """One page of results, and the cursor for the next (null on the last page)."""

    items: list[T]
    next_cursor: str | None = None


def encode_cursor(row: Mapping[str, Any], order: Sequence[str]) -> str:
    values = [row[col] for col in order]
    raw = json.dumps(values, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, order: Sequence[str]) -> list[Any]:
    """The order values a cursor carries. 400 `invalid_cursor` for anything else."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        values = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_cursor") from exc
    if not isinstance(values, list) or len(values) != len(order):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_cursor")
    if any(v is None or isinstance(v, dict | list) for v in values):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_cursor")
    return values


def _quote(value: Any) -> str:
    """A PostgREST filter value, double-quoted so `,.:()` in it (timestamps!) are literal."""
    text = value if isinstance(value, str) else json.dumps(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def after_filter(order: Sequence[str], values: Sequence[Any], desc: bool = False) -> str:
    """The PostgREST `or=(...)` body for "rows after these order values".

    (a, b) > (va, vb)  ==  a > va  OR  (a = va AND b > vb), and so on for more columns.
    """
    op = "lt" if desc else "gt"
    terms = []
    for i, col in enumerate(order):
        eqs = [f"{order[j]}.eq.{_quote(values[j])}" for j in range(i)]
        cmp = f"{col}.{op}.{_quote(values[i])}"
        terms.append(f"and({','.join([*eqs, cmp])})" if eqs else cmp)
    return ",".join(terms)


def keyset(
    query: Any, order: Sequence[str], *, cursor: str | None, limit: int, desc: bool = False
) -> Any:
    """Order, filter past the cursor, and fetch limit+1 rows (the extra one says "more")."""
    if not order:
        raise ValueError("keyset pagination needs at least one order column")
    for col in order:
        query = query.order(col, desc=desc)
    if cursor:
        query = query.or_(after_filter(order, decode_cursor(cursor, order), desc))
    return query.limit(limit + 1)


def page[T](
    rows: Sequence[Mapping[str, Any]],
    order: Sequence[str],
    limit: int,
    item: Callable[..., T],
) -> Page[T]:
    """Build the Page from the limit+1 rows `keyset()` fetched."""
    more = len(rows) > limit
    rows = rows[:limit]
    return Page(
        items=[item(**r) for r in rows],
        next_cursor=encode_cursor(rows[-1], order) if more and rows else None,
    )
