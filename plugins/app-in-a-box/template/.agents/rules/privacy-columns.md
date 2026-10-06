---
description: A migration adds a column that looks personal: map it, minimise it, expire it
globs: supabase/migrations/**
match: \b(?:\w+_)?(?:e_?mail|phone|first_name|last_name|full_name|display_name|address|street|postcode|zip|lat|lng|latitude|longitude|location|coords|birth\w*|dob|gender|ethnicity|religion|sexual\w*|passport|ssn|ip_address|device_id|health\w*|weight|height|heart_rate|blood\w*|diagnosis|medication\w*|symptom\w*|amount|balance|iban|card_number|account_number|face\w*|fingerprint|voiceprint|message|body|caption|bio)(?:_\w+)?\s+(?:text|varchar|character|citext|smallint|int|integer|bigint|numeric|decimal|real|double|float\w*|date|time\w*|jsonb?|geography|geometry|point|bytea|uuid|boolean|inet)\b
example: alter table public.profiles add column birth_date date;
---
This migration adds a column that looks like personal data. Before you go on:

- **Put it in the data map** (privacy/data-map.yaml) under its table, with a
  `category` (identifier, contact, location, health, financial, biometric, ugc, minor,
  ...), a `purpose` a user would accept, and a `retention` (`account`, or an ISO-8601 duration). The privacy
  guard fails CI on a column the map doesn't know.
- **Do you need it at all, at this precision?** A birth year, not a birth date. A
  city, or a position through `coarsen()`, not raw coordinates. A count, not the text.
- **Location expires.** A table holding location gets a TTL in
  `backend/services/jobs_service.py` → `RETENTION` (the prune cron deletes on it).
- **It never leaves through a side door.** Not in `analytics.*` payloads, not in log
  calls, not in Sentry: `scripts/check_guardrails.py` fails CI on each. It is in the
  data export (`routers/export.py`) and goes with the account (cascade or the deletion
  path in `routers/me.py`).
- **Biometric templates are not stored.** Match on the device; keep no face,
  fingerprint or voice data.
- **User content (message, body, caption, bio) shown to other users needs report and
  block** (App Store guideline 1.2); the `ugc` pack enforces it.

The packs and what each enforces: `docs/privacy/GUARDRAILS.md`.
