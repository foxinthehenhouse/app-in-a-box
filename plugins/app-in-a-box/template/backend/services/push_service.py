"""Push notifications through the Expo Push API.

    send_to_user(db, user.id, "Title", "Body", {"url": "/(app)/thing/123"})

How Expo push works, and what this module does about each step:

1. **Send** (`/push/send`, at most 100 messages per request): Expo answers with one
   *ticket* per message. An `error` ticket with `DeviceNotRegistered` means the app
   was uninstalled or the token rotated, so that token is deleted right away.
2. **Receipts** (`/push/getReceipts`, at most 1000 ids per request, available ~15 min
   later, kept ~24 h): the delivery result from Apple/Google. Ticket ids are stored
   in `public.push_tickets` (Postgres, not memory: several workers, and the check
   runs in a later cron call), and `check_receipts()` (cron: /internal/cron/push-receipts)
   prunes tokens whose receipt says `DeviceNotRegistered`.

Every token read/delete is scoped by the owning user's id. Pure helpers
(`chunks`, `parse_tickets`, `parse_receipts`) carry the logic and are unit-tested;
the HTTP client (backend/http.py: timeout, retries, circuit breaker) takes an
injectable transport so tests never hit Expo.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from backend import http as outbound
from backend.config import env
from backend.flags import enabled

logger = logging.getLogger(__name__)

FEATURE = "push (Expo)"
EXPO_BASE = "https://exp.host/--/api/v2/push"
SEND_BATCH = 100  # Expo's per-request limit for /push/send
RECEIPT_BATCH = 1000  # Expo's per-request limit for /push/getReceipts
RECEIPT_DELAY = timedelta(minutes=15)
RECEIPT_TTL = timedelta(hours=24)  # Expo drops receipts after ~a day
TOKEN_RE = re.compile(r"^Expo(nent)?PushToken\[[A-Za-z0-9_\-:.]{10,200}\]$")
DEAD = "DeviceNotRegistered"


class PushError(RuntimeError):
    """Expo rejected the whole request (HTTP error or top-level `errors`)."""


@dataclass(frozen=True)
class PushMessage:
    to: str
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)
    sound: str | None = "default"

    def payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"to": self.to, "title": self.title, "body": self.body}
        if self.data:
            out["data"] = self.data
        if self.sound:
            out["sound"] = self.sound
        return out


@dataclass
class SendResult:
    sent: int = 0
    tickets: list[tuple[str, str]] = field(default_factory=list)  # (ticket_id, token)
    dead_tokens: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # Expo error codes, never payloads


def is_valid_token(token: str) -> bool:
    return bool(TOKEN_RE.match(token))


def chunks[T](items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    if size < 1:
        raise ValueError("size must be >= 1")
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _error_code(entry: dict[str, Any]) -> str:
    details = entry.get("details")
    if isinstance(details, dict) and isinstance(details.get("error"), str):
        return details["error"]
    return "unknown"


def parse_tickets(tokens: Sequence[str], body: Any) -> SendResult:
    """Map Expo's per-message tickets (same order as the request) onto tokens."""
    if not isinstance(body, dict):
        raise PushError("malformed response")
    if body.get("errors"):
        codes = [e.get("code", "unknown") for e in body["errors"] if isinstance(e, dict)]
        raise PushError(f"request rejected: {','.join(codes) or 'unknown'}")
    data = body.get("data")
    if not isinstance(data, list) or len(data) != len(tokens):
        raise PushError("ticket count does not match message count")
    result = SendResult()
    for token, ticket in zip(tokens, data, strict=True):
        if not isinstance(ticket, dict):
            result.errors.append("unknown")
        elif ticket.get("status") == "ok" and isinstance(ticket.get("id"), str):
            result.sent += 1
            result.tickets.append((ticket["id"], token))
        else:
            code = _error_code(ticket)
            result.errors.append(code)
            if code == DEAD:
                result.dead_tokens.append(token)
    return result


def parse_receipts(body: Any) -> tuple[set[str], set[str]]:
    """-> (ticket ids that have a final receipt, ticket ids whose device is gone)."""
    if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
        raise PushError("malformed receipts response")
    done: set[str] = set()
    dead: set[str] = set()
    for ticket_id, receipt in body["data"].items():
        if not isinstance(receipt, dict):
            continue
        done.add(ticket_id)
        if receipt.get("status") == "error" and _error_code(receipt) == DEAD:
            dead.add(ticket_id)
    return done, dead


