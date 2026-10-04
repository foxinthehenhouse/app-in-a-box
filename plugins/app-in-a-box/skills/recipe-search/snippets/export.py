# recipe-search: only if you kept the example `items` table (search.sql step 0). Add
# this reader to backend/routers/export.py above EXPORTERS, and `"items": _read_items,`
# to EXPORTERS: tests/test_v1_export.py fails until a new user-owned table is exported.
# search_tsv (and embedding, with the hybrid) are derived columns: leave them out.


def _read_items(db: Any, user_id: str, start: int, end: int) -> list[dict[str, Any]]:
    return (
        db.table("items")
        .select("id, title, body, created_at")
        .eq("user_id", user_id)
        .order("id")
        .range(start, end)
        .execute()
        .data
        or []
    )
