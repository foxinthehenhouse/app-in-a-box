"""Scheduled jobs. Called by /internal/cron/<job> (routers/internal.py).

Rules every job follows:

- **Idempotent per period.** A cron runner retries, and two schedulers can overlap.
  `claim_run()` inserts (job, run_key) into `public.job_runs`, whose primary key makes
  the second claim fail, so a weekly job runs once per ISO week however often it is
  called. Postgres, not memory: the claim must hold across workers and deploys.
- **Cross-user, but every per-user query is still scoped.** A job iterates users, then
  does per-user work through the same user-scoped helpers the API uses.
- **Bounded.** Page through users; don't load the table.
- **A crash releases the claim.** If a run dies with a Python exception (a DB error),
  the claim is deleted so the scheduler's retry can run it again, instead of the
  period silently reporting `skipped`. A worker killed outright (a deploy, an OOM,
  SIGKILL) can't run that code, so `claim_run()` also takes over a claim whose
  `started_at` is older than `STALE_RUN_HOURS` with `finished_at` still null. Delivery
  is therefore at-least-once: users already handled before the crash may get the push
  twice. One user's failure never aborts the run; it's counted in `failed`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from backend import idempotency
from backend.services import push_service

logger = logging.getLogger(__name__)

PAGE_SIZE = 500
# An unfinished claim older than this belongs to a worker that is no longer running.
# Longer than any job can honestly take, shorter than the shortest job period (a day).
STALE_RUN_HOURS = 6


def iso_week(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _insert_claim(db: Any, job: str, run_key: str) -> bool:
    try:
        db.table("job_runs").insert({"job": job, "run_key": run_key}).execute()
    except Exception as exc:
        if getattr(exc, "code", None) == "23505":  # unique_violation: already claimed
            return False
        raise
    return True


def claim_run(db: Any, job: str, run_key: str, *, now: datetime | None = None) -> bool:
    """True if this call owns (job, run_key); False if it already ran or is running.

    A claim with `finished_at` null and `started_at` older than STALE_RUN_HOURS was left
    by a worker that died without reaching release_run(); it is deleted and re-taken.
    The delete is filtered on exactly those columns, so a run that finishes in between
    keeps its row, and two reclaimers race on the insert's primary key as usual.
    """
    if _insert_claim(db, job, run_key):
        return True
    cutoff = ((now or datetime.now(UTC)) - timedelta(hours=STALE_RUN_HOURS)).isoformat()
    stale = (
        db.table("job_runs")
        .delete()
        .eq("job", job)
        .eq("run_key", run_key)
        .is_("finished_at", "null")
        .lt("started_at", cutoff)
        .execute()
        .data
    )
    if not stale:
        return False
    logger.warning("reclaimed stale job claim %s/%s", job, run_key)
    return _insert_claim(db, job, run_key)


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
    if not claim_run(db, "weekly_digest", run_key, now=now):
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


# Rows that expire: table -> (timestamp column, how long a row is kept). The daily
# prune cron deletes everything older. A table that stores location must be listed
# here (scripts/check_guardrails.py, the `location` pack): a location history kept
# forever is the most revealing thing an app can hold. Keep it as short as the feature
# allows, and say the number in the privacy policy.
RETENTION: dict[str, tuple[str, timedelta]] = {
    "rate_limits": ("window_start", timedelta(days=1)),  # the longest window we use
    "idempotency_keys": ("created_at", timedelta(seconds=idempotency.TTL_SECONDS)),
}


def prune_rate_limits(db: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Delete expired rows from every table in RETENTION: rate-limit windows, idempotency
    keys past their TTL (backend/idempotency.py), and whatever a feature adds. The job
    keeps its first name so existing schedulers keep calling it."""
    now = now or datetime.now(UTC)
    pruned: dict[str, str] = {}
    for table, (column, keep) in RETENTION.items():
        cutoff = (now - keep).isoformat()
        db.table(table).delete().lt(column, cutoff).execute()
        pruned[table] = cutoff
    return {
        "job": "prune_rate_limits",
        "before": pruned["rate_limits"],
        "idempotency_keys_before": pruned["idempotency_keys"],
        "pruned": pruned,
    }