class ExpoPushClient:
    """Thin HTTP wrapper. Pass `transport=httpx.MockTransport(...)` in tests."""

    def __init__(self, transport: outbound.Transport | None = None, timeout: float = 15) -> None:
        headers = {"Accept": "application/json", "Accept-Encoding": "gzip"}
        token = env("EXPO_ACCESS_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = outbound.client(
            "expo-push", base_url=EXPO_BASE, headers=headers, timeout=timeout, transport=transport
        )

    def _post(self, path: str, json: Any, *, idempotent: bool = False) -> Any:
        try:
            resp = self._http.post(path, json=json, idempotent=idempotent)
        except outbound.HTTPError as exc:
            raise PushError(f"expo unreachable: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise PushError(f"expo HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:  # a proxy's HTML error page, a truncated body
            raise PushError("expo returned a non-JSON body") from exc

    def send(self, messages: Sequence[PushMessage]) -> SendResult:
        total = SendResult()
        for batch in chunks(list(messages), SEND_BATCH):
            res = parse_tickets(
                [m.to for m in batch], self._post("/send", [m.payload() for m in batch])
            )
            total.sent += res.sent
            total.tickets += res.tickets
            total.dead_tokens += res.dead_tokens
            total.errors += res.errors
        return total

    def receipts(self, ticket_ids: Sequence[str]) -> tuple[set[str], set[str]]:
        done: set[str] = set()
        dead: set[str] = set()
        for batch in chunks(list(ticket_ids), RECEIPT_BATCH):
            # A read sent as POST: safe to repeat on a 5xx, unlike /send.
            body = self._post("/getReceipts", {"ids": list(batch)}, idempotent=True)
            d, x = parse_receipts(body)
            done |= d
            dead |= x
        return done, dead

    def close(self) -> None:
        self._http.close()


def _prune(db: Any, user_id: str, tokens: Iterable[str]) -> None:
    tokens = sorted(set(tokens))
    if tokens:
        db.table("push_tokens").delete().eq("user_id", user_id).in_("token", tokens).execute()


def send_to_user(
    db: Any,
    user_id: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    *,
    client: ExpoPushClient | None = None,
) -> SendResult:
    """Send to every device of ONE user. Records tickets, prunes dead tokens.

    Sends nothing while the `kill-push` kill switch is on (backend/flags.py).
    """
    if enabled("kill-push", user_id):
        logger.warning("push skipped: the kill-push kill switch is on")
        return SendResult()
    rows = db.table("push_tokens").select("token").eq("user_id", user_id).execute().data or []
    tokens = [r["token"] for r in rows if is_valid_token(r.get("token", ""))]
    if not tokens:
        return SendResult()
    own = client is None
    client = client or ExpoPushClient()
    try:
        result = client.send([PushMessage(t, title, body, data or {}) for t in tokens])
    finally:
        if own:
            client.close()
    _prune(db, user_id, result.dead_tokens)
    if result.tickets:
        db.table("push_tickets").insert(
            [{"ticket_id": tid, "user_id": user_id, "token": tok} for tid, tok in result.tickets]
        ).execute()
    if result.errors:
        logger.info(
            "push to user had %d errors: %s", len(result.errors), sorted(set(result.errors))
        )
    return result


def check_receipts(
    db: Any, *, client: ExpoPushClient | None = None, now: datetime | None = None, limit: int = 5000
) -> dict[str, int]:
    """Cron: fetch receipts for tickets older than RECEIPT_DELAY, prune dead tokens,
    delete settled tickets (and ones older than RECEIPT_TTL, whose receipt is gone)."""
    now = now or datetime.now(UTC)
    ready_before = (now - RECEIPT_DELAY).isoformat()
    rows = (
        db.table("push_tickets")
        .select("ticket_id,user_id,token,created_at")
        .lt("created_at", ready_before)
        .order("created_at")
        .limit(limit)
        .execute()
        .data
        or []
    )
    if not rows:
        return {"checked": 0, "pruned": 0, "settled": 0}
    own = client is None
    client = client or ExpoPushClient()
    try:
        done, dead = client.receipts([r["ticket_id"] for r in rows])
    finally:
        if own:
            client.close()
    expired_before = now - RECEIPT_TTL
    pruned = 0
    settled: list[str] = []
    for r in rows:
        if r["ticket_id"] in dead:
            _prune(db, r["user_id"], [r["token"]])  # scoped to the ticket's owner
            pruned += 1
        created = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
        if r["ticket_id"] in done or created < expired_before:
            settled.append(r["ticket_id"])
    for batch in chunks(settled, 500):
        db.table("push_tickets").delete().in_("ticket_id", list(batch)).execute()
    return {"checked": len(rows), "pruned": pruned, "settled": len(settled)}
