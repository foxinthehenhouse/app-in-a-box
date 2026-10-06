---
description: FE↔BE wire shape is a contract that old app builds hold you to
globs: backend/routers/**, mobile/lib/api.ts
---
The Pydantic response models and the `*Wire` interfaces in `mobile/lib/api.ts` are
mirrored **by hand**. Mobile ships on a release train, so someone is always running a
build from weeks ago against today's API.

- **Add alongside, never mutate in place.** Don't rename, retype or remove a response
  field; add the new one, populate both, migrate the client, and remove the old one in a
  later PR.
- Don't add a required request field without a default that old clients omit.
- **A generic cast is not validation.** `apiFetch<T>()` asserts a shape. When the wire
  shape differs from the UI shape, write an adapter (`toX(wire)`) with a test.
- Change a response model → update its `*Wire` interface in the same PR.
- **A new POST takes `Depends(idempotent())`** (after `rate_limit(...)`); the app's write
  adapter takes `{ idempotencyKey }` and passes it to `apiFetch`. `tests/test_idempotency.py`
  fails a POST under `/api` without it.
- **A new list returns `Page[Thing]`** (`backend/pagination.py`, keyset cursor), mirrored as
  `ThingPageWire { items: ThingWire[]; nextCursor: string | null }` and read with
  `usePagedQuery()`. Never an offset: a row added between loads shifts every later page.

Merge-gate question: *if last month's App Store build gets this JSON tomorrow, does it
still work?*
