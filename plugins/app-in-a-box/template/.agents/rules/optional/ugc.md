---
description: User-generated content and messaging (the `ugc` guardrail pack)
globs: backend/**, mobile/app/**, supabase/migrations/**
---
- Any table of user content ships with report and block (App Store guideline 1.2):
  `content_reports` with a `status`, `user_blocks`, and POST endpoints for both.
- Blocking hides both ways, at once, in every list and query (scope the query, not the UI).
- Reported content disappears for the reporter immediately; moderation works the queue.
- No anonymous or random chat. Never show one user's content to another before the
  author has chosen who can see it.
