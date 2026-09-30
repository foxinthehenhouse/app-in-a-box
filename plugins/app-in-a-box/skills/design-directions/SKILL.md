---
name: design-directions
description: Phase 2 of App in a Box. It renders 3 distinct design directions as phone-sized HTML mockups of the user's own core screen (with motion and a light/dark toggle), has them pick or mix one, then writes a design/tokens.json with BOTH a light and a dark palette, motion, type roles and elevation, contrast-validated in both modes, that the scaffold turns into the app's theme. Use it for initial design or a re-skin.
---

# Phase 2: Design directions

People can't choose a design system from adjectives. Show them their own app in
three coats of paint, and let them point.

## Step 1: pick 3 directions from the archetype library

Choose the three archetypes below that best fit `appbox.yaml` (target user,
retention mechanic, sensitive data). Make them **genuinely different**. Every
direction ships **both** a light and a dark palette (the app follows the phone's
setting); pick which one each mockup shows first by the archetype's home mode.

| Archetype | Feel | Good for | Type pairing | Radius | Motion (tokens) |
|---|---|---|---|---|---|
| **Calm** | Airy, soft neutrals, one muted accent (home: light) | Wellbeing, journaling, finance | Humanist sans (Inter / Figtree) | 16–24 | Slow fades: `standard` 260ms, gentle springs, press scale 0.98 |
| **Athletic dark** | Near-black field, warm off-white ink, one hot accent (home: dark) | Fitness, performance, pro tools | Grotesk + mono numerals (Inter Tight + JetBrains Mono) | 12 | Snappy: `fast` 120ms, stiff springs (damping 22, stiffness 320) |
| **Playful** | Saturated brand colour, chunky shapes, confetti moments (home: light) | Gamified habits, savings, kids-adjacent | Rounded sans (Nunito / Baloo 2) | 20–28 | Bouncy: overshoot `enter` curve, springs damping ~9–12, press scale 0.95 |
| **Editorial** | Serif headlines, generous whitespace, paper tones (home: light) | Content, reading, learning | Serif + sans (Fraunces + Inter) | 4–8 | Minimal: fades only, no springs |
| **Clinical** | White/blue, dense information, high trust (home: light) | Health data, B2B, admin | System sans (SF / Roboto) | 8 | Almost none: `fast` fades |
| **Neo-brutal** | Hard borders, flat blocks, loud type (home: either) | Creator tools, youth, novelty | Display grotesk (Space Grotesk) | 0 | Hard cuts: `instant` durations, no easing flourish |

