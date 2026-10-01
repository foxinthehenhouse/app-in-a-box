---
description: Event-trail coverage (screens, helpers, mutation success+failure)
globs: mobile/app/**, mobile/lib/analytics.ts
---
The event trail from `mobile/lib/analytics.ts` is the only legible reconstruction of a
session. Replay is masked by design; never unmask it (`check-replay-unmask.js` fails CI).

- **New screen under `app/(app)/`** → fire `analytics.screenViewed(...)` on mount.
- **New helper** → it needs a real call site. `check-analytics-coverage.js` flags dead
  helpers (or allowlist it with a reason naming what will call it).
- **User-initiated mutation** → fire BOTH success and failure (`success`,
  `error_code`, `duration_ms`). Success-only is how silent failures produce zero signal.
- Never put PII (email, names, free text) or sensitive magnitudes in event props.
