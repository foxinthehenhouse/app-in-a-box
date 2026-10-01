"""Machine-to-machine endpoints for scheduled jobs: POST /internal/cron/<job>.

Called by a scheduler (GitHub Actions `schedule:` or a Railway cron service, see
docs/runbooks/release.md) with `X-Cron-Secret: $CRON_SECRET`. Never by the app.

`require_cron_secret` fails CLOSED: unset or short secret -> 503 naming the feature
(so a misconfigured scheduler fails loudly), wrong/missing header -> 401. Comparison is
constant-time. To add a job: write it in services/jobs_service.py (idempotent via
`claim_run`), then add a three-line route here and a schedule entry.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from backend.config import env, feature_missing
from backend.db import get_db
from backend.services import jobs_service, push_service

FEATURE = "scheduled jobs (cron)"
CRON_SECRET_MIN_LENGTH = 32  # `openssl rand -hex 32` gives 64


def require_cron_secret(x_cron_secret: str | None = Header(default=None)) -> None:
    secret = env("CRON_SECRET")
    if feature_missing(FEATURE) or len(secret) < CRON_SECRET_MIN_LENGTH:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{FEATURE} not configured")
    if not x_cron_secret or not hmac.compare_digest(
        x_cron_secret.encode("utf-8"), secret.encode("utf-8")
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid cron secret")


router = APIRouter(
    prefix="/internal/cron",
    tags=["internal"],
    include_in_schema=False,
    dependencies=[Depends(require_cron_secret)],  # runs before get_db
)


@router.post("/weekly-digest")
def weekly_digest(db: Any = Depends(get_db)) -> dict[str, Any]:
    if feature_missing(push_service.FEATURE):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"{push_service.FEATURE} not configured"
        )
    return jobs_service.weekly_digest(db)


@router.post("/push-receipts")
def push_receipts(db: Any = Depends(get_db)) -> dict[str, Any]:
    return push_service.check_receipts(db)


@router.post("/prune-rate-limits")
def prune_rate_limits(db: Any = Depends(get_db)) -> dict[str, Any]:
    return jobs_service.prune_rate_limits(db)
