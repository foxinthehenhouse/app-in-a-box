---
name: prototype
description: Phase 2 of App in a Box. Before any code or cloud setup, the team builds a clickable HTML prototype of every v1 screen with toggles for design direction, light/dark, layout variants per screen, density, motion temperature, atmosphere (light, grain, glass), copy tone and optional features; the founder clicks through and refines it in a few quick rounds, then the approved prototype is frozen into design tokens, a screen map and v1 scope that the scaffold builds from. Use after shape, or whenever someone wants to see or change what the app looks like.
---

# Phase 2: Prototype (click it before we build it)

`$KIT` is the plugin root: `${CLAUDE_PLUGIN_ROOT}` in Claude Code, two levels above
this file in Codex, or `<clone>/plugins/app-in-a-box` otherwise.

Changing a prototype costs seconds; changing a wired-up app costs hours. So the whole
UX gets settled here, where it's cheap. You are still **Rae** (the advisor talks, the
team builds). Read `docs/TASTE.md` and `docs/COST.md` first.

The contract is `design/prototype.json` (schema below). Agents write **the spec**;
`scripts/prototype.py` renders the HTML. Never hand-write the prototype HTML.

## Step 1: one question round (inspiration)

Ask together (structured):
1. **"Any apps whose look or feel you love, or can't stand?"** (free text, optional).
   *Why:* one example beats ten adjectives.
2. **Mobbin, only if its MCP is connected** (tools named `mcp__Mobbin__*` or a
   `mobbin` server): "Want me to pull real screens and flows from top apps on Mobbin
   for inspiration? (It's a paid service you're already connected to.)" Yes / No. If
   it's not connected, say in one line that Mobbin is optional and skip it.

Record the answers in `brief.json` → `feel.inspiration` / `feel.avoid`.

## Step 2: build (parallel, then gate)

Every helper gets `design/brief.json` + `docs/TASTE.md` as a stable prefix, nothing else
(`docs/COST.md`). In Claude Code run them as subagents; in Codex, one after another.

1. `flow-architect` (Ines) → `tabs`, `screens`, `sheets`, navigation, empty states.
2. Then in parallel:
   - `visual-designer` (Kai) → 3 `directions` (full tokens v2, light + dark, `icons`),
     using Mobbin references if opted in.
   - `interaction-designer` (Noor) → 2–3 `variants` per key screen (3 for the core-loop
     screen), `features` with tagged blocks.
   - `tech-advisor` (Omar) → build notes per feature and variant (easy/medium/hard,
     costs, what's hard to change later). Keep them for Step 4, not in the spec.
3. `copywriter` (Sam) → every visible string in calm + playful tones.
4. Assemble `design/prototype.json`, then:
   ```
   python3 "$KIT/scripts/prototype.py" check design/prototype.json
   ```
   Fix every line it prints (dangling links, two primary buttons or one behind a
   feature toggle, lorem, missing empty states, contrast, too many tabs, unknown icons,
   unused features) and re-run until clean.

   **If `prototype.py` itself crashes** (a Python traceback rather than a list of
   check lines), it's a kit bug, not a spec problem. Don't hand-write the HTML to get
   past it. Save the traceback and `design/prototype.json`, file an issue on the kit
   repo (`gh issue create -R foxinthehenhouse/app-in-a-box`, or give the founder the
   text to paste), and tell the founder in one line. Then keep going: if `freeze`
   still runs, freeze from the spec; if not, write `docs/product/SCREENS.md` by hand
   from the spec's screens, variants and states (same headings the freeze would
   write), set `progress.design: done`, and continue from phase 3. The scaffold builds
   from SCREENS.md either way.
5. `design-critic` (Vera) reviews against TASTE.md. On FAIL, apply her fixes and re-check.
   After 2 failed rounds, turn the disagreement into a ⚖️ question for the founder.
6. Render:
   ```
   python3 "$KIT/scripts/prototype.py" render design/prototype.json design/prototype.html
   ```
7. **Look at it before the founder does.** Screenshot every screen and sheet, light and
   dark, plus one with reduced motion:
   ```
   node "$KIT/scripts/proto_shots.mjs" design/prototype.html design/shots
   ```
   If it exits 3 (no Playwright), take the same shots with whatever browser tool you
   have (Claude in Chrome, a DevTools or Playwright MCP, Codex's browser). If you have
   none, say so in one line and let `design-critic` work from the spec. Then
   `design-critic` reviews the PNGs, not the spec alone: the TASTE.md rubric, the three
   diagnostics, the Anti-slop list. Fix the spec and re-render on FAIL (2 rounds max,
   as in step 5). A tell it spots that isn't on the Anti-slop list yet goes into
   `design/avoid.md` (one line each), which every later round and every future screen
   reads alongside TASTE.md, so the list grows with the app.

## Step 3: show it

Open or publish `design/prototype.html` (preview/publish if your environment can,
otherwise give the path; `open design/prototype.html` on macOS). Tell them what to try,
in 4 lines max:

> Tap through it like it's real. On the side panel you can switch the **look** (three
> directions, light/dark), each screen's **layout**, how **minimal or rich** it feels,
> **calm or playful** motion and wording, the **atmosphere** (light, grain, glass), and
> turn **optional features** on and off.
> When you like it, press **"Copy my choices"** and paste it here, or just tell me.

## Step 4: refine (1–3 quick rounds)

