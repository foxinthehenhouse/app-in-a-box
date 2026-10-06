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
- **Checked, not just reviewed.** `mobile/scripts/check-a11y.js` (in `npm run gates`)
  fails an unlabelled or role-less Pressable / Touchable / TextInput, an `<Image>` with
  no label and no `accessible={false}`, a label that restates its role, `allowFontScaling={false}`,
  a `maxFontSizeMultiplier` under 1.3 outside `components/ui`, and an animation outside
  `lib/motion.ts` that ignores Reduce Motion. A real exception says why on the line:
  `// a11y-ignore: <why>`. `mobile/__tests__/a11y-screens.test.tsx` renders every route at
  100% and 200% text and fails a control with no role or name; give a new route a root
  testID ending in `-screen` or `-sheet` so it can find it.
- **Store answers come from that evidence.** `python3 scripts/a11y_labels.py` regenerates
  `docs/product/ACCESSIBILITY.md` (CI runs `--check`); never hand-edit a claim into it.
