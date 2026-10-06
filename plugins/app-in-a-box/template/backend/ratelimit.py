"""Per-user rate limiting for write endpoints, counted in Postgres.

Not in-process: the API runs several uvicorn workers (railway.json `--workers`), each
with its own memory, so a module-level counter would let a user through N times the
limit and forget everything on redeploy. The counter lives in `public.rate_limits` and
`public.rate_limit_hit()` increments it atomically (one upsert, one round trip).

Fixed windows: simple and exact per window, but a client can burst up to 2x the
limit across a window boundary. That's fine for abuse protection; if you need a
smooth limit (or >~200 writes/s), move to a sliding window or Redis/Upstash and keep
this dependency's signature so call sites don't change.

    @router.post("/things", dependencies=[Depends(rate_limit("things.create", 30))])

A 429 says when to come back, three ways: `Retry-After` (seconds, the classic), and the
IETF RateLimit fields (draft-ietf-httpapi-ratelimit-headers), `RateLimit-Policy:
"things.create";q=30;w=60` (the quota and window) and `RateLimit: "things.create";r=0;t=12`
(remaining, and seconds until it resets). Only on the 429: putting them on every
response would cost a header per write for numbers nobody reads until they're blocked.

⚖️ Fail-open: if the counter itself errors (DB hiccup), the request is allowed and a
warning is logged, because a limiter outage shouldn't take down every write. Flip
`FAIL_OPEN` to fail closed if abuse costs you more than downtime does.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import Depends, HTTPException, status

from backend.auth import CurrentUser, get_current_user
from backend.db import get_db

logger = logging.getLogger(__name__)
FAIL_OPEN = True


def _count(data: Any) -> int:
    """PostgREST returns a scalar function result bare, but tolerate row shapes too."""
    if isinstance(data, list):
        data = data[0] if data else 0
    if isinstance(data, dict):
        data = next(iter(data.values()), 0)
    return int(data or 0)


def retry_after(window_seconds: int, now: float | None = None) -> int:
    """Seconds until the current fixed window ends (>= 1)."""
    now = time.time() if now is None else now
    return max(1, window_seconds - int(now) % window_seconds)


def _sf_string(value: str) -> str:
    """An RFC 9651 structured-field string: quoted, with `\\` and `"` escaped."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def limit_headers(bucket: str, limit: int, window_seconds: int, reset: int) -> dict[str, str]:
    """The 429's headers: Retry-After plus the IETF RateLimit / RateLimit-Policy fields."""
    name = _sf_string(bucket)
    return {
        "Retry-After": str(reset),
        "RateLimit-Policy": f"{name};q={limit};w={window_seconds}",
        "RateLimit": f"{name};r=0;t={reset}",
    }


def rate_limit(bucket: str, limit: int, window_seconds: int = 60) -> Callable[..., None]:
    """Dependency factory: at most `limit` calls per user per `window_seconds`."""
    if limit < 1 or window_seconds < 1:
        raise ValueError("limit and window_seconds must be >= 1")

    def dependency(
        user: CurrentUser = Depends(get_current_user),
        db: Any = Depends(get_db),
    ) -> None:
        key = f"{bucket}:{user.id}"  # scoped by the verified user id, never the body
        try:
            data = (
                db.rpc("rate_limit_hit", {"p_key": key, "p_window_seconds": window_seconds})
                .execute()
                .data
            )
            count = _count(data)
        except Exception as exc:
            logger.warning("rate limit check failed for %s (%s)", bucket, type(exc).__name__)
            if FAIL_OPEN:
                return
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "rate_limit_unavailable"
            ) from exc
        if count > limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "rate_limited",
                headers=limit_headers(bucket, limit, window_seconds, retry_after(window_seconds)),
            )

    return dependency
