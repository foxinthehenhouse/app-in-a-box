---
description: Every column, analytics prop and permission is declared in privacy/data-map.yaml
globs: supabase/migrations/**, mobile/lib/analytics.ts, mobile/app.json, privacy/**
---
`privacy/data-map.yaml` is the one list of personal data this app touches. The App
Store and Play answers, the iOS privacy manifest and the privacy-policy draft are
generated from it, so a column nobody mapped is data the store answers don't disclose.

- **New column, table, analytics prop or permission** → add it to the map in the same
  PR: its `category`, a `purpose` in plain words, a `retention`, and `shared_with` if a
  third party (not a processor) gets it. Then `python3 scripts/check_data_map.py --write`
  and commit what it regenerates.
- **Sensitive data** (contact, location, health, financial, biometric, ugc, minor)
  needs a retention and never goes to analytics. Send a count, a bucket or a yes/no.
- **`retention: account`** only for tables that cascade from `auth.users`; anything
  else needs a duration and a job that deletes it.
- **Permission text** says what the user gets ("show your runs on a map"), never
  "needed for app functionality". Apple rejects vague usage strings, and so does the guard.
- **A new vendor that receives user data** goes under `processors` (it works for you) or
  `third_parties` (it uses the data for itself), so the policy names it.

`python3 scripts/check_data_map.py` runs in CI and pre-commit. The generated policy is a
draft: the owner reviews it before publishing, and it is not legal advice.
