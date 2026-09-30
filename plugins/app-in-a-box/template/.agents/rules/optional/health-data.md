---
description: Health data handling
globs: backend/**, mobile/lib/**, mobile/app/**, supabase/migrations/**
---
- Health values (weights, vitals, symptoms, sleep) never go into analytics props, logs,
  Sentry events or LLM prompts unless the feature explicitly requires it and it's noted
  in `docs/decision-log.md`.
- No diagnostic or treatment claims in copy. Describe, don't prescribe.
- Any algorithm that changes what a user is told to do physically is a deterministic,
  tested pure function, not LLM output.
