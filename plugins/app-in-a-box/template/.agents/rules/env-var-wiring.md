---
description: A new env-gated feature must be wired into shipping config, not just read in code
globs: mobile/lib/**, mobile/app.config.ts, mobile/eas.json, backend/config.py, backend/main.py
---
Installed-but-unwired features fail **silently** (a `null` client, an empty
`client_id`, a no-op button). Close the loop:

1. **Mobile:** a new `process.env.EXPO_PUBLIC_*` read must exist for shipping builds:
   `eas env:create` for preview + production, and add it to `EAS_MANAGED` in
   `scripts/check-eas-shipping-env.js` (or `eas.json` env blocks).
2. **Backend:** register the vars in `FEATURE_CONFIG` (`backend/config.py`) so absence
   shows in `/health.features_unavailable`. Guard the call site with
   `feature_missing("<its own feature>")`, never "is anything missing?".
3. `.env` is dev-only; no guard reads it. Don't assume prod has what your laptop has.
4. Hand the owner the exact `eas env:create` / Railway variable command for anything
   you can't set yourself.
