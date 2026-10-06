"""Search the caller's own items (recipe-search).

GET /api/v1/search?q=<text>[&cursor=<nextCursor>][&limit=20] -> 200 SearchPage

- Whose rows: always the verified caller's. There is no user parameter, and the query
  runs as the user (backend/services/search_service.py), so RLS applies too.
- `q` uses web-search syntax: words are ANDed, "quoted phrase", `or`, `-exclude`.
  Any input is valid; one with no searchable words returns an empty page.
- Paging is keyset, not offset: pass `nextCursor` back as `cursor` until it is null.
  Results don't shift or repeat when rows are added between pages.
- Read-only handler: plain `def` (runs in the threadpool).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.ratelimit import rate_limit
from backend.routers.me import Wire
from backend.services import search_service

router = APIRouter(prefix="/api/v1", tags=["search"])


class SearchHit(Wire):
    id: str
    title: str
    # Plain text around the match (no markup), or the start of the body.
    snippet: str


class SearchPage(Wire):
    items: list[SearchHit]
    next_cursor: str | None = None


@router.get(
    "/search",
    response_model=SearchPage,
    response_model_by_alias=True,
    dependencies=[Depends(rate_limit("search", 60))],
)
def search_items(
    q: str = Query(min_length=1, max_length=search_service.MAX_QUERY_CHARS),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=search_service.DEFAULT_PAGE, ge=1, le=search_service.MAX_PAGE),
    db: Any = Depends(search_service.get_user_db),
) -> SearchPage:
    query = q.strip()
    if not query:
        return SearchPage(items=[])
    try:
        rows, next_cursor = search_service.search(db, query, limit, cursor)
    except ValueError as exc:
        raise HTTPException(422, "invalid_cursor") from exc
    return SearchPage(
        items=[
            SearchHit(id=str(r["id"]), title=r["title"], snippet=r.get("snippet") or "")
            for r in rows
        ],
        next_cursor=next_cursor,
    )
