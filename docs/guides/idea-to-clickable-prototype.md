# Turn an app idea into a clickable prototype before writing code

Changing a prototype takes seconds. Changing a wired-up app takes hours. So App in a
Box settles what the app is and how it looks first, with no accounts, no cloud setup
and no code. You can stop there, show the prototype to people, and carry on only when
you're sure.

## How to get there

Install the plugin ([Quickstart](../../README.md#quickstart)), open an empty folder
and start [`new-app`](../../plugins/app-in-a-box/skills/new-app/SKILL.md)
(`/app-in-a-box:new-app` in Claude Code, `$new-app` in Codex). The first three phases
are the ones on this page. Accounts come after, so when the prototype is frozen you
can simply stop; `appbox.yaml` remembers where you are and the next run resumes.

## 1. Shape: say it however it comes out

Rae, the product advisor
([shape](../../plugins/app-in-a-box/skills/shape/SKILL.md)), lets you ramble, or paste
notes or a voice transcript. She plays it back as one page, asks only what's missing
(two or three questions a round) and gently challenges what might not work. Technical
choices come to you as plain consequences, so you never pick infrastructure.

You get `docs/product/BRIEF.md`: who it's for, their problem, the core loop and what
v1 includes.

## 2. Idea check: is anyone asking for this?

While you talk, a researcher
([validate-idea](../../plugins/app-in-a-box/skills/validate-idea/SKILL.md)) looks
for competitors and workarounds, real complaints in reviews and forums, and what
people already pay. It writes `docs/product/VALIDATION.md`: a cited scorecard with a
Go / Sharpen / Rethink verdict and the riskiest assumptions. It's advice; you decide.

## 3. Prototype: click it, tune it, freeze it

A team of design agents
([prototype](../../plugins/app-in-a-box/skills/prototype/SKILL.md)) builds an HTML
prototype of every v1 screen: one for flows, one for visuals, one for interaction, a
copywriter, and a critic who reviews screenshots against a
[taste rubric](../../plugins/app-in-a-box/docs/TASTE.md) before you see anything.

Open `design/prototype.html` and tap through it like it's real. The side panel lets
you switch:

- the **look**: three design directions, each in light and dark
- the **layout** of each key screen, from two or three variants
- **minimal or rich** density, **calm or playful** motion and wording
- the **atmosphere**: light, grain and glass
- **optional features**, on and off

Press **Copy my choices** and paste them back, or just say what you'd change. A
couple of quick rounds is usually enough. When you decide which features make v1,
each one comes with a one-line build note ("Streaks: easy, no extra cost").

When it's right, the prototype is frozen into:

- `design/tokens.json`: colours, type, spacing and motion, checked by a WCAG contrast
  gate and a design check that rejects stock tells (overused fonts, pure-grey
  neutrals, the default AI violet, bouncy easing)
- `docs/product/SCREENS.md`: each screen's chosen layout mapped to the kit's
  components and native iOS/Android symbols, the navigation, the states and the v1
  feature list

## What happens next (if you want it to)

The scaffold phase builds the real Expo app from `SCREENS.md` and `tokens.json`, and
checks that the app matches the prototype. The prototype skill also works later,
whenever you want to see or change what the app looks like.

## Related

- [Build the whole app with Claude Code](build-an-app-with-claude-code.md) or
  [with Codex](build-an-app-with-codex.md)
- [The design directions reference](../../plugins/app-in-a-box/skills/design-directions/SKILL.md)
- [START_HERE.md](../../START_HERE.md): every phase, with times
