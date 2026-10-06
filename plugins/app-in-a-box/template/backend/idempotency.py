"""Idempotency keys: a write retried with the same `Idempotency-Key` runs ONCE.

The app queues writes offline and replays them on reconnect, even after a restart
(mobile/lib/query.ts). A replay can be a duplicate: the request went out, the server
committed it, and the app died before the response arrived. With a key, the second
request gets the first one's stored response instead of running again.

    @router.post("/things", dependencies=[Depends(rate_limit("things.create", 30)),
                                          Depends(idempotent())])

How it works (state in Postgres, never memory: several workers, and the retry may land
on another one):

1. `idempotent()` (the dependency) reads the header. No header: nothing happens, the
   request runs as usual. A malformed key is a 400.
2. It claims (caller, key) with `idempotency_claim()`, one atomic upsert, recording a
   fingerprint of method + path + body.
   - New claim: the request runs. `IdempotencyMiddleware` holds the response, stores a
     2xx (status, body, content type) on the claim, then sends it. Anything else (4xx,
     5xx, a crash) deletes the claim, so the retry runs for real.
   - Same key, same request, finished: the stored response is replayed with
     `Idempotent-Replayed: true`. The handler does not run.
   - Same key, different request: 422 `idempotency_key_reused` (a client bug).
   - Same key, still running: 409 `idempotency_key_in_flight` with `Retry-After`.
3. Keys expire after `TTL` (the daily prune cron deletes them); an unfinished claim
   older than `STALE_SECONDS` belongs to a worker that died, and is taken over.

Keys are scoped to the verified caller (`user.id` from the token), so one user's key can
never replay another user's response. tests/test_idempotency.py fails any POST route
under /api without this dependency.

⚖️ Fails closed: if the claim itself errors (a DB blip), the request is a 503, not run
unprotected. The client retries a 5xx with the same key, and a write that might run
twice is worse than one that waits. (`backend/ratelimit.py` fails open, the other way.)
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from backend.auth import CurrentUser, get_current_user
from backend.db import get_db

logger = logging.getLogger(__name__)

HEADER = "Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"
KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
TTL_SECONDS = 24 * 60 * 60  # a queued offline write replays within a day, or not at all
STALE_SECONDS = 120  # longer than any request can take (the client gives up at 15s)
STATE_KEY = "idempotency_claim"  # where the dependency leaves the claim for the middleware
MARKER = "__idempotent__"  # set on the dependency, so the route guard can find it


@dataclass
class Claim:
    """This request owns (user_id, key) until the middleware settles it."""

    db: Any
    user_id: str
    key: str
    settled: bool = False


class IdempotentReplay(Exception):
    """Raised by the dependency to answer with a stored response; see `replay_response`."""

    def __init__(self, status_code: int, body: str | None, content_type: str | None) -> None:
        super().__init__(f"replay {status_code}")
        self.status_code = status_code
        self.body = body
        self.content_type = content_type


def fingerprint(method: str, path: str, body: bytes) -> str:
    """What makes two requests "the same": method, path and exact body bytes."""
    digest = hashlib.sha256()
    for part in (method.upper().encode(), path.encode(), body):
        digest.update(len(part).to_bytes(8, "big"))  # length-prefixed: no ambiguous joins
        digest.update(part)
    return digest.hexdigest()


def _first(data: Any) -> dict[str, Any]:
    """PostgREST returns a set-returning function as a list of rows."""
    if isinstance(data, list):
        data = data[0] if data else {}
    return data if isinstance(data, dict) else {}


def idempotent() -> Callable[..., Awaitable[None]]:
    """Dependency factory. Put it AFTER `rate_limit(...)`, so a 429 never claims a key."""

    async def dependency(
        request: Request,
        user: CurrentUser = Depends(get_current_user),
        db: Any = Depends(get_db),
        idempotency_key: str | None = Header(default=None),
    ) -> None:
        if idempotency_key is None:
            return
        if not KEY_RE.match(idempotency_key):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid_idempotency_key")
        fp = fingerprint(request.method, request.url.path, await request.body())
        params = {
            "p_user_id": user.id,  # from the token, never the request
            "p_key": idempotency_key,
            "p_fingerprint": fp,
            "p_stale_seconds": STALE_SECONDS,
            "p_ttl_seconds": TTL_SECONDS,
        }
        try:
            row = _first(
                await run_in_threadpool(lambda: db.rpc("idempotency_claim", params).execute().data)
            )
        except Exception as exc:
            logger.warning("idempotency claim failed (%s)", type(exc).__name__)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "idempotency_unavailable"
            ) from exc
        if row.get("claimed"):
            setattr(request.state, STATE_KEY, Claim(db, user.id, idempotency_key))
            return
        if row.get("stored_fingerprint") != fp:
            raise HTTPException(422, "idempotency_key_reused")
        if row.get("stored_status") is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "idempotency_key_in_flight", headers={"Retry-After": "1"}
            )
        raise IdempotentReplay(
            int(row["stored_status"]), row.get("stored_body"), row.get("stored_content_type")
        )

    setattr(dependency, MARKER, True)
    return dependency


async def replay_response(_request: Request, exc: Exception) -> Response:
    """Exception handler for IdempotentReplay (registered in main.create_app)."""
    assert isinstance(exc, IdempotentReplay)
    no_body = exc.status_code in (204, 304)
    return Response(
        content=None if no_body else (exc.body or "").encode("utf-8"),
        status_code=exc.status_code,
        media_type=None if no_body else exc.content_type,
        headers={REPLAYED_HEADER: "true"},
    )


def _store(
    db: Any, user_id: str, key: str, status_code: int, body: str | None, content_type: str | None
) -> None:
    db.table("idempotency_keys").update(
        {
            "response_status": status_code,
            "response_body": body,
            "response_content_type": content_type,
            "completed_at": datetime.now(UTC).isoformat(),
        }
    ).eq("user_id", user_id).eq("key", key).execute()


def _release(db: Any, user_id: str, key: str) -> None:
    """Drop an unfinished claim so the client's retry runs for real."""
    try:
        db.table("idempotency_keys").delete().eq("user_id", user_id).eq("key", key).is_(
            "response_status", "null"
        ).execute()
    except Exception:  # never mask the response or the original error
        logger.exception("could not release idempotency claim")


