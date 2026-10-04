# Defaults: what a good manager would decide for you

The founder shouldn't have to answer "when should we ask for notifications?" or "do
we need a review prompt?". A seasoned product lead would just decide, and say so.
These are those decisions, baked in. Shape states them as defaults instead of asking
(see `decisions` in `design/brief.json`), and every feature builds to them unless the
founder overrides one. An override is a product call: record it in the ledger
(`status: asked`) so the next agent doesn't "fix" it back.

Paths are relative to the generated app's root. A row says where the default already
lives in the template, or that it's on the roadmap: the kit never claims something
exists that doesn't. `python3 "$KIT/scripts/check_intake.py" defaults` fails on any
path below that isn't real.

| Default | What it means | Where it lives |
|---|---|---|
| Value-first onboarding | No carousels, no tour. The first screen is the core action, and the first session ends on the payoff (`payoff` in the brief). Sign-up comes after the user has something worth saving where the product allows. | The payoff moment: `mobile/components/ui/Celebration.tsx`. A dedicated first-run flow is on the roadmap; until then the core-loop screen is the first screen. |
| Permission priming after the payoff | Never ask on launch. Ask from the moment the permission is useful, after one line saying why, and only once the user has felt the payoff. | `mobile/lib/push.ts` (asks in context, from the Settings toggle or a feature's moment) |
| Notification policy | Opt-in after the first payoff, at most one a day, quiet hours (nothing 9pm to 8am local), and every nudge points at the core loop. No "we miss you". | Push client and sender: `mobile/lib/push.ts`, `backend/services/push_service.py`. The daily cap and quiet hours as enforced code are on the roadmap; today they're a rule `build-feature` follows (`.agents/skills/build-feature/SKILL.md`). |
| Review prompt after the 3rd success | Ask for a store rating only after the user completes the core action successfully for the third time, never after an error, at most once per version. | On the roadmap (needs `expo-store-review`). |
| Share sheet and deep links | Anything worth showing someone has a share action that opens a deep link back into the app. | One link resolver: `mobile/lib/links.ts`, `mobile/app/+native-intent.tsx`, universal links via `mobile/scripts/set-app-domain.js`. The system share sheet is wired for data export (`mobile/lib/export.ts`); a share action for content is on the roadmap. |
| Empty, error and loading states | Every screen has all three, honest and useful: what's missing and the one next step; what went wrong, with a retry and a support code; a skeleton, not a spinner. | `mobile/components/ui/Feedback.tsx` (EmptyState), `mobile/components/ui/ErrorNotice.tsx`, `mobile/components/ui/Skeleton.tsx`, `mobile/components/ui/OfflineBanner.tsx` |
| Accessibility | Labels and roles on everything you can tap, 48px targets, contrast at AA, Dynamic Type, reduced motion honoured. | `.agents/rules/mobile-a11y.md`, reviewed by `.agents/agents/design-a11y-reviewer.md` |
| Dark mode | Light and dark from day one, following the phone, with an override in Settings. | `mobile/lib/theme.ts`, `mobile/app/(app)/settings.tsx` |
| Haptics | A light tap on primary actions and a success buzz on the payoff. On even with reduced motion (they're an accessibility aid, not motion). | `mobile/lib/motion.ts`, `mobile/components/ui/PressableScale.tsx` |
| Account deletion and data export | Delete account and "Download my data" from inside the app (Apple and Google require deletion). | `mobile/app/delete-account.tsx`, `backend/routers/me.py`, `mobile/lib/export.ts`, `backend/routers/export.py` |
| Crash reporting | Crashes arrive with the request id the user sees. | `mobile/lib/monitoring.ts`, `backend/observability.py` |
| Over-the-air updates | JS fixes reach phones without a store review; native changes still need a build. | `mobile/lib/updates.ts`, `mobile/components/ui/UpdateBanner.tsx`, `.agents/skills/ship/SKILL.md` |
| Analytics north star | One number, five events that measure it, success and failure on every user action. | `mobile/lib/analytics.ts`, `mobile/scripts/check-analytics-coverage.js`, `.agents/skills/north-star-report/SKILL.md` |
| Privacy policy | A plain-language policy listing what's collected and why, linked from the store listing and Settings. | The store checklist asks for it (`.agents/skills/ship/SKILL.md`); a fill-in policy template is on the roadmap. |
| Feedback channel | One obvious way to reach a human from inside the app, carrying the support code. | Error screens show a copyable support code (`mobile/components/ui/ErrorNotice.tsx`); an in-app "Send feedback" row is on the roadmap. The channel itself (email, Discord, a form) is a `pre-launch` decision. |
