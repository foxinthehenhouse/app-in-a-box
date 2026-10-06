---
description: Money handling
globs: backend/**, mobile/lib/**, mobile/app/**, supabase/migrations/**
---
- Money is an integer in minor units (cents) plus an ISO currency code. Never a float,
  in the DB, the wire or the UI state.
- Balances are derived from an append-only ledger of transactions, never an
  updated-in-place number.
- No amounts, account numbers or merchant names in analytics props, logs or Sentry.
- Copy never implies investment, lending or financial advice.
- The `financial` guardrail pack lints analytics payloads and log calls, and fails a
  floating-point money column (docs/privacy/GUARDRAILS.md).