def settle(claim: Claim, status_code: int, body: bytes, content_type: str | None) -> None:
    """Store a 2xx on the claim; release it for anything else. Never raises."""
    if claim.settled:
        return
    claim.settled = True
    if not 200 <= status_code < 300:
        _release(claim.db, claim.user_id, claim.key)
        return
    try:
        text = body.decode("utf-8") if body else None
        _store(claim.db, claim.user_id, claim.key, status_code, text, content_type)
    except Exception as exc:  # undecodable body or a DB blip: let the retry run instead
        logger.warning("could not store idempotent response (%s)", type(exc).__name__)
        _release(claim.db, claim.user_id, claim.key)


class IdempotencyMiddleware:
    """Pure ASGI. Only touches requests whose dependency claimed a key: holds that
    response until it is stored, so a fast retry can't find the claim half-written."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state: dict[str, Any] = scope.setdefault("state", {})
        held: list[dict[str, Any]] = []

        async def hold(message: dict[str, Any]) -> None:
            claim = state.get(STATE_KEY)
            if not isinstance(claim, Claim) or claim.settled:
                await send(message)
                return
            held.append(message)
            if message["type"] != "http.response.body" or message.get("more_body", False):
                return
            start = next(m for m in held if m["type"] == "http.response.start")
            ctype = next(
                (
                    v.decode("latin-1")
                    for k, v in start.get("headers", [])
                    if k.lower() == b"content-type"
                ),
                None,
            )
            body = b"".join(m.get("body", b"") for m in held if m["type"] == "http.response.body")
            await run_in_threadpool(settle, claim, start["status"], body, ctype)
            for m in held:
                await send(m)

        try:
            await self.app(scope, receive, hold)
        except BaseException:
            claim = state.get(STATE_KEY)
            if isinstance(claim, Claim) and not claim.settled:
                claim.settled = True
                await run_in_threadpool(_release, claim.db, claim.user_id, claim.key)
            raise
