"""Account deletion beyond Postgres (GDPR Art. 17): Storage, PostHog, Sentry.

Deleting the auth user cascades every `user_id ... on delete cascade` table, but three
places hold data about the user that no cascade reaches:

- **Storage.** Objects don't cascade from auth.users. Every bucket in
  `USER_FILE_BUCKETS` keeps a user's files under `<user id>/...`, and
  `purge_storage()` removes everything under that prefix. A failure here RAISES: the
  files are ours, so the deletion stops (500) and the client's retry finishes the job.
  `tests/test_erasure.py` fails when a migration creates a bucket that is in neither
  `USER_FILE_BUCKETS` nor `NOT_USER_FILE_BUCKETS` (with a reason).
- **PostHog.** The app identifies users by id (mobile/lib/analytics.ts), so PostHog
  holds a person with that distinct id and their events. `delete_posthog_person()`
  deletes both (the persons bulk_delete endpoint, `delete_events: true`).
- **Sentry.** Both SDKs are set up never to send the user (backend/observability.py
  scrubs it, the app sets `sendDefaultPii: false` and never calls setUser), so normally
  there is nothing to find. `purge_sentry_user()` is the backstop for the event that
  carried a user anyway: it deletes every issue matching `user.id:<id>`. That removes
  the WHOLE issue, other users' events in it included, which is the only deletion
  Sentry's API offers at that granularity.

The two vendors are optional and dormant until configured (OPTIONAL_FEATURE_CONFIG in
backend/config.py): with their variables unset they are a no-op that touches no
network, and `/health?deep=1` lists them as unconfigured. They are best effort: a
vendor outage must not keep someone from deleting their account (App Store 5.1.1(v)),
so a failure is logged and written to the audit trail as `account.erasure_failed`
(target: the vendor), which is the to-do list for a manual follow-up. Each vendor call
is idempotent, so a retried deletion repeats them safely.

The HTTP client takes an injectable httpx transport so tests never hit a real vendor.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.config import env, feature_missing

logger = logging.getLogger(__name__)

POSTHOG_FEATURE = "account erasure: PostHog"
SENTRY_FEATURE = "account erasure: Sentry"
TIMEOUT = 10.0
STORAGE_PAGE = 100  # Storage list() page size
STORAGE_REMOVE_BATCH = 1000
SENTRY_MAX_PAGES = 20

# Buckets that hold user files under `<user id>/`. Add yours in the same PR as the
# migration that creates the bucket.
USER_FILE_BUCKETS: tuple[str, ...] = ()

# Buckets a migration creates that hold NO per-user files, with the reason.
NOT_USER_FILE_BUCKETS: dict[str, str] = {}


class ErasureError(RuntimeError):
    """A vendor refused or failed the deletion. The message names the vendor and the
    HTTP status only, never a response body (it may echo the user's id back)."""


# ---- Storage ------------------------------------------------------------------------


def _list_files(bucket: Any, folder: str) -> list[str]:
    """Every object path under `folder`, recursing into sub-folders (id None)."""
    paths: list[str] = []
    offset = 0
    while True:
        page = bucket.list(folder, {"limit": STORAGE_PAGE, "offset": offset}) or []
        for item in page:
            path = f"{folder}/{item['name']}"
            if item.get("id") is None:
                paths += _list_files(bucket, path)
            else:
                paths.append(path)
        if len(page) < STORAGE_PAGE:
            return paths
        offset += STORAGE_PAGE


def purge_storage(db: Any, user_id: str) -> int:
    """Remove every object under `<user_id>/` in each user bucket. Returns the count.

    Raises on failure: the caller must stop before the auth user is deleted."""
    if not user_id or "/" in user_id:
        raise ValueError("purge_storage needs a bare user id")
    removed = 0
    for name in USER_FILE_BUCKETS:
        bucket = db.storage.from_(name)
        paths = _list_files(bucket, user_id)
        for start in range(0, len(paths), STORAGE_REMOVE_BATCH):
            batch = paths[start : start + STORAGE_REMOVE_BATCH]
            # Belt and braces: never remove a path outside the caller's own prefix.
            if not all(p.startswith(f"{user_id}/") for p in batch):
                raise ValueError("a listed path escaped the user's prefix")
            bucket.remove(batch)
            removed += len(batch)
    return removed


# ---- PostHog + Sentry ---------------------------------------------------------------


def _client(transport: httpx.BaseTransport | None, base_url: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
        transport=transport,
    )


def _check(vendor: str, resp: httpx.Response, *, ok_404: bool = False) -> None:
    if resp.is_success or (ok_404 and resp.status_code == 404):
        return
    raise ErasureError(f"{vendor} answered HTTP {resp.status_code}")


def delete_posthog_person(user_id: str, transport: httpx.BaseTransport | None = None) -> bool:
    """Delete the PostHog person with this distinct id, and their events.

    False (and no request) when the feature is unconfigured; True once PostHog accepted
    it. PostHog deletes events asynchronously, so "accepted" is the strongest answer."""
    if feature_missing(POSTHOG_FEATURE):
        return False
    project = env("POSTHOG_PROJECT_ID")
    with _client(transport, env("POSTHOG_API_HOST"), env("POSTHOG_ERASURE_KEY")) as http:
        try:
            resp = http.post(
                f"/api/projects/{project}/persons/bulk_delete/",
                json={"distinct_ids": [user_id], "delete_events": True},
            )
        except httpx.HTTPError as exc:
            raise ErasureError(f"PostHog unreachable ({type(exc).__name__})") from exc
        _check("PostHog", resp, ok_404=True)
    return True


def purge_sentry_user(user_id: str, transport: httpx.BaseTransport | None = None) -> int | None:
    """Delete every Sentry issue tagged with this user, in each configured project.

    None (and no request) when unconfigured; else the number of issues deleted."""
    if feature_missing(SENTRY_FEATURE):
        return None
    org = env("SENTRY_ORG")
    projects = [p.strip() for p in env("SENTRY_PROJECTS").split(",") if p.strip()]
    deleted = 0
    with _client(
        transport, env("SENTRY_API_URL") or "https://sentry.io", env("SENTRY_ERASURE_TOKEN")
    ) as http:
        for project in projects:
            deleted += _purge_sentry_project(
                http, f"/api/0/projects/{org}/{project}/issues/", user_id
            )
    return deleted


def _purge_sentry_project(http: httpx.Client, path: str, user_id: str) -> int:
    """Search, delete what the page held, search again: the list is paged (100 a page)
    and a deleted issue drops out of the next search. Sentry deletes asynchronously, so
    an issue it accepted may still be listed: a page with nothing new means done. And
    bounded, so a search that never runs dry can't spin."""
    # statsPeriod="" searches all time; the default is the last 24 hours.
    query = {"query": f"user.id:{user_id}", "statsPeriod": ""}
    seen: set[str] = set()
    try:
        for _ in range(SENTRY_MAX_PAGES):
            found = http.get(path, params=query)
            _check("Sentry", found)
            ids = [str(i["id"]) for i in found.json() if "id" in i and str(i["id"]) not in seen]
            if not ids:
                return len(seen)
            _check("Sentry", http.delete(path, params=[("id", i) for i in ids]))
            seen.update(ids)
    except httpx.HTTPError as exc:
        raise ErasureError(f"Sentry unreachable ({type(exc).__name__})") from exc
    raise ErasureError(f"Sentry still lists issues for the user after {SENTRY_MAX_PAGES} pages")
