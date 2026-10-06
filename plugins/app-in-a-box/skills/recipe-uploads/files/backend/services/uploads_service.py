"""Image uploads to a private Supabase Storage bucket (added by the recipe-uploads skill).

The bytes never pass through this API. The flow:

1. `create_upload()`: the app says what it wants to send (type + size). Both are
   checked here, the object path is chosen HERE (`<user id>/<random uuid>`, never
   from the request), and Storage hands back a signed upload URL for exactly that path.
2. The app PUTs the file straight to Storage with that URL. The bucket itself enforces
   `file_size_limit` and `allowed_mime_types` (see the migration), so a client that
   lies about step 1 is refused by Storage, not trusted.
3. `complete_upload()`: `record_upload()` (a Postgres function) reads what actually
   landed from `storage.objects`, re-checks size and type, and records the row in
   `public.uploads`. An object that fails the check is removed.

Reads hand out short-lived signed download URLs; the bucket is private, so a URL is
the only way to see a file. Every path is built from the caller's verified id. Storage
objects do NOT cascade from auth.users: the bucket is listed in
`erasure_service.USER_FILE_BUCKETS`, so account deletion empties the caller's folder
(completed uploads or not) before the auth user goes.

The limits live here and in the migration's bucket row; tests/test_uploads.py fails
if the two disagree.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status

from backend.db import rpc

BUCKET = "uploads"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB: a phone photo at quality 0.8 is 1-4 MB
# iOS hands over HEIC unless the picker re-encodes (lib/uploads.ts asks for JPEG).
ALLOWED_TYPES = ("image/jpeg", "image/png", "image/webp", "image/heic")
DOWNLOAD_URL_TTL = 60 * 60  # an hour: long enough to render a screen, short if leaked
EXPORT_URL_TTL = 7 * 24 * 60 * 60  # a week to download the files named in a data export


def object_path(user_id: str, upload_id: str) -> str:
    """The only shape a path can have: the caller's folder, then a server-chosen uuid."""
    return f"{user_id}/{upload_id}"


def _bucket(db: Any) -> Any:
    return db.storage.from_(BUCKET)


def create_upload(db: Any, user_id: str) -> dict[str, str]:
    """A fresh upload id and a signed URL that can write exactly one object under the
    caller's folder. Type and size were validated by the request model (and are
    enforced again by the bucket and by record_upload())."""
    upload_id = str(uuid.uuid4())
    signed = _bucket(db).create_signed_upload_url(object_path(user_id, upload_id))
    return {"upload_id": upload_id, "signed_url": signed["signed_url"]}


def complete_upload(db: Any, user_id: str, upload_id: str) -> dict[str, Any]:
    """Record an upload once the bytes are in Storage. Idempotent: completing twice
    returns the same row. 404 if nothing landed at the path; 422 (and the object is
    removed) if what landed is too big or not an allowed image."""
    try:
        row = rpc(
            db,
            "record_upload",
            {
                "p_user_id": user_id,
                "p_upload_id": upload_id,
                "p_max_bytes": MAX_BYTES,
                "p_allowed_types": list(ALLOWED_TYPES),
            },
        )
    except HTTPException as exc:
        if exc.status_code == 422:  # landed, but too big or not an allowed image
            _bucket(db).remove([object_path(user_id, upload_id)])
        raise
    if isinstance(row, list):
        row = row[0] if row else None
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "upload_not_found")
    return with_download_urls(db, [row], DOWNLOAD_URL_TTL)[0]


def list_uploads(db: Any, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    rows = (
        db.table("uploads")
        .select("id, path, content_type, size_bytes, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .order("id")
        .limit(limit)
        .execute()
        .data
        or []
    )
    return with_download_urls(db, rows, DOWNLOAD_URL_TTL)


def delete_upload(db: Any, user_id: str, upload_id: str) -> bool:
    """Remove one of the caller's uploads (object, then row). False if it isn't theirs."""
    rows = (
        db.table("uploads")
        .select("id")
        .eq("id", upload_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return False
    _bucket(db).remove([object_path(user_id, upload_id)])
    db.table("uploads").delete().eq("id", upload_id).eq("user_id", user_id).execute()
    return True


def with_download_urls(
    db: Any, rows: list[dict[str, Any]], ttl_seconds: int
) -> list[dict[str, Any]]:
    """Each row plus `download_url`, signed in one batch call. Rows come from reads
    scoped to the caller, and the table's check constraint pins every `path` to its
    owner's folder, so this only ever signs the caller's own files."""
    if not rows:
        return []
    signed = _bucket(db).create_signed_urls([r["path"] for r in rows], ttl_seconds)
    by_path = {s.get("path"): s.get("signedURL") or s.get("signedUrl") for s in signed}
    return [{**r, "download_url": by_path.get(r["path"]) or ""} for r in rows]

