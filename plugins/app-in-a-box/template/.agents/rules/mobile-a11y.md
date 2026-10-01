---
description: React Native accessibility checklist
globs: mobile/app/**, mobile/components/**
---
- Every interactive element: `accessibilityRole` + an `accessibilityLabel` stating
  **purpose** ("Save profile", not "Save button").
- **48px minimum tap target** (`minTapTarget`). Pad small touchables.
- **Never encode meaning in colour alone.** Pair status colours with text or an icon.
- Text colours come from the ink ramp only (`ink`, `inkDim`, `inkFaint`). `border`
  and decorative colours are not text.
- `testID` follows `{screen}-{component}-{qualifier}`.
- Full-screen tap-to-dismiss backdrops: `accessible={false}` if the sheet has a Close
  button, otherwise `accessibilityRole="button"` with a label like "Close".
- Announce content that replaces the screen via `AccessibilityInfo.announceForAccessibility`.
