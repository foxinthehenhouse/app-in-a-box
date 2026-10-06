---
description: Biometric data (the `biometric` guardrail pack)
globs: backend/**, mobile/**, supabase/migrations/**
---
- Match on the device through the OS (Face ID, Touch ID, BiometricPrompt) and keep only
  the outcome. Never store or send a face, fingerprint or voice template.
- No biometric value in analytics props, logs, Sentry or LLM prompts.
- Some places (Illinois' BIPA, the GDPR's special categories) need written consent and a
  retention schedule before any biometric processing: flag it to the owner.