If they pasted choices, apply them. Then ask what's still open (structured, 2–3 per
round, recommended option first, *why* on each):
- **Direction** (A/B/C or "mix: describe").
- **Layout of the core-loop screen**, and of any other screen with variants.
- **Density and temperature** ("Minimal and calm", "Rich and lively"…) and **tone**.
- **Features in v1**: each toggle with Omar's one-line build note ("Streaks: easy, no
  extra cost"; "Sharing with friends: hard, needs a second user before it's useful").
- **"Anything that felt off?"** Free text; turn it into spec edits.

Each change is a spec edit → `check` → `render`, which is fast and cheap. Show the
re-rendered prototype and say what changed in one line. Offer to stop refining after
each round; don't wear them out.

## Step 5: freeze

When they say it's right, confirm once ("This becomes the app: screens, look and v1
features. Changing it later is still possible, just slower."). Write their choices to
`design/choices.in.json`: the JSON they pasted from "Copy my choices", verbatim, or
built from what they told you (`direction`, `mode`, `density`, `temperature`, `tone`,
`variants: {screen: variant}`, `features: {id: bool}`, `atmosphere: {mode: none|glow|field,
intensity: low|medium|high, grain: bool, surface: solid|glass}`; anything left out takes
the spec's default, so `{}` means "the defaults"). Then:

```
python3 "$KIT/scripts/prototype.py" freeze design/prototype.json design/choices.in.json --target .
python3 "$KIT/scripts/check_contrast.py" design/tokens.json
```

That writes `design/tokens.json` (the chosen direction with density and temperature
applied, plus `atmosphere`: the knobs, both light colours and their contrast-safe alpha), `docs/product/SCREENS.md` (each screen's chosen layout mapped to the kit's
components, the navigation, the states and the v1 feature list),
`design/choices.json` and `DESIGN.md` (the design system every later agent reads before
UI work, generated from tokens.json; a re-freeze rewrites only its generated blocks, so
write the feel in the founder's words and any design call in its Decisions log, outside
the markers). Update `BRIEF.md` → "Screens (v1)" and "Out of scope for v1"
from SCREENS.md. Set `progress.design: done`.

## `design/prototype.json` (schema)

`prototype.py check` enforces every rule here and names the field it rejects. Shape:

```json
{
  "version": 1,
  "app": {"name": "…", "tagline": "…"},
  "directions": [{"id": "calm", "label": "Calm", "why": "…", "icons": "rounded",
                  "tokens": {"…tokens v2, as in skills/design-directions…": 0}}],
  "defaults": {"direction": "calm", "mode": "light", "density": "regular",
               "temperature": "calm", "tone": "calm"},
  "features": [{"id": "streaks", "label": "Streaks", "default": false, "why": "…"}],
  "tabs": [{"screen": "home", "label": "Home", "icon": "home"}],
  "screens": [{"id": "home", "title": "Home",
               "variants": [{"id": "list", "label": "List", "blocks": []}],
               "states": {"empty": []}}],
  "sheets": [{"id": "add", "title": "Add", "blocks": []}]
}
```

A direction's tokens may set its default atmosphere, e.g. `"atmosphere": {"mode":
"field"}` for a direction whose whole point is a living, lit feel. Without one it's a
soft glow with grain on solid surfaces. You never pick the glow's colours: the renderer
derives them from the accent and keeps every ink at AA on the lit ground (`check` names
a bad value). The renderer also does the motion (overlapping blur-rise screen changes
on the direction's spring tokens, staggered content, touch bloom, a receding sheet,
numbers that count up) and its reduced-motion version. None of it goes in the spec.

Strings are plain or `{"calm": "…", "playful": "…"}` (the copy-tone toggle), one line
each. Tabs come only from `tabs`; every other screen is reached by a `go` action. Actions:
`{"go": "<screen>"}`, `{"sheet": "<id>"}`, `{"back": true}`, `{"toast": "…"}`.

Blocks (required fields, then *optional*). Any block can also carry
`"feature": "<id>"` (shown only while that toggle is on) and `"note"` (an annotation):

| Block | Fields |
|---|---|
| `header` | `title`; *`eyebrow`, `subtitle`* |
| `text` | `body`; *`style`* |
| `list` | `items` (each `title`; *`meta`, `trailing`, `icon`, `action`*); *`title`* |
| `card` | `title`; *`eyebrow`, `body`, `icon`, `action`* |
| `button` | `label`, `style` (`primary` / `secondary` / `ghost`); *`icon`, `action`* |
| `chips`, `segmented` | `options`; *`label`, `selected`* |
| `input` | `label`; *`placeholder`, `value`* |
| `stat` | `label`, `value`; *`hint`, `icon`* |
| `progress` | `label`, `value` (0–1); *`hint`* |
| `empty` | `title`, `body`; *`icon`, `action`*: an empty state's action also needs a `label` (its button text) |
| `image` | *`label`, `ratio`* (e.g. `"3:4"`) |
| `divider` | *`label`* |
| `toast` | `text` |

Icons (a direction draws them `rounded` or `sharp`): arrow, bell, bolt, book,
bookmark, calendar, camera, cart, chart, check, chevron, clock, close, edit, filter,
flame, gift, heart, home, image, info, leaf, list, lock, mail, message, money, moon,
pin, play, plus, search, settings, share, sparkle, star, sun, tag, trash, user, users.
Freeze maps each one to its native iOS and Android symbol in SCREENS.md.

## Exit check

`prototype.py check` is clean, `design/tokens.json` passes the contrast gate,
`docs/product/SCREENS.md` exists, and the founder said yes to the frozen version.
