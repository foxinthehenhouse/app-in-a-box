"""Image uploads (added by the recipe-uploads skill). Logic: services/uploads_service.py.

POST   /api/v1/uploads                {"contentType": "image/jpeg", "sizeBytes": 123456}
                                      -> UploadTicket (signed URL for one object)
POST   /api/v1/uploads/{id}/complete  -> Upload (recorded once the bytes are in Storage)
GET    /api/v1/uploads                -> UploadList (newest first, signed download URLs)
DELETE /api/v1/uploads/{id}           -> 204

The owner is ALWAYS the verified caller: the object path is built from `user.id`
server-side, and a body naming anyone (or any path) is a 422 (WireIn). Every route is
rate limited: issuing and signing URLs costs Storage calls, and a loop that mints
upload URLs is exactly how a bucket fills up overnight.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import Field

from backend.auth import CurrentUser, get_current_user
from backend.db import get_db
from backend.ratelimit import rate_limit
from backend.routers.me import Wire, WireIn
from backend.services import uploads_service
from backend.services.uploads_service import MAX_BYTES

router = APIRouter(prefix="/api/v1", tags=["uploads"])

# Keep in step with uploads_service.ALLOWED_TYPES (tests/test_uploads.py checks).
ContentType = Literal["image/jpeg", "image/png", "image/webp", "image/heic"]


class UploadRequest(WireIn):
    """POST body. Mirrored by `UploadRequestWire` in mobile/lib/api.ts. Validated here
    so the app gets a clean 422 before it sends a byte; the bucket enforces the same
    limits on the bytes themselves."""

    content_type: ContentType
    size_bytes: int = Field(gt=0, le=MAX_BYTES)


class UploadTicket(Wire):
    upload_id: str
    signed_url: str


class Upload(Wire):
    id: str
    content_type: str
    size_bytes: int
    created_at: str
    download_url: str


class UploadList(Wire):
    items: list[Upload]


def _upload(row: dict[str, Any]) -> Upload:
    return Upload(
        id=str(row["id"]),
        content_type=row["content_type"],
        size_bytes=int(row["size_bytes"]),
        created_at=str(row["created_at"]),
        download_url=row.get("download_url") or "",
    )


@router.post(
    "/uploads",
    response_model=UploadTicket,
    response_model_by_alias=True,
    dependencies=[Depends(rate_limit("uploads.create", 20))],
)
def create_upload(
    body: UploadRequest,  # validating it IS the check: a bad type or size is a 422 here
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> UploadTicket:
    return UploadTicket(**uploads_service.create_upload(db, user.id))


@router.post(
    "/uploads/{upload_id}/complete",
    response_model=Upload,
    response_model_by_alias=True,
    dependencies=[Depends(rate_limit("uploads.complete", 30))],
)
def complete_upload(
    upload_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> Upload:
    return _upload(uploads_service.complete_upload(db, user.id, str(upload_id)))


@router.get(
    "/uploads",
    response_model=UploadList,
    response_model_by_alias=True,
    dependencies=[Depends(rate_limit("uploads.list", 60))],
)
def list_uploads(
    user: CurrentUser = Depends(get_current_user), db: Any = Depends(get_db)
) -> UploadList:
    return UploadList(
        items=[_upload(r) for r in uploads_service.list_uploads(db, user.id)]
    )


@router.delete(
    "/uploads/{upload_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("uploads.delete", 30))],
)
def delete_upload(
    upload_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> Response:
    if not uploads_service.delete_upload(db, user.id, str(upload_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "upload_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
