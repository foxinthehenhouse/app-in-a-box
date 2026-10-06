"""Full-text search over the caller's own rows (recipe-search).

This is the one place the backend talks to Postgres AS THE USER instead of with the
service key. `search_items()` is SECURITY INVOKER: it runs with the caller's rights, so
row-level security applies, and it also filters on `auth.uid()`. Called with the
service key (which bypasses RLS and carries no uid), it returns nothing. So the route
hands PostgREST the user's own access token (`get_user_db`), never the service client:
the database, not a filter someone has to remember, decides whose rows come back.
supabase/tests/database/search.test.sql proves it, including against a planted
SECURITY DEFINER rewrite.

The cursor is opaque to the client: base64url of `[rank, id]` from the last row of the
page. A forged cursor can only move where *your own* results start; it can't reach
anyone else's rows, because the function never looks at another user's.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.auth import CurrentUser, get_current_user
from backend.config import env, feature_missing, supabase_url
from backend.db import rpc

FEATURE = "search (Postgres full-text)"
FUNCTION = "search_items"
DEFAULT_PAGE = 20
# One row past the page tells us whether there is a next one; the SQL caps at 50.
MAX_PAGE = 40
MAX_QUERY_CHARS = 200

_bearer = HTTPBearer(auto_error=False)


def encode_cursor(rank: float, row_id: str) -> str:
    raw = json.dumps([rank, row_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[float, str]:
    """`(rank, id)` from a cursor this API issued. ValueError for anything else."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        rank, row_id = json.loads(raw)
        rank = float(rank)
        row_id = str(uuid.UUID(str(row_id)))
    except (binascii.Error, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid cursor") from exc
    if not math.isfinite(rank):
        raise ValueError("invalid cursor")
    return rank, row_id


def get_user_db(
    user: CurrentUser = Depends(get_current_user),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Iterator[Any]:
    """A PostgREST client that carries the CALLER's access token, so RLS applies.

    `get_current_user` has already verified the token (and 401'd without one). The
    `apikey` is the publishable (anon) key: with it, PostgREST takes the role and uid
    from the user's token. 503 with a named reason when search isn't wired.
    """
    if feature_missing(FEATURE):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{FEATURE} not configured")
    assert creds is not None  # get_current_user refused a missing token already
    from postgrest import SyncPostgrestClient

    client = SyncPostgrestClient(
        f"{supabase_url()}/rest/v1",
        headers={
            "apikey": env("SUPABASE_ANON_KEY"),
            "Authorization": f"Bearer {creds.credentials}",
        },
        timeout=10,
    )
    try:
        yield client
    finally:
        client.aclose()


def search(
    db: Any, query: str, limit: int = DEFAULT_PAGE, cursor: str | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    """One page of the caller's matches, best first, and the cursor for the next page.

    `db` must be the user-scoped client from `get_user_db`. Raises ValueError on a
    cursor this API didn't issue (the route turns it into a 422).
    """
    limit = max(1, min(limit, MAX_PAGE))
    after_rank, after_id = decode_cursor(cursor) if cursor else (None, None)
    rows = (
        rpc(
            db,
            FUNCTION,
            {
                "p_query": query,
                "p_limit": limit + 1,
                "p_after_rank": after_rank,
                "p_after_id": after_id,
            },
        )
        or []
    )
    page = rows[:limit]
    more = len(rows) > limit
    next_cursor = encode_cursor(page[-1]["rank"], page[-1]["id"]) if more and page else None
    return page, next_cursor
