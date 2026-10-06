#!/usr/bin/env python3
"""DESIGN.md: the design system in one file an agent reads before any UI work.

design/tokens.json stays the source of truth (the design flow writes it; the renderer
turns it into mobile/lib/tokens.ts). This script projects it into DESIGN.md at the repo
root, in the open DESIGN.md format from Google Stitch (Apache-2.0, see
THIRD_PARTY_NOTICES.md in the kit): YAML frontmatter with the home mode's palette, the
type roles, radius, spacing and a few component recipes, then the format's eight
sections in order (Overview, Colors, Typography, Layout, Elevation & Depth, Shapes,
Components, Do's and Don'ts), then what Stitch's format can't hold: Dark Mode, Motion,
Atmosphere, Iconography, an Agent Prompt Guide, and a hand-written Decisions log.

Only the frontmatter and the text between the generated markers belong to this script:

    <!-- design.md:generated:colors -->  ...  <!-- /design.md:generated:colors -->

Everything outside them is yours (the feel in your own words, the Decisions log) and
survives every regeneration. A generated block that goes missing is put back under its
heading (or appended as a new section, before Decisions).

    design_md.py                 write DESIGN.md from design/tokens.json
    design_md.py --check         exit 1 if DESIGN.md's generated parts differ from what
                                 design/tokens.json says (a hand edit, or a token change
                                 nobody regenerated). Prose outside the markers is free.
    --tokens PATH / --out PATH   defaults: design/tokens.json, DESIGN.md (run from root)

Exit codes: 0 ok, 1 drift, 2 usage. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GEN = "design.md:generated"
# (marker key, section heading) in document order. The first eight are Stitch's
# sections in Stitch's order; the rest are extra sections its consumers preserve.
SECTIONS = (
    ("overview", "Overview"),
    ("colors", "Colors"),
    ("typography", "Typography"),
    ("layout", "Layout"),
    ("elevation", "Elevation & Depth"),
    ("shapes", "Shapes"),
    ("components", "Components"),
    ("dos-donts", "Do's and Don'ts"),
    ("dark-mode", "Dark Mode"),
    ("motion", "Motion"),
    ("atmosphere", "Atmosphere"),
    ("iconography", "Iconography"),
    ("agent-guide", "Agent Prompt Guide"),
)
DECISIONS = "Decisions"
# The only top-level frontmatter keys Stitch's schema knows. Anything else is ours to
# keep in the body, never in the frontmatter.
STITCH_KEYS = (
    "version",
    "name",
    "description",
    "omitted",
    "colors",
    "typography",
    "rounded",
    "spacing",
    "components",
)
# tokens.json colour name -> Stitch's conventional token name, so Stitch tooling finds
# `primary` (its linter wants one) while the Colors table still names the code token.
STITCH_COLOR = {
    "bg": "background",
    "surface": "surface",
    "surfaceRaised": "surface-raised",
    "control": "surface-control",
    "border": "outline",
    "ink": "on-surface",
    "inkDim": "on-surface-variant",
    "inkFaint": "on-surface-faint",
    "accent": "primary",
    "onAccent": "on-primary",
    "success": "success",
    "warning": "warning",
    "danger": "error",
    "shadow": "shadow",
}
COLOR_ROLE = {
    "bg": "Screen background",
    "surface": "Sheets and grouped areas",
    "surfaceRaised": "Cards (borderless: tone, not lines, lifts them)",
    "control": "Fill for buttons, chips, fields",
    "border": "Hairlines and outlines (not text)",
    "ink": "Primary text",
    "inkDim": "Secondary text",
    "inkFaint": "Tertiary text: meta labels, units, placeholders",
    "accent": "The action colour: the primary button, links, selection",
    "onAccent": "Text and icons on an accent fill",
    "success": "Status icons, dots, borders (not text)",
    "warning": "Status icons, dots, borders (not text)",
    "danger": "Errors (safe as text)",
    "shadow": "Shadow colour",
}
RADIUS_USE = {
    "sm": "small inner pieces (a segmented thumb, a row's icon tile)",
    "md": "buttons, fields, list rows",
    "lg": "cards",
    "pill": "chips and round icon buttons",
}
MODES = ("light", "dark")


# ---------------------------------------------------------------- reading tokens


def palettes(tokens: dict) -> dict[str, dict]:
    """{mode: palette}. A v1 file has one flat palette; treat it as its own mode."""
    color = tokens.get("color") or {}
    if any(isinstance(v, dict) for v in color.values()):
        return {m: p for m, p in color.items() if isinstance(p, dict)}
    return {str(tokens.get("mode") or "light"): color} if color else {}


def home_mode(tokens: dict) -> str:
    pals = palettes(tokens)
    mode = tokens.get("mode")
    if mode in pals:
        return str(mode)
    return next(iter(pals), "dark")


def _num(v: object) -> str:
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _px(v: object) -> str:
    return f"{_num(v)}px"


def _kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def _stitch_color(name: str) -> str:
    return STITCH_COLOR.get(name, _kebab(name))


def _group(tokens: dict, key: str) -> dict:
    v = tokens.get(key)
    return v if isinstance(v, dict) else {}


# ---------------------------------------------------------------- frontmatter


def _yaml_key(k: str) -> str:
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k)


def _yaml_scalar(v: object) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return _num(v)
    return json.dumps(str(v))  # a JSON string is a valid YAML double-quoted scalar


def _yaml(d: dict, indent: int = 0) -> list[str]:
    out = []
    for k, v in d.items():
        pad = "  " * indent
        if isinstance(v, dict):
            if v:
                out.append(f"{pad}{_yaml_key(k)}:")
                out += _yaml(v, indent + 1)
        else:
            out.append(f"{pad}{_yaml_key(k)}: {_yaml_scalar(v)}")
    return out


def frontmatter_data(tokens: dict) -> dict:
    """Stitch's schema, projected from tokens.json. Only STITCH_KEYS at the top."""
    pals = palettes(tokens)
    mode = home_mode(tokens)
    pal = pals.get(mode, {})
    colors = {_stitch_color(k): v for k, v in pal.items() if isinstance(v, str)}
    fonts = _group(tokens, "font")
    typography = {}
    for role, t in _group(tokens, "type").items():
        if not isinstance(t, dict):
            continue
        entry: dict = {}
        fam = fonts.get(t.get("font"), t.get("font"))
        if isinstance(fam, str):
            entry["fontFamily"] = fam
        if "size" in t:
            entry["fontSize"] = _px(t["size"])
        if "weight" in t:
            try:
                entry["fontWeight"] = int(str(t["weight"]))
            except ValueError:
                entry["fontWeight"] = str(t["weight"])
        if "lineHeight" in t:
            entry["lineHeight"] = _px(t["lineHeight"])
        if "letterSpacing" in t:
            entry["letterSpacing"] = _px(t["letterSpacing"])
        typography[role] = entry
    rounded = {k: _px(v) for k, v in _group(tokens, "radius").items()}
    spacing = {k: _px(v) for k, v in _group(tokens, "space").items()}
    tap = tokens.get("minTapTarget", 48)
    space = _group(tokens, "space")

    groups = {"colors": colors, "typography": typography, "rounded": rounded}

    def recipe(**props: str | None) -> dict:
        """A Stitch component: "{group.key}" references (dropped when the key doesn't
        exist in this theme) and literal values (dropped when None)."""
        out = {}
        for prop, val in props.items():
            m = re.fullmatch(r"\{(\w+)\.([\w-]+)\}", val or "")
            if val is not None and (not m or m.group(2) in groups[m.group(1)]):
                out[prop] = val
        return out

    def pad(key: str) -> str | None:
        return _px(space[key]) if key in space else None

    components = {
        "button-primary": recipe(
            backgroundColor="{colors.primary}",
            textColor="{colors.on-primary}",
            typography="{typography.body}",
            rounded="{rounded.md}",
            padding=pad("lg"),
            height=_px(tap),
        ),
        "button-secondary": recipe(
            backgroundColor="{colors.surface-control}",
            textColor="{colors.on-surface}",
            typography="{typography.body}",
            rounded="{rounded.md}",
            padding=pad("lg"),
            height=_px(tap),
        ),
        "input": recipe(
            backgroundColor="{colors.surface-control}",
            textColor="{colors.on-surface}",
            typography="{typography.body}",
            rounded="{rounded.md}",
            padding=pad("md"),
            height=_px(tap),
        ),
        "chip": recipe(
            backgroundColor="{colors.surface-control}",
            textColor="{colors.on-surface}",
            typography="{typography.secondary}",
            rounded="{rounded.pill}",
            padding=pad("md"),
            height=_px(tap),
        ),
        "chip-selected": recipe(
            backgroundColor="{colors.primary}",
            textColor="{colors.on-primary}",
        ),
        "card": recipe(
            backgroundColor="{colors.surface-raised}",
            textColor="{colors.on-surface}",
            rounded="{rounded.lg}",
            padding=pad("lg"),
        ),
    }
    other = [m for m in pals if m != mode]
    desc = f"Generated from design/tokens.json. Frontmatter colours are the {mode} palette"
    desc += f"; the {', '.join(other)} palette is under Dark Mode." if other else "."
    data = {
        "version": "alpha",
        "name": str(tokens.get("name") or "custom"),
        "description": desc,
        "colors": colors,
        "typography": typography,
        "rounded": rounded,
        "spacing": spacing,
        "components": {k: v for k, v in components.items() if v},
    }
    assert set(data) <= set(STITCH_KEYS)
    return data


