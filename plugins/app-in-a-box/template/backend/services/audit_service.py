"""The audit trail: one append-only row per sensitive action.

    audit_service.record(db, user.id, "data.export")
    audit_service.record(db, admin.id, "role.change", target=member_id)

Rows land in `public.audit_events` (supabase/migrations/20261005120100_audit_events.sql):
service role only, and a trigger refuses every UPDATE, DELETE and TRUNCATE, so what is
written here stays written. Each row carries the actor (the verified caller's id, or
None for a system job), the action, an optional target, the request id (the same one
in the logs and on Sentry events) and the time.

What counts as sensitive, and must call `record()` in the same handler:
  - account deletion (`DELETE /api/v1/me`): written BEFORE the user is deleted
  - a data export (`GET /api/v1/me/export`)
  - a role or permission change: when you add roles (an admin flag, team membership),
    the endpoint that grants or revokes one records `role.change` with the member's id
    as the target. The template ships no roles, so nothing calls it yet.

Fail closed: `record()` raises if the insert fails, so a sensitive action never
happens without its row. Call it before the irreversible step where there is one.

Never put personal data in `target`: an id or a vendor name, nothing a person typed.
The trail outlives the account by design (it is how you prove the deletion happened),
so it must hold nothing that deletion was meant to remove.
"""

from __future__ import annotations

from typing import Any

from backend.observability import current_request_id

TABLE = "audit_events"

# action -> what it means. A typo'd action is a ValueError, not a row nobody queries.
ACTIONS: dict[str, str] = {
    "account.delete": "the caller deleted their account",
    "account.erasure_failed": "a third-party erasure step failed; target names the vendor",
    "data.export": "the caller downloaded their data",
    "role.change": "a role or permission was granted or revoked; target is the member",
}


def record(db: Any, actor_id: str | None, action: str, target: str | None = None) -> None:
    """Append one audit row. Raises on an unknown action or a failed insert."""
    if action not in ACTIONS:
        raise ValueError(f"unknown audit action {action!r}: add it to audit_service.ACTIONS")
    rid = current_request_id()
    db.table(TABLE).insert(
        {
            "actor_id": actor_id,
            "action": action,
            "target": target,
            "request_id": None if rid == "-" else rid,
        }
    ).execute()
