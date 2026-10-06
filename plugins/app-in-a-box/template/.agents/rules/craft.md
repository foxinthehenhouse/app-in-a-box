---
description: The craft bar for screens and components (docs/design/CRAFT.md, docs/design/TASTE.md)
globs: mobile/app/**, mobile/components/**
---
You are editing something a user sees. Hold it to `docs/design/CRAFT.md` (the bar, and
the component that delivers each row) and `docs/design/TASTE.md` (the taste rubric and
its Copy section). Before you call it done:

- **One primary action** (`Button variant="primary"`, once); the rest secondary or ghost.
- **States:** loading is a `Skeleton`/`SkeletonCard`, empty is an `EmptyState` that
  teaches the next step, error is an `ErrorNotice` with a retry. `check-screen-states`
  fails a data screen under `app/(app)/` without all three (or a `// states: <why>`).
- **Every touch answers** through `PressableScale`, `Button`, `IconButton` or `ListRow`
  (scale, tint, haptic). A bare `Pressable` outside `components/ui/` fails
  `check-design-tells`.
- **Optimistic and reversible:** mutate through a `lib/query.ts` option set (optimistic
  `onMutate`, rollback in `onError`); confirm before anything destructive.
- **Motion explains** where things went (`screenEntrance`, `Card index`, sheet routes);
  reduced motion crossfades.
- **Spacing from `t.space.*` only**; related things close, groups apart.
- **No dead ends:** every state offers a way on, every sheet a Close.
- **Copy in the house voice:** buttons are verbs, errors give a reason or a next step.
  `check-copy` lints `locales/`.

`pr-review` will screenshot the screen in light and dark and the `craft-reviewer` grades
it against CRAFT.md; look at it yourself first (both modes, large text).
