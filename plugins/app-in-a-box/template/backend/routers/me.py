"""The caller's own profile. A minimal, correctly scoped example to copy."""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from backend.auth import CurrentUser, get_current_user
from backend.db import get_db
from backend.ratelimit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["me"])


class Wire(BaseModel):
    """Base for response models: snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class WireIn(Wire):
    """Base for REQUEST bodies: an unknown field is a 422, never a silent drop.

    Two reasons. A body-supplied owner (`{"userId": ...}`) is refused outright rather
    than ignored, so there is nothing to probe. And a client build that sends a field
    this API no longer has (a rename that forgot mobile/lib/api.ts) fails loudly instead
    of returning 200 having stored nothing. tests/test_wire_contract.py pairs every
    request model with its `*Wire` TS type and requires this base.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Profile(Wire):
    id: str
    display_name: str | None = None
    onboarded: bool = False


class ProfileUpdate(WireIn):
    """PATCH body. Mirrored by `ProfilePatchWire` in mobile/lib/api.ts."""

    display_name: str | None = Field(default=None, max_length=80)
    onboarded: bool | None = None


@router.get("/me", response_model=Profile, response_model_by_alias=True)
def read_me(user: CurrentUser = Depends(get_current_user), db: Any = Depends(get_db)) -> Profile:
    rows = db.table("profiles").select("*").eq("id", user.id).limit(1).execute().data
    if not rows:
        return Profile(id=user.id)
    return Profile(**rows[0])


@router.patch(
    "/me",
    response_model=Profile,
    response_model_by_alias=True,
    dependencies=[Depends(rate_limit("me.update", 30))],
)
def update_me(
    body: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> Profile:
    patch = body.model_dump(exclude_none=True)
    # The id always comes from the verified token, never from the request body.
    row = {**patch, "id": user.id}
    saved = db.table("profiles").upsert(row, on_conflict="id").execute().data
    return Profile(**saved[0]) if saved else Profile(id=user.id, **patch)


class AccountDeletion(WireIn):
    """The client must send `{"confirm": "DELETE"}`: a stray or replayed DELETE with no
    body can't erase an account. Extra fields (e.g. someone else's id) are rejected
    (WireIn). Mirrored by `AccountDeletionWire` in mobile/lib/api.ts."""

    confirm: Literal["DELETE"]


def _delete_user_files(db: Any, user_id: str) -> None:
    """Storage objects do NOT cascade from auth.users. If the app stores files, delete
    this user's objects here (e.g. `db.storage.from_("avatars").remove([...])` for the
    paths under f"{user_id}/") BEFORE the auth user goes. No-op until there's a bucket."""


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit("me.delete", 3, 3600))],
)
def delete_me(
    body: AccountDeletion,
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> Response:
    """Delete the caller's account (App Store guideline 5.1.1(v)).

    Deleting the auth user cascades every `user_id ... on delete cascade` table
    (profiles, push_tokens, ...). The id comes from the verified token only. Idempotent:
    an already-deleted user gets 204. The access token stays cryptographically valid
    until it expires (~1 h), so the client must sign out immediately after a 204.
    """
    _delete_user_files(db, user.id)
    try:
        db.auth.admin.delete_user(user.id)
    except Exception as exc:
        if getattr(exc, "status", None) == 404:
            return Response(status_code=status.HTTP_204_NO_CONTENT)
        raise
    logger.info("account deleted: %s", user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
