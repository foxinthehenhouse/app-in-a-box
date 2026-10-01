"""Register / unregister this device's Expo push token.

POST   /api/v1/me/push-token   {"token": "ExponentPushToken[...]", "platform": "ios"}  -> 204
DELETE /api/v1/me/push-token   {"token": "ExponentPushToken[...]"}                     -> 204

Register goes through `register_push_token()` (a Postgres function) because it is a
multi-row write: it upserts this token AND prunes the user's oldest tokens beyond the
cap, atomically. A token is unique across users: when someone else signs in on the
same phone, the token moves to them, so the previous account stops getting pushes.
The owner is ALWAYS the verified caller, never a body field.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ConfigDict, Field, field_validator

from backend.auth import CurrentUser, get_current_user
from backend.config import feature_missing
from backend.db import get_db, rpc
from backend.ratelimit import rate_limit
from backend.routers.me import Wire
from backend.services.push_service import FEATURE, is_valid_token

router = APIRouter(prefix="/api/v1/me", tags=["push"])

MAX_TOKENS_PER_USER = 10


class PushTokenIn(Wire):
    model_config = ConfigDict(extra="ignore")

    token: str = Field(max_length=256)
    platform: Literal["ios", "android", "web"] | None = None

    @field_validator("token")
    @classmethod
    def _expo_token(cls, v: str) -> str:
        if not is_valid_token(v):
            raise ValueError("not an Expo push token")
        return v


class PushTokenOut(Wire):
    token: str = Field(max_length=256)


def _require_push() -> None:
    if feature_missing(FEATURE):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{FEATURE} not configured")


@router.post(
    "/push-token",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_push), Depends(rate_limit("push_token.write", 20))],
)
def register_push_token(
    body: PushTokenIn,
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> Response:
    rpc(
        db,
        "register_push_token",
        {
            "p_user_id": user.id,
            "p_token": body.token,
            "p_platform": body.platform,
            "p_max_tokens": MAX_TOKENS_PER_USER,
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/push-token",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_push), Depends(rate_limit("push_token.write", 20))],
)
def unregister_push_token(
    body: PushTokenOut,
    user: CurrentUser = Depends(get_current_user),
    db: Any = Depends(get_db),
) -> Response:
    # Scoped by owner: you can only remove a token registered to YOU.
    db.table("push_tokens").delete().eq("user_id", user.id).eq("token", body.token).execute()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
