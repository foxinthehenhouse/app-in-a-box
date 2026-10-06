---
description: Location data (the `location` guardrail pack)
globs: backend/**, mobile/**, supabase/migrations/**
---
- Read positions through `coarsen()` (`mobile/lib/location.ts`); precise only where the
  feature needs it, said on the line with `guardrail-ok(location): <why>`.
- Background location only for a core feature, with a reason in `privacy/data-map.yaml`
  and a purpose string in the OS prompt. Never for analytics or ads.
- Every location table has a TTL in `backend/services/jobs_service.py` → `RETENTION`.
- Any screen that shares location renders `<WhoCanSeeMe>`. Sharing is opt-in, visible and
  revocable by the person being located, never only by the person watching.