def frontmatter(tokens: dict) -> str:
    return "---\n" + "\n".join(_yaml(frontmatter_data(tokens))) + "\n---\n"


# ---------------------------------------------------------------- generated blocks


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(r) + " |" for r in rows),
    ]


def _overview(t: dict) -> list[str]:
    pals = palettes(t)
    mode = home_mode(t)
    other = [m for m in pals if m != mode]
    fonts = _group(t, "font")
    radius = _group(t, "radius")
    dur = _group(_group(t, "motion"), "duration")
    lines = [
        f"Theme **{t.get('name') or 'custom'}**. Home mode **{mode}**"
        + (
            f", with {' and '.join(other)} shipped too (the app follows the OS)."
            if other
            else " only (the app locks to it)."
        ),
    ]
    if fonts:
        lines.append(
            "Faces: " + ", ".join(f"{role} **{fam}**" for role, fam in fonts.items()) + "."
        )
    if "md" in radius:
        lines.append(f"Corners: `radius.md` {_px(radius['md'])} on buttons, fields and rows.")
    if "standard" in dur:
        lines.append(f"Motion: `motion.duration.standard` {_num(dur['standard'])}ms.")
    lines += [
        "",
        "Every value in this file comes from `design/tokens.json`. Code reads them through",
        "`mobile/lib/tokens.ts` (generated) and `useTheme()`, never as literals.",
    ]
    return lines


