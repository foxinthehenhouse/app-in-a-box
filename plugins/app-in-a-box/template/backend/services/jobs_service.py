"""Scheduled jobs. Called by /internal/cron/<job> (routers/internal.py).

Rules every job follows:

- **Idempotent per period.** A cron runner retries, and two schedulers can overlap.
  `claim_run()` inserts (job, run_key) into `public.job_runs`, whose primary key makes
  the second claim fail, so a weekly job runs once per ISO week however often it is
  called. Postgres, not memory: the claim must hold across workers and deploys.
- **Cross-user, but every per-user query is still scoped.** A job iterates users, then
  does per-user work through the same user-scoped helpers the API uses.
- **Bounded.** Page through users; don't load the table.
- **A crash releases the claim.** If a run dies mid-way (a DB error, a deploy), the
  claim is deleted so the scheduler's retry can run it again, instead of the period
  silently reporting `skipped`. Delivery is therefore at-least-once: users already
  handled before the crash may get the push twice. One user's failure never aborts
  the run; it's counted in `failed`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.services import push_service

logger = logging.getLogger(__name__)

PAGE_SIZE = 500


def iso_week(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def claim_run(db: Any, job: str, run_key: str) -> bool:
    """True if this call owns (job, run_key); False if it already ran or is running."""
    try:
        db.table("job_runs").insert({"job": job, "run_key": run_key}).execute()
    except Exception as exc:
        if getattr(exc, "code", None) == "23505":  # unique_violation: already claimed
            return False
        raise
    return True


def release_run(db: Any, job: str, run_key: str) -> None:
    """Give up a claim after a crash so a retry can run this period again."""
    try:
        db.table("job_runs").delete().eq("job", job).eq("run_key", run_key).is_(
            "finished_at", "null"
        ).execute()
    except Exception:  # never mask the original error
        logger.exception("could not release job claim %s/%s", job, run_key)


def finish_run(db: Any, job: str, run_key: str, stats: dict[str, int]) -> None:
    db.table("job_runs").update({"finished_at": datetime.now(UTC).isoformat(), "stats": stats}).eq(
        "job", job
    ).eq("run_key", run_key).execute()


def weekly_digest(
    db: Any,
    *,
    now: datetime | None = None,
    client: push_service.ExpoPushClient | None = None,
) -> dict[str, Any]:
    """Example job: a weekly push to onboarded users. Replace the copy and add a real
    per-user summary (computed with queries scoped by that user's id)."""
    now = now or datetime.now(UTC)
    run_key = iso_week(now)
    if not claim_run(db, "weekly_digest", run_key):
        return {"job": "weekly_digest", "run_key": run_key, "skipped": True}
    try:
        stats = {"users": 0, "sent": 0, "failed": 0}
        start = 0
        while True:
            page = (
                db.table("profiles")
                .select("id")
                .eq("onboarded", True)
                .order("id")
                .range(start, start + PAGE_SIZE - 1)
                .execute()
                .data
                or []
            )
            for row in page:
                stats["users"] += 1
                try:
                    res = push_service.send_to_user(
                        db,
                        row["id"],
                        "Your week, in one glance",
                        "Your weekly summary is ready. Take a look when you have a minute.",
                        {"type": "weekly_digest", "url": "/"},
                        client=client,
                    )
                    stats["sent"] += res.sent
                except Exception as exc:  # one user's failure never aborts the run
                    stats["failed"] += 1
                    logger.warning("weekly_digest push failed: %s", type(exc).__name__)
            if len(page) < PAGE_SIZE:
                break
            start += PAGE_SIZE
    except Exception:
        release_run(db, "weekly_digest", run_key)
        raise
    finish_run(db, "weekly_digest", run_key, stats)
    return {"job": "weekly_digest", "run_key": run_key, "skipped": False, **stats}


def prune_rate_limits(db: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Delete rate-limit windows older than a day (the longest window we use)."""
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=1)).isoformat()
    db.table("rate_limits").delete().lt("window_start", cutoff).execute()
    return {"job": "prune_rate_limits", "before": cutoff}
