# Craft: the bar every screen clears

`TASTE.md` says what beautiful and intuitive mean here. This page is the short list a
new screen owes its user, and the piece of the kit that pays each one. If a row's
"delivered by" column doesn't fit your screen, build the missing piece in
`mobile/components/ui/` first, so the next screen gets it for free.

`build-feature` treats this page as part of done. `pr-review` shoots the changed
screens (light and dark) and the `craft-reviewer` agent grades them against it. The
grade is advisory; the rows marked *(gate)* are checked by `npm run gates`.

| # | The screen… | Delivered by |
|---|---|---|
| 1 | **Has one primary action**, under the thumb. Everything else is secondary or ghost. | `Button variant="primary"` (once per screen), `variant="secondary"` / `"ghost"` for the rest |
| 2 | **Has a real empty state that teaches**: what's missing, why it matters, the one next step. Never a blank list. *(gate)* | `EmptyState` with `action`; `check-screen-states.js` |
| 3 | **Loads with skeletons, not spinners**, shaped like the content that's coming. A spinner lives only inside a busy button. *(gate)* | `Skeleton`, `SkeletonCard`, `Button loading`; `check-screen-states.js` |
| 4 | **Fails honestly**: what happened, a retry, the support reference. Offline keeps the last data on screen. *(gate)* | `ErrorNotice`, `useLoaded` (`lib/use-load.ts`), `OfflineBanner`; `check-screen-states.js` |
| 5 | **Answers every touch**: a press scale, a tint and a haptic graded by commitment. *(gate)* | `PressableScale`, `Button`, `IconButton`, `ListRow` (`hapticFor` in `lib/motion.ts`); `check-design-tells.js` raw-pressable |
| 6 | **Changes optimistically, and lets a reversible change be undone.** The screen updates on tap and rolls back if the server says no; a destructive one confirms first. | the option-set pattern in `lib/query.ts` (`updateMeOptions`: `onMutate` + rollback in `onError`), a toast saying what happened (`useToast`), `delete-account.tsx`'s type-to-confirm |
| 7 | **Moves to explain where things went**: screens rise in, a sheet comes up from the edge it leaves by, lists stagger as one list. Reduced motion crossfades. | `Screen` (`screenEntrance`), `Card index` (`entrance`), `formSheet` routes, `lib/motion.ts` |
| 8 | **Keeps the spacing rhythm**: every gap from the token scale (4 · 8 · 16 · 24 · 32 · 48), related things close, groups apart. | `makeStyles((t) => …)` with `t.space.*`, `Section`, `Card` |
| 9 | **Has no dead ends.** Every state offers a way on: back, retry, the next step, or home. Every sheet has a Close. | `SheetHeader` + `closeSheet()`, `ErrorNotice onRetry`, `EmptyState action`, `app/+not-found.tsx` |
| 10 | **Speaks in the house voice**: buttons are verbs, errors give a reason or a next step, no "Oops", no shouting. *(gate)* | `locales/en.ts` through `t()`; `check-copy.js` (rules in `TASTE.md` → Copy) |

## How it's checked

- **Gates (block the push):** `check-screen-states.js`, `check-copy.js`,
  `check-design-tells.js`. Each has a reasoned escape hatch (`// states: <why>`, the
  locale's `_copyIgnore`, `// design-ignore: <why>`) that a reviewer reads.
- **Review (advisory):** `pr-review` runs `scripts/screenshots.sh` on the changed
  routes and hands the PNGs to `craft-reviewer`, which scores each row above and
  lists must-fix items. It never blocks a merge on taste alone; the owner decides.
- **By eye:** before you ask for review, look at your screen in both modes at a large
  text size and run `TASTE.md`'s three diagnostics (squint, delete the icons,
  screenshot).