def _colors(t: dict) -> list[str]:
    mode = home_mode(t)
    pal = palettes(t).get(mode, {})
    if not pal:
        return ["No palette in `design/tokens.json` yet."]
    rows = [
        [f"`color.{k}`", f"`{_stitch_color(k)}`", f"`{v}`", COLOR_ROLE.get(k, "")]
        for k, v in pal.items()
        if isinstance(v, str)
    ]
    return [
        f"The {mode} palette (home mode). Frontmatter names follow Stitch's conventions;",
        "code uses the token name.",
        "",
        *_table(["Token", "DESIGN.md name", "Hex", "Use"], rows),
        "",
        "Text is the ink ramp `ink` → `inkDim` → `inkFaint`, plus `accent` and `danger`.",
        "Every text token clears WCAG AA (4.5:1) on every surface in both modes;",
        "`scripts/check_contrast.py` fails the build if one doesn't.",
    ]


def _typography(t: dict) -> list[str]:
    type_ = _group(t, "type")
    if not type_:
        return ["No type roles in `design/tokens.json`; the app derives them from `size`."]
    fonts = _group(t, "font")
    rows = []
    for role, r in type_.items():
        if not isinstance(r, dict):
            continue
        fam = fonts.get(r.get("font"), r.get("font", ""))
        rows.append(
            [
                f"`{role}`",
                str(fam),
                f"{_num(r.get('size', ''))}/{_num(r.get('lineHeight', ''))}",
                str(r.get("weight", "")),
                _num(r.get("letterSpacing", 0)),
                "yes" if r.get("uppercase") else "",
                f"{_num(r.get('maxScale', ''))}×",
            ]
        )
    return [
        'Set text with `<Text variant="role">`: it applies the face, size, weight, line',
        "height and the Dynamic Type cap.",
        "",
        *_table(["Role", "Face", "Size/line", "Weight", "Tracking", "Caps", "Max scale"], rows),
    ]


def _layout(t: dict) -> list[str]:
    space = _group(t, "space")
    tap = t.get("minTapTarget", 48)
    lines = []
    if space:
        lines += [
            *_table(["Token", "Value"], [[f"`space.{k}`", _px(v)] for k, v in space.items()]),
            "",
        ]
    lines += [
        f"Tap targets are at least {_px(tap)} (`minTapTarget`). Screens pad by `space.lg`",
        "and stack sections by `space.md` (`Screen`); one column on a phone, content",
        "inside the safe area.",
    ]
    return lines


