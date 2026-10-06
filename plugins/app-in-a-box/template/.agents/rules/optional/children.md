---
description: Children's data (COPPA / age-appropriate design)
globs: backend/**, mobile/**, supabase/migrations/**
---
- No third-party analytics identifiers or session replay for under-13 users; collect
  the minimum data; no public profiles or open messaging by default.
- Parental consent flows are an owner/legal decision. Flag them, don't design around them.
- The `minors` guardrail pack enforces this: the age gate, analytics off for under-age
  users, no ads/attribution SDKs, nothing public by default (docs/privacy/GUARDRAILS.md).