**Deriving the other mode** (don't just invert): keep the accent's hue, and shift
lightness so it still reads (a light-mode accent usually needs to be *darker* to clear
3:1 on a pale background; a dark-mode accent *lighter*). Dark surfaces step **up** in
lightness as they elevate (bg < surface < surfaceRaised) because shadows vanish on
dark grounds. Tint neutrals toward the brand hue rather than pure grey.

## Step 2: render the mockups

Write one self-contained HTML file, `design/directions.html`:
- Three phone frames (390×844) side by side, stacked on narrow screens.
- Each frame shows **the user's core-loop screen** from `docs/product/BRIEF.md`,
  with realistic sample content in their domain, not lorem ipsum. Below it, show a
  strip with the primary button, a card, a list row, an input, a chip row, a
  skeleton line, an empty state and a toast: the kit's real components.
- **A light/dark toggle per frame** (and one global): each direction's palettes are
  CSS custom properties on the frame (`.a[data-mode="dark"] { --bg: ... }`), so the
  toggle proves both palettes, not just the flattering one.
- **Motion preview in CSS** from the direction's motion tokens: the button scales to
  `pressScale` on `:active` with the `fast` duration, the list rows enter with a
  staggered fade + 8px rise (`enter` curve, `deliberate` duration), the skeleton
  shimmers on the `loop` curve, the toast slides in, and a "Celebrate" button fires a
  CSS confetti burst for playful directions. Wrap it all in
  `@media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }`,
  the same promise the app makes.
- Label each one with its archetype name and one line on why it fits.
- Only inline CSS/JS and Google Fonts. No build step.

Show it to the user. If your environment can publish or preview HTML, use that.
Otherwise give them the file path to open. Then ask (structured):
"Which direction?" with the options A / B / C / "Mix: I'll describe".

## Step 3: write `design/tokens.json` (tokens v2)

This is the single source of truth. The renderer generates `mobile/lib/tokens.ts`
(both palettes + types), themes `app.json` (splash background per mode) and draws a
placeholder icon from it. Start from the kit's `template/design/tokens.json` and
change values; keep every key.

```json
{
  "name": "athletic-dark",
  "version": 2,
  "mode": "dark",
  "color": {
    "light": {
      "bg": "#F7F6F3", "surface": "#FFFFFF", "surfaceRaised": "#FFFFFF", "control": "#EFEDE8",
      "border": "#DAD7D0", "ink": "#16171A", "inkDim": "#4A4D55", "inkFaint": "#62656D",
      "accent": "#C2410C", "onAccent": "#FFFFFF", "success": "#1B7F55", "warning": "#A15C00",
      "danger": "#C0283F", "shadow": "#1A1A1A"
    },
    "dark": {
      "bg": "#0C0D0F", "surface": "#16181C", "surfaceRaised": "#1D2025", "control": "#16181C",
      "border": "#2E3238", "ink": "#EDE9E0", "inkDim": "#B8B4AA", "inkFaint": "#9A968D",
      "accent": "#FF6B2C", "onAccent": "#0C0D0F", "success": "#3DDC97", "warning": "#FFB020",
      "danger": "#FF6B6B", "shadow": "#000000"
    }
  },
  "font": { "display": "Inter Tight", "body": "System", "mono": "Menlo" },
  "type": {
    "display":   { "font": "display", "size": 40, "lineHeight": 46, "weight": "700", "letterSpacing": -0.8, "maxScale": 1.3 },
    "title":     { "font": "display", "size": 28, "lineHeight": 34, "weight": "700", "letterSpacing": -0.4, "maxScale": 1.4 },
    "heading":   { "font": "display", "size": 20, "lineHeight": 26, "weight": "600", "letterSpacing": -0.2, "maxScale": 1.6 },
    "body":      { "font": "body", "size": 16, "lineHeight": 23, "weight": "400", "letterSpacing": 0, "maxScale": 2.0 },
    "secondary": { "font": "body", "size": 14, "lineHeight": 20, "weight": "400", "letterSpacing": 0, "maxScale": 2.0 },
    "meta":      { "font": "body", "size": 12, "lineHeight": 16, "weight": "600", "letterSpacing": 0.6, "maxScale": 1.6, "uppercase": true },
    "mono":      { "font": "mono", "size": 14, "lineHeight": 20, "weight": "500", "letterSpacing": 0, "maxScale": 1.6 }
  },
  "motion": {
    "duration": { "instant": 90, "fast": 140, "standard": 220, "screen": 320, "deliberate": 480, "ambient": 1400 },
    "easing": { "standard": [0.2, 0, 0, 1], "enter": [0.05, 0.7, 0.1, 1], "exit": [0.3, 0, 0.8, 0.15], "loop": [0.45, 0, 0.55, 1] },
    "spring": { "snappy": { "damping": 22, "stiffness": 320, "mass": 1 }, "gentle": { "damping": 20, "stiffness": 180, "mass": 1 }, "bouncy": { "damping": 12, "stiffness": 220, "mass": 1 } },
    "pressScale": 0.97
  },
  "elevation": { "none": {...}, "card": {...}, "raised": {...}, "overlay": {...} },
  "opacity": { "disabled": 0.45, "pressed": 0.12, "scrim": 0.45, "muted": 0.7 },
  "size": { "xs": 12, "sm": 14, "md": 16, "lg": 20, "xl": 28, "xxl": 40 },
  "space": { "xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32, "xxl": 48 },
  "radius": { "sm": 8, "md": 12, "lg": 20, "pill": 999 },
  "icon": { "glyph": "A" },
  "minTapTarget": 48
}
```

- `mode` is the fallback when the phone reports no preference (and the icon's palette).
- `maxScale` caps Dynamic Type per role (never below 1): body text must be allowed to
  grow a lot; a 40pt display line less so.
- `easing` values are cubic-bezier control points; `loop` must be symmetric (it runs
  the skeleton shimmer back and forth).
- A named `font` family (not `System`) must be embedded with the `expo-font` config
  plugin in the scaffold phase, or iOS silently falls back.
- The v1 shape (one flat `color` map) still works but locks the app to one mode.

Rules, all enforced by the validator, **in each mode**:
- `ink`, `inkDim` and `inkFaint` each clear **4.5:1** on `bg`, `surface`,
  `surfaceRaised` and `control`. `onAccent` clears 4.5:1 on `accent`.
- `accent` clears **3:1** on `bg` and `surface` (tab tint, focus ring, icons).
- `success` / `warning` / `danger` clear 3:1 on `bg` and `surface`; `danger` clears
  4.5:1 (error text uses it). They always ship with an icon or text too.
- Both palettes have exactly the same keys.

Validate:

```
python3 "$KIT/scripts/check_contrast.py" design/tokens.json
```

If it fails, adjust the failing colour's lightness (in the mode it names) until it
passes. **Don't drop the requirement.** Show the user the before/after only if the
change is visible.

Set `appbox.yaml` → `design.direction: <name>` and `progress.design: done`.