def _elevation(t: dict) -> list[str]:
    elev = _group(t, "elevation")
    op = _group(t, "opacity")
    lines = [
        "Depth is tone first: `bg` → `surface` → `surfaceRaised`, each a step lighter (dark)",
        "or brighter (light). Shadows are soft and sparing.",
        "",
    ]
    if elev:
        rows = [
            [
                f"`elevation.{k}`",
                _num(v.get("elevation", "")),
                _num(v.get("shadowOpacity", "")),
                _num(v.get("shadowRadius", "")),
                _num(v.get("shadowOffsetY", "")),
            ]
            for k, v in elev.items()
            if isinstance(v, dict)
        ]
        lines += [*_table(["Level", "Android", "Opacity", "Blur", "Offset Y"], rows), ""]
    if op:
        lines.append(
            "Opacity: " + ", ".join(f"`opacity.{k}` {_num(v)}" for k, v in op.items()) + "."
        )
    return lines


def _shapes(t: dict) -> list[str]:
    radius = _group(t, "radius")
    if not radius:
        return ["No radius scale in `design/tokens.json`."]
    rows = [[f"`radius.{k}`", _px(v), RADIUS_USE.get(k, "")] for k, v in radius.items()]
    return [
        *_table(["Token", "Value", "Use"], rows),
        "",
        "One radius per kind of thing; never mix.",
    ]


def _components(t: dict) -> list[str]:
    tap = _px(t.get("minTapTarget", 48))
    return [
        "Build from `components/ui` (`mobile/components/ui/index.ts`); never restyle one",
        "inline. The recipes in the frontmatter, in words:",
        "",
        f"- **Button, primary:** `accent` fill, `onAccent` label, `radius.md`, {tap} tall.",
        "  One per screen, for the action the screen exists for.",
        "- **Button, secondary:** `control` fill, `border` outline, `ink` label.",
        "- **Field:** `control` fill, `border` outline that turns `accent` on focus and",
        "  `danger` when invalid; `inkFaint` placeholder.",
        "- **Chip:** pill, `control` fill; selected is `accent` with an `onAccent` label.",
        "- **Card:** `surfaceRaised`, `radius.lg`, `space.lg` padding, `elevation.card`.",
        "  Never a card inside a card.",
        "- **Every tap** goes through `PressableScale`: press scale, tint and a haptic.",
    ]


def _dos(t: dict) -> list[str]:
    tap = _px(t.get("minTapTarget", 48))
    return [
        "- Do read colours, type, space and radius from `useTheme()`; never a hex literal or",
        "  a raw `fontSize` in a screen.",
        "- Do keep one primary (accent) action per screen.",
        f"- Do keep every tap target at least {tap}, and label it for screen readers.",
        "- Do pair colour with a word or an icon; never meaning by colour alone.",
        "- Don't paint text in `success` or `warning`: they are for icons, dots and borders.",
        "- Don't let content or screens bounce: easing curves decelerate; only springs on",
        "  small elements overshoot.",
        "- Don't reach for the generic tells (overused fonts, pure-grey neutrals, the stock",
        "  AI violet, gradient text, emoji as icons): `docs/design/TASTE.md`.",
    ]


def _dark_mode(t: dict) -> list[str]:
    pals = palettes(t)
    present = [m for m in MODES if m in pals] + [m for m in pals if m not in MODES]
    if len(present) < 2:
        return [
            f"One palette only ({', '.join(present) or 'none'}): the app locks to it and",
            "ignores the OS setting.",
        ]
    names = list(dict.fromkeys(k for m in present for k in pals[m]))
    rows = [[f"`color.{k}`", *(f"`{pals[m].get(k, '')}`" for m in present)] for k in names]
    return [
        f"Both palettes ship; the home mode is **{home_mode(t)}**. The app follows the OS,",
        "with a System / Light / Dark override (`useThemePreference()`). Same token names",
        "in both, so a screen never branches on the mode.",
        "",
        *_table(["Token", *present], rows),
    ]


