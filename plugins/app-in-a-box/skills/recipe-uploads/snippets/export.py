def _read_uploads(db: Any, user_id: str, start: int, end: int) -> list[dict[str, Any]]:
    """The caller's uploaded files (recipe-uploads), each with a signed download link
    that lasts a week, so the export includes the files and not just their names."""
    rows = (
        db.table("uploads")
        .select("id, path, content_type, size_bytes, created_at")
        .eq("user_id", user_id)
        .order("created_at")
        .order("id")
        .range(start, end)
        .execute()
        .data
        or []
    )
    return uploads_service.with_download_urls(db, rows, uploads_service.EXPORT_URL_TTL)