def _motion(t: dict) -> list[str]:
    m = _group(t, "motion")
    if not m:
        return ["No motion tokens; `lib/motion.ts` uses its defaults."]
    lines = ["Through `lib/motion.ts` only; every preset honours reduce motion.", ""]
    dur = _group(m, "duration")
    if dur:
        lines += [
            "Durations: " + ", ".join(f"`{k}` {_num(v)}ms" for k, v in dur.items()) + ".",
        ]
    ease = _group(m, "easing")
    if ease:
        lines.append(
            "Easing (cubic-bezier): "
            + ", ".join(
                f"`{k}` ({', '.join(_num(x) for x in v)})"
                for k, v in ease.items()
                if isinstance(v, list)
            )
            + "."
        )
    spring = _group(m, "spring")
    if spring:
        lines.append(
            "Springs: "
            + ", ".join(
                f"`{k}` (damping {_num(v.get('damping', ''))}, stiffness "
                f"{_num(v.get('stiffness', ''))})"
                for k, v in spring.items()
                if isinstance(v, dict)
            )
            + "."
        )
    if "pressScale" in m:
        lines.append(f"Press scale: {_num(m['pressScale'])}.")
    return lines


def _atmosphere(t: dict) -> list[str]:
    a = _group(t, "atmosphere")
    if not a:
        return ["None recorded: screens paint flat `bg`."]
    knobs = ", ".join(
        f"{k} **{_num(a[k])}**" for k in ("mode", "intensity", "grain", "surface") if k in a
    )
    lines = [f"The light behind each screen, as chosen in the prototype: {knobs}.", ""]
    color = _group(a, "color")
    rows = []
    for mode, c in color.items():
        if isinstance(c, dict):
            rows.append(
                [mode]
                + [f"`{c[k]}`" if k in c else "" for k in ("light1", "light2")]
                + [_num(c.get("alpha", ""))]
            )
    if rows:
        lines += [*_table(["Mode", "Light 1", "Light 2", "Peak alpha"], rows), ""]
    lines.append(
        "The alpha is capped so the ink ramp still clears AA where the light is brightest."
    )
    return lines


def _iconography(t: dict) -> list[str]:
    glyph = _group(t, "icon").get("glyph")
    return [
        "One icon component, `Icon` (`components/ui/Icon.tsx`): an SF Symbol name (`sf`) on",
        "iOS and a Material name (`md`) on Android and web. The names each screen uses are",
        "in `docs/product/SCREENS.md` → Icons. Never emoji or text glyphs as icons.",
        "Decorative icons are hidden from screen readers; an icon-only button has a label.",
        "",
        (
            f"App icon glyph: **{glyph}**."
            if glyph
            else "App icon glyph: the first letter of the app name (set `icon.glyph` to change it)."
        ),
    ]


def _agent_guide(t: dict) -> list[str]:
    mode = home_mode(t)
    pal = palettes(t).get(mode, {})
    acc = pal.get("accent")
    return [
        "Before any UI work, read this file top to bottom, then build with these rules:",
        "",
        "1. Use `components/ui` first; compose before you create.",
        "2. Colours, type, space, radius, motion: tokens through `useTheme()` and",
        "   `lib/motion.ts`, never literals. If a token is missing, say so; don't invent one.",
        "3. Design for both modes at once"
        + (f"; the home mode is {mode} and the accent there is `{acc}`." if acc else "."),
        "4. Want a different colour, face or radius? That is a design change: re-run the",
        "   design flow (prototype → freeze) or edit `design/tokens.json` with the owner's",
        "   yes, then regenerate. Never edit this file's generated blocks or `lib/tokens.ts`",
        "   by hand: `python3 scripts/design_md.py --check` fails CI on it.",
        "",
        'A prompt that works: "Build the <screen> from docs/product/SCREENS.md using',
        "components/ui and the tokens in DESIGN.md; one primary action; skeleton while",
        'loading; an empty state with one next step."',
    ]


BUILDERS = {
    "overview": _overview,
    "colors": _colors,
    "typography": _typography,
    "layout": _layout,
    "elevation": _elevation,
    "shapes": _shapes,
    "components": _components,
    "dos-donts": _dos,
    "dark-mode": _dark_mode,
    "motion": _motion,
    "atmosphere": _atmosphere,
    "iconography": _iconography,
    "agent-guide": _agent_guide,
}


def block(key: str, tokens: dict) -> str:
    body = "\n".join(BUILDERS[key](tokens)).rstrip()
    return f"<!-- {GEN}:{key} -->\n{body}\n<!-- /{GEN}:{key} -->"


def _block_re(key: str) -> re.Pattern[str]:
    k = re.escape(key)
    return re.compile(rf"<!-- {re.escape(GEN)}:{k} -->\n.*?\n<!-- /{re.escape(GEN)}:{k} -->", re.S)


# ---------------------------------------------------------------- the document


def fresh(tokens: dict) -> str:
    """A new DESIGN.md: generated blocks plus the places your own words go."""
    parts = [
        frontmatter(tokens),
        "<!-- Generated from design/tokens.json by scripts/design_md.py. The frontmatter",
        "     and the text between design.md:generated markers are rewritten on every run;",
        "     anything you write outside them is kept. Change the design through the design",
        "     flow (or design/tokens.json), then regenerate. Never edit a generated block. -->",
        "",
        f"# {tokens.get('name') or 'Custom'} design system",
        "",
    ]
    for key, heading in SECTIONS:
        parts += [f"## {heading}", "", block(key, tokens), ""]
        if key == "overview":
            parts += [
                "<!-- Your words, kept on every regeneration: who the app is for, how it",
                "     should feel (calm or lively, dense or airy), and why this palette. -->",
                "",
            ]
    parts += [
        f"## {DECISIONS}",
        "",
        "Design calls and their reasons, newest first. Hand-written; regeneration never",
        "touches this section.",
        "",
    ]
    return "\n".join(parts)


def _split_frontmatter(text: str) -> tuple[str | None, str]:
    m = re.match(r"---\n.*?\n---\n", text, re.S)
    return (m.group(0), text[m.end() :]) if m else (None, text)


def update(text: str | None, tokens: dict) -> str:
    """Regenerate the frontmatter and every generated block; keep everything else."""
    if not text:
        return fresh(tokens)
    _, body = _split_frontmatter(text)
    for key, heading in SECTIONS:
        new = block(key, tokens)
        pat = _block_re(key)
        if pat.search(body):
            body = pat.sub(lambda _m, new=new: new, body, count=1)
            continue
        head = re.search(rf"^## {re.escape(heading)}[ \t]*\n", body, re.M)
        if head:
            body = body[: head.end()] + "\n" + new + "\n" + body[head.end() :]
            continue
        section = f"## {heading}\n\n{new}\n\n"
        dec = re.search(rf"^## {re.escape(DECISIONS)}[ \t]*$", body, re.M)
        if dec:
            body = body[: dec.start()] + section + body[dec.start() :]
        else:
            body = body.rstrip("\n") + "\n\n" + section
    return frontmatter(tokens) + (body if body.startswith("\n") else "\n" + body)


def drift(text: str, tokens: dict, name: str = "DESIGN.md") -> list[str]:
    """What in `text` no longer matches tokens. Prose outside the markers is ignored."""
    errs = []
    fm, body = _split_frontmatter(text)
    if fm is None:
        errs.append(f"{name}: no frontmatter (the --- block of tokens at the top)")
    elif fm != frontmatter(tokens):
        errs.append(f"{name}: frontmatter differs from design/tokens.json")
    for key, _ in SECTIONS:
        found = _block_re(key).findall(body)
        if not found:
            errs.append(f"{name}: generated block '{key}' is missing")
        elif len(found) > 1:
            errs.append(f"{name}: generated block '{key}' appears {len(found)} times")
        elif found[0] != block(key, tokens):
            errs.append(f"{name}: generated block '{key}' differs from design/tokens.json")
    return errs


def write(path: Path, tokens: dict) -> bool:
    """Write or refresh DESIGN.md at path. True when the file changed."""
    old = path.read_text(encoding="utf-8") if path.is_file() else None
    new = update(old, tokens)
    if new == old:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--tokens", default="design/tokens.json")
    ap.add_argument("--out", default="DESIGN.md")
    ap.add_argument("--check", action="store_true", help="exit 1 if DESIGN.md has drifted")
    a = ap.parse_args(argv)
    try:
        tokens = json.loads(Path(a.tokens).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"{a.tokens}: cannot read tokens: {e}")
        return 2
    if not isinstance(tokens, dict):
        print(f"{a.tokens}: tokens must be a JSON object")
        return 2
    out = Path(a.out)
    if a.check:
        if not out.is_file():
            print(f"{a.out}: missing. Generate it: python3 scripts/design_md.py")
            return 1
        errs = drift(out.read_text(encoding="utf-8"), tokens, a.out)
        for e in errs:
            print(e)
        if errs:
            print(
                f"DESIGN.md check FAILED: {len(errs)} generated part(s) drifted. Change the "
                "design in design/tokens.json (the design flow), never in DESIGN.md, then run "
                "python3 scripts/design_md.py (your prose outside the markers is kept)."
            )
            return 1
        print("DESIGN.md check passed (frontmatter and generated blocks match design/tokens.json).")
        return 0
    print(f"{'wrote' if write(out, tokens) else 'unchanged:'} {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
