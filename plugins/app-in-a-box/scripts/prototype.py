#!/usr/bin/env python3
"""Render, lint and freeze design/prototype.json: the clickable prototype of every v1 screen.

Agents write a small JSON spec; this script turns it into ONE self-contained HTML file
from the component library in scripts/proto/ (so the model never hand-writes markup
and a variant change re-renders for free), lints it for the mechanical taste rules,
and, once the user has clicked around and chosen, freezes the choices into the files
the scaffold builds from.

    prototype.py render <spec> <out.html>
    prototype.py check  <spec>
    prototype.py freeze <spec> <choices.json> --target <repo root>
    prototype.py fonts  [--library fonts.json] [--skill design-directions/SKILL.md]

render   one HTML file: phone frame (390x844), working navigation, tabs, sheets,
         toasts, per-screen states, and a control panel (direction, type pairing,
         light/dark, density, temperature, tone, per-screen variant, feature
         toggles, screen map, annotations, "Copy my choices"). Inline CSS/JS;
         Google Fonts only.
         Refuses a malformed spec (schema errors); other lints print as warnings
         so a work-in-progress spec can still be clicked through.
check    prints one line per problem and exits 1 on any: schema errors, dangling
         go/sheet targets, >1 primary button per variant, a primary button behind a
         feature toggle, unreachable screens or
         sheets, placeholder text (lorem, TODO, xxx...), a list with no empty state
         on its screen, a direction failing check_contrast.py, >5 tabs, a feature
         no block references.
freeze   takes the JSON the prototype's "Copy my choices" button emits,
         {direction, mode, density, temperature, tone, variants: {screen: variant},
         features: {id: bool}, atmosphere: {mode, intensity, grain, surface},
         font: {display, body}}, and writes under --target:
           design/tokens.json       the chosen direction, density + temperature applied,
                                    the chosen type pairing (if any) in `font`, plus
                                    atmosphere (lights, colours, capped alpha)
           docs/product/SCREENS.md  per screen: chosen variant -> components/ui, nav
                                    graph, states, features in/out of v1
           design/choices.json      every selection, resolved (no gaps)
fonts    checks the type library (scripts/proto/fonts.json): every family OFL-1.1 with
         no Reserved Font Name, none on check_design.py's overused list, every pairing
         made of listed families suited to their roles, and the design-directions
         archetype table naming only listed (or built-in) families.

A direction's `tokens` is a tokens v2 object. Its `color` must be complete (light AND
dark), unless the direction gives a `palette` instead: {"accent": "#RRGGBB",
"neutralHue": 0..360, "neutralChroma": 4..24} (only accent is required), from which
scripts/palette.py derives both modes contrast-safe by construction; any keys
`tokens.color` still sets override the derived ones. Any other top-level key it leaves
out (type, space, elevation...) is taken from template/design/tokens.json, so the
frozen file always has every key.

Exit codes: 0 ok, 1 problems found / refused, 2 usage. Standard library only.
"""

from __future__ import annotations

import argparse
import colorsys
import copy
import hashlib
import html
import json
import os
import tempfile
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
PROTO = HERE / "proto"
TEMPLATE_TOKENS = KIT / "template" / "design" / "tokens.json"
sys.path.insert(0, str(HERE))
import check_contrast as cc  # noqa: E402  (sibling module; shared contrast gate)
import check_design as dc  # noqa: E402  (sibling module; shared design-tells gate)
import palette as pl  # noqa: E402  (sibling module; HCT palette from one accent)

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
FONT_RE = re.compile(r"^[A-Za-z0-9 ]{1,40}$")
# Built in on the phone, so never loaded. Must equal BUILT_IN_FONTS in the template's
# mobile/lib/fonts.ts (selftest-checked); any other family is loaded from Google Fonts
# here and registered per weight in the app.
SYSTEM_FONTS = {"System", "SF Pro", "Roboto"}
MONO_FONTS = {"Menlo", "SF Mono", "monospace"}
SANS_STACK = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'
MONO_STACK = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace'

MODES = ("light", "dark")
TONES = ("calm", "playful")
ICON_STYLES = ("rounded", "sharp")
DENSITY = {"compact": 0.75, "regular": 1.0, "airy": 1.25}
# One table drives both the prototype's CSS and freeze, so what you click is what ships.
TEMPERATURE = {
    "calm": {
        "motion": 1.15,
        "radius": 1.0,
        "press": 0.6,
        "saturation": 0.9,
        "enter": None,
        "damping": 1.15,  # springs settle without overshoot
    },
    "lively": {
        "motion": 0.85,
        "radius": 1.25,
        "press": 1.6,
        "saturation": 1.15,
        # Quicker to arrive, never past the mark: content and screens don't bounce
        # (TASTE.md, Motion). Overshoot lives only in the small-element springs below.
        "enter": [0.16, 1, 0.3, 1],
        "damping": 0.75,  # presses and selections overshoot a little
    },
}
# Atmosphere: the light the app sits in, and its surfaces. A direction may set its
# default in tokens.atmosphere; the founder turns the knobs in the panel; the result is
# frozen into design/tokens.json -> atmosphere like every other choice.
ATMO_MODES = ("none", "glow", "field")  # field = WebGL, falls back to glow without it
ATMO_INTENSITY = {"low": 0.4, "medium": 0.62, "high": 0.85}  # peak alpha of each light
ATMO_SURFACES = ("solid", "glass")
ATMO_DEFAULT = {"mode": "glow", "intensity": "medium", "grain": True, "surface": "solid"}
ATMO_KEYS = {"mode": ATMO_MODES, "intensity": tuple(ATMO_INTENSITY), "surface": ATMO_SURFACES}
# Each light is the accent's hue (and a neighbour's), saturated, at the brightest
# lightness that keeps every ink at AA over the lit ground and over a glass card on it.
# A colour that exists in no token file can't be checked by a token gate, so the
# renderer composites the field and checks it here instead (atmo_lights).
# Two lights, as fractions of the phone: (centre x, centre y, radius x, radius y). The
# first crowns the top edge, the second rises from the lower right; ATMO_DRIFT is the
# far end of their slow drift (dx, dy, scale). phone.css draws exactly this geometry
# from the --atmo-l* variables render() writes.
ATMO_LIGHTS = ((0.18, -0.06, 0.78, 0.44), (1.02, 0.74, 0.70, 0.40))
ATMO_DRIFT = (-0.03, 0.025, 1.06)
GLASS_FILL = {"light": 0.78, "dark": 0.70}  # glass card = surfaceRaised at this alpha
INK_AA = 4.5
BUTTON_STYLES = ("primary", "secondary", "ghost")
MAX_TABS = 5

# type -> (required fields, optional fields). Every block may also carry feature/note.
BLOCKS = {
    "header": ({"title"}, {"eyebrow", "subtitle"}),
    "text": ({"body"}, {"style"}),
    "list": ({"items"}, {"title"}),
    "card": ({"title"}, {"eyebrow", "body", "icon", "action"}),
    "button": ({"label", "style"}, {"icon", "action"}),
    "chips": ({"options"}, {"label", "selected"}),
    "segmented": ({"options"}, {"label", "selected"}),
    "input": ({"label"}, {"placeholder", "value"}),
    "stat": ({"label", "value"}, {"hint", "icon"}),
    "progress": ({"label", "value"}, {"hint"}),
    "empty": ({"title", "body"}, {"icon", "action"}),
    "image": (set(), {"label", "ratio"}),
    "divider": (set(), {"label"}),
    "toast": ({"text"}, set()),
}
COMMON = {"type", "feature", "note"}
ITEM_FIELDS = ({"title"}, {"meta", "trailing", "icon", "action"})
STRING_FIELDS = {
    "title",
    "eyebrow",
    "subtitle",
    "body",
    "label",
    "placeholder",
    "value",
    "hint",
    "text",
    "meta",
    "trailing",
}
# What each block becomes in the generated app (template/mobile/components/ui).
COMPONENTS = {  # every name here is an export of the template's components/ui (selftest)
    "header": "Title + Body",
    "text": "Body",
    "list": "Card + ListRow",
    "card": "Card",
    "button": "Button",
    "chips": "Chip",
    "segmented": "SegmentedControl",
    "input": "Field",
    "stat": "StatCard",
    "progress": "ProgressBar",
    "empty": "EmptyState",
    "image": "Media",
    "divider": "Section",
    "toast": "useToast",
}
# Emoji used as UI (icons, bullets, headings) is a tell; the kit's icon set does that job.
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")
LABEL_KEYS = ("title", "label", "eyebrow")  # copy that names or heads something
MAX_EYEBROWS = 1  # per block list: a label over every heading is a template tell
MAX_CARD_RUN = 3  # consecutive cards: a fourth makes a wall of equal cards
PLACEHOLDER_RE = re.compile(
    r"(?i:\blorem\b|\bipsum\b|dolor sit amet)|\bTODO\b|\bFIXME\b|\bTBD\b|(?i:\bx{3,}\b)"
)
NON_COPY_KEYS = {
    "id",
    "type",
    "style",
    "go",
    "sheet",
    "icon",
    "icons",
    "feature",
    "screen",
    "tokens",
    "_comment",
    "ratio",
    "back",
    "selected",
    "default",
    "version",
}


# ---------------------------------------------------------------- loading + helpers


def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def icon_names() -> set[str]:
    return set(load_json(str(PROTO / "icons.json"))["icons"])


def icon_native() -> dict[str, list[str]]:
    """Prototype icon name -> [SF Symbol, Material Symbol] for the app's <Icon sf md>."""
    return load_json(str(PROTO / "icons.json"))["native"]


def _bad_icon(where: str, name, icons: set) -> str:
    return f"{where}: {name!r} is not in the icon set ({', '.join(sorted(icons))})"


CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _one_line(v) -> bool:
    return isinstance(v, str) and bool(v.strip()) and not CONTROL_RE.search(v)


def is_string(v) -> bool:
    """A visible string: plain, or {"calm": ..., "playful": ...} for the tone toggle.
    One line, no control characters: a newline in a title would forge a heading in
    SCREENS.md, which the scaffold agent reads as its spec."""
    if isinstance(v, str):
        return _one_line(v)
    return isinstance(v, dict) and set(v) == set(TONES) and all(_one_line(v[t]) for t in TONES)


def tone(v, t: str = "calm") -> str:
    return v.get(t, "") if isinstance(v, dict) else str(v)


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "color":
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def merged_tokens(direction: dict) -> dict:
    """The direction's tokens over the template's (colour is never inherited). A
    `palette` derives the colours; keys the direction's own `color` sets win."""
    base = load_json(str(TEMPLATE_TOKENS))
    base.pop("color", None)
    base.pop("$schema", None)
    out = deep_merge(base, direction.get("tokens") or {})
    src = direction.get("palette")
    if isinstance(src, dict) and not palette_errors(src):
        derived = pl.derive_palette(
            src["accent"], src.get("neutralHue"), src.get("neutralChroma", pl.NEUTRAL_CHROMA)
        )
        own = out.get("color") if isinstance(out.get("color"), dict) else {}
        out["color"] = {
            m: {**derived[m], **(own[m] if isinstance(own.get(m), dict) else {})} for m in MODES
        }
    return out


def palette_errors(src) -> list[str]:
    """What's wrong with a direction's `palette` (empty when it can be derived)."""
    if not isinstance(src, dict):
        return ["must be an object: {accent, neutralHue?, neutralChroma?}"]
    errs = [f"unknown key {k!r}" for k in sorted(src) if k not in ("accent", "neutralHue", "neutralChroma")]
    if not (isinstance(src.get("accent"), str) and cc.HEX.match(src["accent"])):
        errs.append("accent: must be #RRGGBB")
    nh = src.get("neutralHue")
    if nh is not None and not (_is_num(nh) and 0 <= nh <= 360):
        errs.append("neutralHue: must be a number of degrees in 0..360")
    lo, hi = pl.NEUTRAL_CHROMA_RANGE
    nc = src.get("neutralChroma")
    if nc is not None and not (_is_num(nc) and lo <= nc <= hi):
        errs.append(f"neutralChroma: must be a number in {lo:g}..{hi:g} (lower rounds to pure grey)")
    return errs


def block_lists(spec: dict):
    """Yield (where, owner, blocks) for every block list: variants, states, sheets."""
    for s in spec.get("screens") or []:
        if not isinstance(s, dict):
            continue
        sid = s.get("id", "?")
        for v in s.get("variants") or []:
            if isinstance(v, dict):
                yield (
                    f"screens[{sid}].variants[{v.get('id', '?')}]",
                    ("screen", sid),
                    v.get("blocks") or [],
                )
        states = s.get("states") or {}
        if isinstance(states, dict):
            for name, blocks in states.items():
                yield (
                    f"screens[{sid}].states.{name}",
                    ("screen", sid),
                    blocks if isinstance(blocks, list) else [],
                )
    for sh in spec.get("sheets") or []:
        if isinstance(sh, dict):
            yield (
                f"sheets[{sh.get('id', '?')}]",
                ("sheet", sh.get("id", "?")),
                sh.get("blocks") or [],
            )


def actions_in(block: dict):
    """Every action a block can fire (its own, its list rows', its empty CTA)."""
    if not isinstance(block, dict):
        return
    if isinstance(block.get("action"), dict):
        yield block["action"]
    for item in block.get("items") or []:
        if isinstance(item, dict) and isinstance(item.get("action"), dict):
            yield item["action"]


# ---------------------------------------------------------------- check


def _check_action(p: list, where: str, a, needs_label: bool) -> None:
    if not isinstance(a, dict):
        p.append(f"{where}.action: must be an object")
        return
    kinds = [k for k in ("go", "sheet", "back", "toast") if k in a]
    extra = set(a) - {"go", "sheet", "back", "toast", "label"}
    if len(kinds) != 1:
        p.append(f"{where}.action: needs exactly one of go/sheet/back/toast, got {sorted(a)}")
    if extra:
        p.append(f"{where}.action: unknown keys {sorted(extra)}")
    for k in ("go", "sheet"):
        if k in a and not (isinstance(a[k], str) and ID_RE.match(a[k])):
            p.append(f"{where}.action.{k}: must be a screen/sheet id")
    if "back" in a and a["back"] is not True:
        p.append(f"{where}.action.back: must be true")
    if "toast" in a and not is_string(a["toast"]):
        p.append(f"{where}.action.toast: must be a string or {{calm, playful}}")
    if needs_label and not is_string(a.get("label")):
        p.append(f"{where}.action.label: an empty state's action needs a label")


def _check_block(p: list, where: str, b, features: set, icons: set) -> None:
    if not isinstance(b, dict):
        p.append(f"{where}: block must be an object")
        return
    t = b.get("type")
    if t not in BLOCKS:
        p.append(f"{where}: unknown block type {t!r} (have: {', '.join(BLOCKS)})")
        return
    req, opt = BLOCKS[t]
    for k in sorted(req - set(b)):
        p.append(f"{where}: {t} block is missing {k!r}")
    for k in sorted(set(b) - req - opt - COMMON):
        p.append(f"{where}: {t} block has unknown field {k!r}")
    for k in STRING_FIELDS & set(b):
        if k == "value" and t == "progress":
            continue
        if not is_string(b[k]):
            p.append(f"{where}.{k}: must be a non-empty string or {{calm, playful}}")
    if "feature" in b and b["feature"] not in features:
        p.append(f"{where}.feature: {b['feature']!r} is not a defined feature")
    if "icon" in b and b["icon"] not in icons:
        p.append(_bad_icon(f"{where}.icon", b["icon"], icons))
    if t == "button" and b.get("style") not in BUTTON_STYLES:
        p.append(f"{where}.style: must be one of {', '.join(BUTTON_STYLES)}")
    if t in ("chips", "segmented"):
        opts = b.get("options")
        if not (isinstance(opts, list) and len(opts) >= 2 and all(is_string(o) for o in opts)):
            p.append(f"{where}.options: needs 2+ strings")
        elif "selected" in b and not (
            isinstance(b["selected"], int) and 0 <= b["selected"] < len(opts)
        ):
            p.append(f"{where}.selected: must index into options")
    if t == "progress" and not (isinstance(b.get("value"), (int, float)) and 0 <= b["value"] <= 1):
        p.append(f"{where}.value: progress value must be a number in 0..1")
    if t == "text" and b.get("style") not in (None, "body", "secondary"):
        p.append(f"{where}.style: text style is body or secondary")
    if t == "image" and "ratio" in b and not re.fullmatch(r"\d+:\d+", str(b["ratio"])):
        p.append(f"{where}.ratio: use W:H, e.g. 16:9")
    if t == "list":
        items = b.get("items")
        if not (isinstance(items, list) and items):
            p.append(f"{where}.items: a list needs at least one row (its empty state covers zero)")
        else:
            for i, it in enumerate(items):
                iw = f"{where}.items[{i}]"
                if not isinstance(it, dict):
                    p.append(f"{iw}: must be an object")
                    continue
                for k in sorted(ITEM_FIELDS[0] - set(it)):
                    p.append(f"{iw}: row is missing {k!r}")
                for k in sorted(set(it) - ITEM_FIELDS[0] - ITEM_FIELDS[1]):
                    p.append(f"{iw}: row has unknown field {k!r}")
                for k in ("title", "meta", "trailing"):
                    if k in it and not is_string(it[k]):
                        p.append(f"{iw}.{k}: must be a non-empty string or {{calm, playful}}")
                if "icon" in it and it["icon"] not in icons:
                    p.append(_bad_icon(f"{iw}.icon", it["icon"], icons))
                if "action" in it:
                    _check_action(p, iw, it["action"], False)
    if "action" in b:
        _check_action(p, where, b["action"], t == "empty")


def _control_chars(v, where: str, p: list) -> None:
    if isinstance(v, str):
        if CONTROL_RE.search(v):
            p.append(f"{where}: must be one line (no newlines or control characters)")
    elif isinstance(v, dict):
        for k, x in v.items():
            _control_chars(x, f"{where}.{k}", p)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _control_chars(x, f"{where}[{i}]", p)


def _schema(spec: dict, p: list) -> None:
    icons = icon_names()
    _control_chars(spec, "spec", p)
    if spec.get("version") != 1:
        p.append("version: must be 1")
    app = spec.get("app")
    if not (isinstance(app, dict) and is_string(app.get("name"))):
        p.append("app.name: required")
    dirs = spec.get("directions")
    if not (isinstance(dirs, list) and dirs):
        p.append("directions: needs at least one direction")
        dirs = []
    seen = set()
    for i, d in enumerate(dirs):
        w = f"directions[{i}]"
        if not isinstance(d, dict):
            p.append(f"{w}: must be an object")
            continue
        did = d.get("id")
        if not (isinstance(did, str) and ID_RE.match(did)):
            p.append(f"{w}.id: must be a lowercase id")
        elif did in seen:
            p.append(f"{w}.id: duplicate {did!r}")
        seen.add(did)
        for k in ("label", "why"):
            if not is_string(d.get(k)):
                p.append(f"{w}.{k}: required")
        if d.get("icons") not in ICON_STYLES:
            p.append(f"{w}.icons: must be one of {', '.join(ICON_STYLES)}")
        tok = d.get("tokens")
        if not isinstance(tok, dict):
            p.append(f"{w}.tokens: must be a tokens v2 object")
            continue
        col = tok.get("color")
        derived = "palette" in d
        if derived:
            p.extend(f"{w}.palette: {e}" for e in palette_errors(d["palette"]))
        if derived and col is not None and not (
            isinstance(col, dict) and set(col) <= set(MODES) and all(isinstance(v, dict) for v in col.values())
        ):
            p.append(f"{w}.tokens.color: with a palette, may only override keys in color.light / color.dark")
        elif not derived and not (
            isinstance(col, dict) and all(isinstance(col.get(m), dict) for m in MODES)
        ):
            p.append(f"{w}.tokens.color: needs both color.light and color.dark (tokens v2), or a palette")
        else:
            for m in MODES:
                if not isinstance((col or {}).get(m), dict):
                    continue
                for k in () if derived else cc.REQUIRED:
                    if k not in col[m]:
                        p.append(f"{w}.tokens.color.{m}.{k}: required")
                for k, val in col[m].items():
                    if not (isinstance(k, str) and TOKEN_KEY_RE.fullmatch(k)):
                        p.append(f"{w}.tokens.color.{m}: bad key {k!r}")
                    elif not (isinstance(val, str) and cc.HEX.match(val)):
                        p.append(f"{w}.tokens.color.{m}.{k}: must be #RRGGBB")
        for role, fam in (tok.get("font") or {}).items():
            if not (isinstance(fam, str) and FONT_RE.match(fam)):
                p.append(f"{w}.tokens.font.{role}: must be a plain family name")
        _token_values(merged_tokens(d), f"{w}.tokens", p)
    features = spec.get("features", [])
    if not isinstance(features, list):
        p.append("features: must be a list")
        features = []
    fids = set()
    for i, f in enumerate(features):
        w = f"features[{i}]"
        if not (isinstance(f, dict) and isinstance(f.get("id"), str) and ID_RE.match(f["id"])):
            p.append(f"{w}.id: must be a lowercase id")
            continue
        if f["id"] in fids:
            p.append(f"{w}.id: duplicate {f['id']!r}")
        fids.add(f["id"])
        if not is_string(f.get("label")):
            p.append(f"{w}.label: required")
        if not isinstance(f.get("default"), bool):
            p.append(f"{w}.default: must be true or false")
    screens = spec.get("screens")
    if not (isinstance(screens, list) and screens):
        p.append("screens: needs at least one screen")
        screens = []
    sids = set()
    for i, s in enumerate(screens):
        if not isinstance(s, dict):
            p.append(f"screens[{i}]: must be an object")
            continue
        sid = s.get("id")
        w = f"screens[{sid if isinstance(sid, str) else i}]"
        if not (isinstance(sid, str) and ID_RE.match(sid)):
            p.append(f"{w}.id: must be a lowercase id")
        elif sid in sids:
            p.append(f"{w}.id: duplicate screen id")
        sids.add(sid)
        if not is_string(s.get("title")):
            p.append(f"{w}.title: required")
        variants = s.get("variants")
        if not (isinstance(variants, list) and variants):
            p.append(f"{w}.variants: needs at least one variant")
            continue
        vids = set()
        for j, v in enumerate(variants):
            vw = f"{w}.variants[{j}]"
            if not (isinstance(v, dict) and isinstance(v.get("id"), str) and ID_RE.match(v["id"])):
                p.append(f"{vw}.id: must be a lowercase id")
                continue
            if v["id"] in vids:
                p.append(f"{vw}.id: duplicate variant id {v['id']!r}")
            vids.add(v["id"])
            if not is_string(v.get("label")):
                p.append(f"{w}.variants[{v['id']}].label: required")
            if not (isinstance(v.get("blocks"), list) and v["blocks"]):
                p.append(f"{w}.variants[{v['id']}].blocks: needs at least one block")
        states = s.get("states", {})
        if not isinstance(states, dict) or set(states) - {"empty"}:
            p.append(f"{w}.states: only an `empty` state is supported")
        elif "empty" in states and not (isinstance(states["empty"], list) and states["empty"]):
            p.append(f"{w}.states.empty: must be a non-empty block list")
    sheets = spec.get("sheets", [])
    if not isinstance(sheets, list):
        p.append("sheets: must be a list")
        sheets = []
    shids = set()
    for i, sh in enumerate(sheets):
        if not (isinstance(sh, dict) and isinstance(sh.get("id"), str) and ID_RE.match(sh["id"])):
            p.append(f"sheets[{i}].id: must be a lowercase id")
            continue
        if sh["id"] in shids or sh["id"] in sids:
            p.append(
                f"sheets[{sh['id']}].id: duplicate id (sheet and screen ids share one namespace)"
            )
        shids.add(sh["id"])
        if not is_string(sh.get("title")):
            p.append(f"sheets[{sh['id']}].title: required")
        if not (isinstance(sh.get("blocks"), list) and sh["blocks"]):
            p.append(f"sheets[{sh['id']}].blocks: needs at least one block")
    tabs = spec.get("tabs", [])
    if not isinstance(tabs, list):
        p.append("tabs: must be a list")
        tabs = []
    for i, tb in enumerate(tabs):
        w = f"tabs[{i}]"
        if not isinstance(tb, dict):
            p.append(f"{w}: must be an object")
            continue
        if tb.get("screen") not in sids:
            p.append(f"{w}.screen: dangling target {tb.get('screen')!r} (no such screen)")
        if not is_string(tb.get("label")):
            p.append(f"{w}.label: required")
        if tb.get("icon") not in icons:
            p.append(_bad_icon(f"{w}.icon", tb.get("icon"), icons))
    d = spec.get("defaults")
    if not isinstance(d, dict):
        p.append("defaults: required")
    else:
        if d.get("direction") not in seen:
            p.append(f"defaults.direction: {d.get('direction')!r} is not a direction id")
        for key, allowed in (
            ("mode", MODES),
            ("density", tuple(DENSITY)),
            ("temperature", tuple(TEMPERATURE)),
            ("tone", TONES),
        ):
            if d.get(key) not in allowed:
                p.append(f"defaults.{key}: must be one of {', '.join(allowed)}")
    for where, _owner, blocks in block_lists(spec):
        for k, b in enumerate(blocks):
            _check_block(p, f"{where}.blocks[{k}]", b, fids, icons)


def _walk_copy(node, path: str):
    """Yield (path, text) for every visible string in the spec (not ids or tokens)."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            if k not in NON_COPY_KEYS:
                yield from _walk_copy(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_copy(v, f"{path}[{i}]")


def _lints(spec: dict, p: list) -> None:
    screens = {s["id"]: s for s in spec.get("screens") or [] if isinstance(s, dict) and "id" in s}
    sheets = {s["id"]: s for s in spec.get("sheets") or [] if isinstance(s, dict) and "id" in s}

    edges: dict[tuple, set] = {}
    for where, owner, blocks in block_lists(spec):
        primaries = 0
        for k, b in enumerate(blocks):
            if isinstance(b, dict) and b.get("type") == "button" and b.get("style") == "primary":
                primaries += 1
                if b.get("feature"):
                    p.append(
                        f"{where}.blocks[{k}]: the primary button is behind feature "
                        f"{b['feature']!r}, so turning it off leaves no main action; make it "
                        "secondary and keep the core-loop action primary"
                    )
            for a in actions_in(b):
                if "go" in a:
                    if a["go"] not in screens:
                        p.append(
                            f"{where}.blocks[{k}]: dangling go target {a['go']!r} (no such screen)"
                        )
                    else:
                        edges.setdefault(owner, set()).add(("screen", a["go"]))
                if "sheet" in a:
                    if a["sheet"] not in sheets:
                        p.append(
                            f"{where}.blocks[{k}]: dangling sheet target {a['sheet']!r} (no such sheet)"
                        )
                    else:
                        edges.setdefault(owner, set()).add(("sheet", a["sheet"]))
        if primaries > 1:
            p.append(f"{where}: {primaries} primary buttons (one primary action per screen)")

    tabs = [t for t in spec.get("tabs") or [] if isinstance(t, dict)]
    if len(tabs) > MAX_TABS:
        p.append(f"tabs: {len(tabs)} tabs (max {MAX_TABS}; move the rest into a screen)")
    roots = [("screen", t["screen"]) for t in tabs if t.get("screen") in screens]
    if not roots and screens:
        roots = [("screen", next(iter(screens)))]
    seen, todo = set(roots), list(roots)
    while todo:
        for nxt in edges.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    for sid in screens:
        if ("screen", sid) not in seen:
            p.append(f"screens[{sid}]: unreachable (no tab or go action leads here)")
    for shid in sheets:
        if ("sheet", shid) not in seen:
            p.append(f"sheets[{shid}]: unreachable (no sheet action opens it)")

    for path, text in _walk_copy({k: v for k, v in spec.items() if k != "directions"}, ""):
        m = PLACEHOLDER_RE.search(text)
        if m:
            p.append(f"{path}: placeholder text {m.group(0)!r} (write the real copy)")

    for sid, s in screens.items():
        has_list = any(
            isinstance(b, dict) and b.get("type") == "list"
            for v in s.get("variants") or []
            if isinstance(v, dict)
            for b in v.get("blocks") or []
        )
        empty = (s.get("states") or {}).get("empty") if isinstance(s.get("states"), dict) else None
        if has_list and not empty:
            p.append(f"screens[{sid}]: has a list but no states.empty (what does a new user see?)")

    for d in spec.get("directions") or []:
        if isinstance(d, dict) and isinstance(d.get("tokens"), dict):
            for line in cc.check(merged_tokens(d)):
                p.append(f"directions[{d.get('id')}]: contrast: {line}")
            for line in dc.check(merged_tokens(d)):
                p.append(f"directions[{d.get('id')}]: design: {line}")

    # Layout tells (TASTE.md, Anti-slop list): the spec can't write CSS, but it can
    # still build the template look out of blocks.
    for where, _owner, blocks in block_lists(spec):
        blocks = [b for b in blocks if isinstance(b, dict)]
        eyebrows = sum(1 for b in blocks if b.get("eyebrow"))
        if eyebrows > MAX_EYEBROWS:
            p.append(
                f"{where}: {eyebrows} eyebrows (a small label over every heading is a template "
                f"tell; keep at most {MAX_EYEBROWS} and let the headings speak)"
            )
        run = 0
        for b in blocks:
            run = run + 1 if b.get("type") == "card" else 0
            if run == MAX_CARD_RUN + 1:
                p.append(
                    f"{where}: {run}+ cards in a row (a wall of equal cards; make it a list, "
                    "or give one card the job and let the rest be rows)"
                )
    for path, text in _walk_copy({k: v for k, v in spec.items() if k != "directions"}, ""):
        key = re.sub(r"\[\d+\]$", "", path).rsplit(".", 1)[-1]
        if EMOJI_RE.search(text) and (key in LABEL_KEYS or key == "options" or EMOJI_RE.match(text.strip())):
            p.append(f"{path}: emoji as UI {text!r} (use an icon from the set, or plain words)")

    used = {
        b.get("feature")
        for _w, _o, blocks in block_lists(spec)
        for b in blocks
        if isinstance(b, dict)
    }
    for f in spec.get("features") or []:
        if isinstance(f, dict) and f.get("id") not in used:
            p.append(
                f"features[{f.get('id')}]: defined but no block references it (cut it or use it)"
            )


def check(spec) -> list[str]:
    if not isinstance(spec, dict):
        return ["spec: must be a JSON object"]
    problems: list[str] = []
    _schema(spec, problems)
    _lints(spec, problems)
    return list(dict.fromkeys(problems))


# ---------------------------------------------------------------- tokens -> CSS


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


TOKEN_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9]{0,39}")


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _token_values(t: dict, w: str, p: list) -> None:
    """Every non-colour token value direction_css writes into the page's <style>:
    keys are plain identifiers and values are numbers, so spec text can't close the
    style block (the colour values are checked as #RRGGBB above)."""

    def key(where: str, k) -> bool:
        if isinstance(k, str) and TOKEN_KEY_RE.fullmatch(k):
            return True
        p.append(f"{where}: bad key {k!r}")
        return False

    for group in ("space", "radius"):
        for k, v in (t.get(group) or {}).items():
            if key(f"{w}.{group}", k) and not _is_num(v):
                p.append(f"{w}.{group}.{k}: must be a number")
    motion = t.get("motion") or {}
    for k, v in (motion.get("duration") or {}).items():
        if key(f"{w}.motion.duration", k) and not _is_num(v):
            p.append(f"{w}.motion.duration.{k}: must be a number")
    for k, v in (motion.get("easing") or {}).items():
        if key(f"{w}.motion.easing", k) and not (
            isinstance(v, list) and len(v) == 4 and all(_is_num(x) for x in v)
        ):
            p.append(f"{w}.motion.easing.{k}: must be 4 numbers")
    if "pressScale" in motion and not _is_num(motion["pressScale"]):
        p.append(f"{w}.motion.pressScale: must be a number")
    if "minTapTarget" in t and not _is_num(t["minTapTarget"]):
        p.append(f"{w}.minTapTarget: must be a number")
    for k, sp in (motion.get("spring") or {}).items():
        if key(f"{w}.motion.spring", k) and not (
            isinstance(sp, dict)
            and all(_is_num(sp.get(f)) and sp.get(f) > 0 for f in ("damping", "stiffness", "mass"))
        ):
            p.append(f"{w}.motion.spring.{k}: damping, stiffness and mass must be positive numbers")
    atmo = t.get("atmosphere")
    if atmo is not None:
        p.extend(f"{w}.atmosphere{e}" for e in atmo_errors(atmo))
    for role, spec in (t.get("type") or {}).items():
        if not key(f"{w}.type", role):
            continue
        if not isinstance(spec, dict):
            p.append(f"{w}.type.{role}: must be an object")
            continue
        for f in ("size", "lineHeight"):
            if not _is_num(spec.get(f)):
                p.append(f"{w}.type.{role}.{f}: must be a number")
        if "letterSpacing" in spec and not _is_num(spec["letterSpacing"]):
            p.append(f"{w}.type.{role}.letterSpacing: must be a number")
        if not re.fullmatch(r"[1-9]00", str(spec.get("weight", "400"))):
            p.append(f"{w}.type.{role}.weight: must be 100-900")
        if spec.get("font", "body") not in ("display", "body", "mono"):
            p.append(f"{w}.type.{role}.font: must be display, body or mono")
    for name, spec in (t.get("elevation") or {}).items():
        if key(f"{w}.elevation", name) and not (
            isinstance(spec, dict)
            and all(_is_num(spec.get(f, 0)) for f in ("shadowOffsetY", "shadowRadius", "shadowOpacity"))
        ):
            p.append(f"{w}.elevation.{name}: shadow values must be numbers")


def temper(pal: dict, temperature: str, mode: str) -> dict:
    """Scale the accent's saturation for the temperature; keep it only if no new
    contrast failure appears (so a lively accent can never break the gate)."""
    factor = TEMPERATURE[temperature]["saturation"]
    acc = pal.get("accent")
    if not (isinstance(acc, str) and cc.HEX.match(acc)):
        return dict(pal)
    r, g, b = (c / 255 for c in _hex_to_rgb(acc))
    h, lum, s = colorsys.rgb_to_hls(r, g, b)
    r2, g2, b2 = colorsys.hls_to_rgb(h, lum, max(0.0, min(1.0, s * factor)))
    new = dict(pal, accent="#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in (r2, g2, b2))))
    if len(cc._contrast(mode, new)) > len(cc._contrast(mode, pal)):
        return dict(pal)
    return new


def _stack(name: str, role: str) -> str:
    if name in SYSTEM_FONTS:
        return MONO_STACK if role == "mono" else SANS_STACK
    if name in MONO_FONTS:
        return MONO_STACK
    return f'"{name}", ' + (MONO_STACK if role == "mono" else SANS_STACK)


def _kebab(k: str) -> str:
    return re.sub(r"([A-Z])", r"-\1", k).lower()


def _shadow(spec: dict, color: str) -> str:
    r, g, b = _hex_to_rgb(color)
    return (
        f"0 {spec.get('shadowOffsetY', 0)}px {spec.get('shadowRadius', 0)}px "
        f"rgba({r},{g},{b},{spec.get('shadowOpacity', 0)})"
    )


def atmo_errors(a) -> list[str]:
    """Problems with an atmosphere object (a direction's default or a choice)."""
    if not isinstance(a, dict):
        return [": must be an object"]
    errs = [f".{k}: unknown key" for k in sorted(set(a) - set(ATMO_DEFAULT))]
    for k, options in ATMO_KEYS.items():
        if k in a and a[k] not in options:
            errs.append(f".{k}: {a[k]!r} is not one of {', '.join(options)}")
    if "grain" in a and not isinstance(a["grain"], bool):
        errs.append(".grain: must be true or false")
    return errs


def atmosphere_of(d: dict) -> dict:
    """A direction's default atmosphere, every key filled."""
    a = merged_tokens(d).get("atmosphere")
    return {**ATMO_DEFAULT, **(a if isinstance(a, dict) else {})}


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, round(c))) for c in rgb))


def _over(fg: str, bg: str, a: float) -> str:
    """fg composited over bg at alpha a (what color-mix(fg a%, transparent) over bg paints)."""
    f, b = _hex_to_rgb(fg), _hex_to_rgb(bg)
    return _hex([fc * a + bc * (1 - a) for fc, bc in zip(f, b)])


def second_hue(pal: dict, mode: str) -> str:
    """The glow's second light: the accent's hue turned 38 degrees, so two apps with
    different accents never share an atmosphere (and no extra token is needed). It
    turns the other way rather than land in yellow-olive, which goes muddy when dim."""
    r, g, b = (c / 255 for c in _hex_to_rgb(pal["accent"]))
    h, lum, sat = colorsys.rgb_to_hls(r, g, b)
    lum = min(lum, 0.62) if mode == "dark" else max(lum, 0.42)
    h2 = (h + 38 / 360) % 1
    if 40 / 360 <= h2 <= 95 / 360:
        h2 = (h - 38 / 360) % 1
    return _hex(c * 255 for c in colorsys.hls_to_rgb(h2, lum, sat * 0.9))


def _falloffs() -> list[tuple[float, float]]:
    """Every (light 1, light 2) strength pair the glow paints inside the 390x844 phone,
    from the same geometry the CSS draws (ATMO_LIGHTS) at both ends of its drift, cut
    down to the pairs no other pair beats on both lights (only those can be the darkest
    or brightest spot)."""
    pairs = set()
    for dx, dy, sc in ((0.0, 0.0, 1.0), ATMO_DRIFT):
        for yi in range(43):
            for xi in range(21):
                # undo the drift transform (about the centre) to find the gradient point
                x = (xi / 20 - 0.5 - dx) / sc + 0.5
                y = (yi / 42 - 0.5 - dy) / sc + 0.5
                f = []
                for cx, cy, rx, ry in ATMO_LIGHTS:
                    r = (((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2) ** 0.5
                    f.append(round(max(0.0, 1 - r), 3))
                pairs.add((f[0], f[1]))
    return [p for p in pairs if not any(q != p and q[0] >= p[0] and q[1] >= p[1] for q in pairs)]


FALLOFFS: list[tuple[float, float]] = []


def lit_grounds(pal: dict, mode: str, alpha: float, c1: str, c2: str) -> list[str]:
    """Every colour text can land on once lights c1 and c2 are lit at peak `alpha`: the
    lit ground at each worst-case spot, and a glass card over it."""
    if not FALLOFFS:
        FALLOFFS.extend(_falloffs())
    out = []
    for f1, f2 in FALLOFFS:
        ground = _over(c2, _over(c1, pal["bg"], alpha * f1), alpha * f2)
        out += [ground, _over(pal["surfaceRaised"], ground, GLASS_FILL[mode])]
    return out


def _glow(base: str, toward: str, t: float) -> str:
    """base's hue, saturated, at a lightness t of the way from `toward` to base."""
    r, g, b = (c / 255 for c in _hex_to_rgb(base))
    h, lb, sb = colorsys.rgb_to_hls(r, g, b)
    r, g, b = (c / 255 for c in _hex_to_rgb(toward))
    lt = colorsys.rgb_to_hls(r, g, b)[1]
    return _hex(c * 255 for c in colorsys.hls_to_rgb(h, lt + (lb - lt) * t, min(1.0, sb * 1.1)))


def atmo_lights(pal: dict, mode: str, intensity: str) -> dict:
    """The two light colours and their peak alpha for one palette: the brightest pair
    (closest to the accent) at which every ink still clears AA everywhere on the lit
    ground. Alpha 0 when even a ground-coloured light can't (the palette has no
    headroom at all)."""
    a = ATMO_INTENSITY[intensity]
    hue2 = second_hue(pal, mode)

    def pair(t: float) -> tuple[str, str]:
        return _glow(pal["accent"], pal["bg"], t), _glow(hue2, pal["bg"], t)

    def ok(t: float) -> bool:
        c1, c2 = pair(t)
        return all(cc.ratio(pal[ink], g) >= INK_AA for g in lit_grounds(pal, mode, a, c1, c2) for ink in cc.INKS)

    if not ok(0.0):
        c1, c2 = pair(0.0)
        return {"light1": c1, "light2": c2, "alpha": 0}
    lo, hi = 0.0, 1.0
    if ok(1.0):
        lo = 1.0
    else:
        for _ in range(16):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    c1, c2 = pair(lo)
    return {"light1": c1, "light2": c2, "alpha": a}


def _simplify(pts: list, eps: float) -> list:
    """Ramer-Douglas-Peucker: the fewest points that stay within eps of the curve."""
    (t0, x0), (t1, x1) = pts[0], pts[-1]
    worst, at = 0.0, 0
    for i in range(1, len(pts) - 1):
        t, x = pts[i]
        d = abs(x0 + (x1 - x0) * (t - t0) / (t1 - t0) - x)
        if d > worst:
            worst, at = d, i
    if worst <= eps:
        return [pts[0], pts[-1]]
    return _simplify(pts[: at + 1], eps)[:-1] + _simplify(pts[at:], eps)


def settle_spring(sp: dict) -> dict:
    """The spring every screen-scale move uses: the direction's gentle spring, damped
    to at least critical so it arrives without passing the mark. Temperature changes
    its speed (the CSS scales the duration by --mmult), never makes it bounce."""
    crit = 2 * (float(sp["stiffness"]) * float(sp.get("mass", 1))) ** 0.5
    return dict(sp, damping=max(float(sp["damping"]), crit))


def spring_curve(sp: dict) -> tuple[str, int]:
    """A damped spring as a CSS linear() easing plus its settle time in ms, so the
    prototype moves on the same spring tokens Reanimated uses in the app."""
    k, c, m = float(sp["stiffness"]), float(sp["damping"]), float(sp.get("mass", 1))
    x, v, dt, t, pts = 0.0, 0.0, 1 / 1000, 0.0, [(0.0, 0.0)]
    settled = 0
    while t < 3.0:
        a = (k * (1 - x) - c * v) / m
        v += a * dt
        x += v * dt
        t += dt
        if abs(1 - x) < 0.002 and abs(v) < 0.02:
            settled += 1
            if settled > 30:
                break
        else:
            settled = 0
        if round(t * 1000) % 8 == 0:
            pts.append((t, x))
    dur = max(t, 0.05)
    pts.append((t, 1.0))
    keep = _simplify(pts, 0.003)
    stops = ", ".join(f"{xv:.3f} {tv / dur * 100:.1f}%" for tv, xv in keep[1:-1])
    return f"linear(0, {stops}, 1)", round(dur * 1000)


def direction_css(d: dict) -> str:
    t = merged_tokens(d)
    sel = f'.phone[data-direction="{d["id"]}"]'
    v = []
    fonts = t.get("font", {})
    for role in ("display", "body", "mono"):
        v.append(f"--font-{role}: {_stack(fonts.get(role, 'System'), role)};")
    for k, px in t.get("space", {}).items():
        v.append(f"--s-{k}: {px}px;")
    for k, px in t.get("radius", {}).items():
        v.append(f"--r-{k}: {px}px;")
    for k, ms in t.get("motion", {}).get("duration", {}).items():
        v.append(f"--d-{k}: {ms}ms;")
    for k, pts in t.get("motion", {}).get("easing", {}).items():
        v.append(f"--e-{k}: cubic-bezier({', '.join(str(x) for x in pts)});")
    v.append(f"--press-base: {t.get('motion', {}).get('pressScale', 0.97)};")
    for role, spec in t.get("type", {}).items():
        v.append(f"--t-{role}-font: var(--font-{spec.get('font', 'body')});")
        v.append(f"--t-{role}-size: {spec['size']}px;")
        v.append(f"--t-{role}-lh: {spec['lineHeight']}px;")
        v.append(f"--t-{role}-weight: {spec.get('weight', '400')};")
        v.append(f"--t-{role}-ls: {spec.get('letterSpacing', 0)}px;")
        v.append(f"--t-{role}-case: {'uppercase' if spec.get('uppercase') else 'none'};")
    v.append(f"--tap: {t.get('minTapTarget', 48)}px;")
    out = [f"{sel} {{ {' '.join(v)} }}"]
    springs = t.get("motion", {}).get("spring") or {}
    for temp, cfg in TEMPERATURE.items():
        sv = []
        for name, sp in springs.items():
            curve, ms = spring_curve(dict(sp, damping=sp["damping"] * cfg["damping"]))
            sv.append(f"--spring-{name}: {curve}; --spring-{name}-dur: {ms}ms;")
        if "gentle" in springs:
            curve, ms = spring_curve(settle_spring(springs["gentle"]))
            sv.append(f"--settle: {curve}; --settle-dur: {ms}ms;")
        if sv:
            out.append(f'{sel}[data-temperature="{temp}"] {{ {" ".join(sv)} }}')
    for mode in MODES:
        pal = t["color"][mode]
        cv = [f"--{_kebab(k)}: {val};" for k, val in pal.items()]
        for name in ATMO_INTENSITY:
            lit = atmo_lights(pal, mode, name)
            out.append(
                f'{sel}[data-mode="{mode}"][data-intensity="{name}"] '
                f"{{ --atmo-1: {lit['light1']}; --atmo-2: {lit['light2']}; --atmo-a: {lit['alpha']}; }}"
            )
        shadow = pal.get("shadow", "#000000")
        for name, spec in (t.get("elevation") or {}).items():
            cv.append(f"--elev-{name}: {_shadow(spec, shadow)};")
        out.append(f'{sel}[data-mode="{mode}"] {{ {" ".join(cv)} }}')
        for temp in TEMPERATURE:
            tempered = temper(pal, temp, mode)
            if tempered["accent"] != pal["accent"]:
                out.append(
                    f'{sel}[data-mode="{mode}"][data-temperature="{temp}"] '
                    f'{{ --accent: {tempered["accent"]}; }}'
                )
    return "\n".join(out)


def feel_css() -> str:
    out = []
    for name, k in DENSITY.items():
        out.append(f'.phone[data-density="{name}"] {{ --density: {k}; }}')
    for name, cfg in TEMPERATURE.items():
        enter = (
            f"cubic-bezier({', '.join(str(x) for x in cfg['enter'])})"
            if cfg["enter"]
            else "var(--e-enter)"
        )
        out.append(
            f'.phone[data-temperature="{name}"] {{ --mmult: {cfg["motion"]}; '
            f'--rmult: {cfg["radius"]}; --press-k: {cfg["press"]}; '
            f"--ease-pop: {enter}; }}"
        )
    for mode, fill in GLASS_FILL.items():
        out.append(f'.phone[data-mode="{mode}"] {{ --glass-fill: {fill * 100:g}%; }}')
    (x1, y1, rx1, ry1), (x2, y2, rx2, ry2) = ATMO_LIGHTS
    dx, dy, sc = ATMO_DRIFT

    def light(n: int, rx, ry, x, y) -> str:
        mix = f"color-mix(in srgb, var(--atmo-{n}) calc(var(--atmo-a) * 100%), transparent)"
        return f"radial-gradient({rx * 100:g}% {ry * 100:g}% at {x * 100:g}% {y * 100:g}%, {mix}, transparent)"

    out.append(
        f".atmo::before {{ background: {light(1, rx1, ry1, x1, y1)}, {light(2, rx2, ry2, x2, y2)}; }}"
    )
    out.append(
        f"@keyframes atmo-drift {{ to {{ transform: translate({dx * 100:g}%, {dy * 100:g}%) scale({sc:g}); }} }}"
    )
    return "\n".join(out)


FONT_CACHE = Path(
    os.environ.get("APPBOX_FONT_CACHE") or Path.home() / ".cache" / "app-in-a-box" / "fonts"
)
FONT_MAX_BYTES = 160_000  # one family's Latin subset; anything bigger stays a <link>
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def _font_families(spec: dict) -> list[str]:
    fams = []
    for d in spec["directions"]:
        for fam in (merged_tokens(d).get("font") or {}).values():
            if fam not in SYSTEM_FONTS and fam not in MONO_FONTS and fam not in fams:
                fams.append(fam)
    return fams


def _css2_url(fam: str) -> str:
    # Ask only for weights the family has: Google answers 400 to a weight it lacks
    # (Young Serif is 400 only), and the whole family would silently fall back.
    have = (_library_families().get(fam) or {}).get("weights")
    ws = [w for w in (400, 500, 600, 700) if not have or w in have] or [400]
    return (
        "https://fonts.googleapis.com/css2?family="
        + fam.replace(" ", "+")
        + ":wght@"
        + ";".join(str(w) for w in ws)
        + "&display=swap"
    )


_NET = {"down": False}  # after one failed fetch, stop trying: offline renders stay fast


def _fetch(url: str, path: Path) -> bytes | None:
    """url's bytes, from the cache or (unless APPBOX_OFFLINE=1) the network."""
    if path.is_file():
        return path.read_bytes()
    if os.environ.get("APPBOX_OFFLINE") == "1" or _NET["down"]:
        return None
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (fixed https hosts)
            data = r.read(FONT_MAX_BYTES + 1)
    except Exception:  # offline, blocked, DNS: fall back to a <link>
        _NET["down"] = True
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError:
        pass
    return data


def inline_font(fam: str) -> str | None:
    """@font-face rules for fam's Latin subset with the woff2 inlined, or None when it
    can't be fetched (or is too big). Cached, so a re-render needs no network."""
    import base64

    slug = re.sub(r"[^a-z0-9]+", "-", fam.lower())
    css = _fetch(_css2_url(fam), FONT_CACHE / f"{slug}.google.css")
    if not css:
        return None
    by_url: dict[str, list[int]] = {}
    for block in re.findall(r"/\* latin \*/\s*@font-face\s*\{(.*?)\}", css.decode("utf-8", "replace"), re.S):
        m_url = re.search(r"url\((https://fonts\.gstatic\.com/[A-Za-z0-9/._-]+\.woff2)\)", block)
        m_w = re.search(r"font-weight:\s*(\d{3})", block)
        if m_url and m_w and "font-style: normal" in block:
            by_url.setdefault(m_url.group(1), []).append(int(m_w.group(1)))
    if not by_url:
        return None
    rules, total = [], 0
    for url, weights in by_url.items():
        data = _fetch(url, FONT_CACHE / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".woff2"))
        if not data or not data.startswith(b"wOF2"):
            return None
        total += len(data)
        if total > FONT_MAX_BYTES:
            return None
        w = f"{min(weights)} {max(weights)}" if len(weights) > 1 else str(weights[0])
        rules.append(
            f'@font-face {{ font-family: "{fam}"; font-style: normal; font-weight: {w}; '
            f"font-display: block; src: url(data:font/woff2;base64,"
            f'{base64.b64encode(data).decode()}) format("woff2"); }}'
        )
    return "\n".join(rules)


def fonts(spec: dict) -> tuple[str, str]:
    """(<head> links, inline @font-face CSS). Each family is inlined when it can be, so
    the prototype renders right offline and when forwarded; one that can't (offline
    first render, too big) falls back to a Google Fonts <link> and says so. The Type
    knob's alternates come after the directions' own families and share a budget
    (ALT_FONT_BUDGET): past it they load as <link>s, so offering them can't bloat the
    file past it, at the cost of needing a connection to preview those few."""
    links, faces = [], []
    own = _font_families(spec)
    alt_bytes = 0
    for fam in own + [f for f in _alt_families(spec) if f not in own]:
        face = inline_font(fam)
        if face and fam not in own:
            if alt_bytes + len(face) > ALT_FONT_BUDGET:
                face = None
            else:
                alt_bytes += len(face)
        if face:
            faces.append(face)
        else:
            links.append(f'<link rel="stylesheet" href="{_css2_url(fam).replace("&", "&amp;")}">')
            print(f"note: font {fam!r} is loaded from Google Fonts (not inlined: offline or too big)")
    if links:
        links.insert(0, '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
        links.insert(0, '<link rel="preconnect" href="https://fonts.googleapis.com">')
    return "\n".join(links), "\n".join(faces)


# ---------------------------------------------------------------- type library

# A curated list of OFL families (scripts/proto/fonts.json) with pairings grouped by
# personality. The Type knob offers a direction the pairings that share its display
# face's personality, so the founder can swap faces without leaving its character.
FONT_LIBRARY = PROTO / "fonts.json"
DIRECTIONS_SKILL = KIT / "skills" / "design-directions" / "SKILL.md"
FONT_ROLES = ("display", "body", "mono")
TYPE_OPTIONS_MAX = 3  # alternative pairings offered per direction
ALT_FONT_BUDGET = 400_000  # inlined CSS for all the alternates; keeps the page under ~1 MB
FONT_SOURCE_RE = re.compile(r"https://github\.com/google/fonts/tree/main/ofl/[a-z0-9]+")
_LIB: dict = {}


def font_library() -> dict:
    if not _LIB:
        _LIB.update(load_json(str(FONT_LIBRARY)))
    return _LIB


def _library_families(lib: dict | None = None) -> dict[str, dict]:
    lib = font_library() if lib is None else lib
    fams = lib.get("families") if isinstance(lib, dict) else None
    return {f["family"]: f for f in fams or [] if isinstance(f, dict) and isinstance(f.get("family"), str)}


def pairing_label(pr: dict) -> str:
    return pr["display"] if pr["display"] == pr["body"] else f"{pr['display']} + {pr['body']}"


def personality_of(d: dict) -> str | None:
    """The personality of a direction's display face (else its body face), when the
    library knows it. A system or unlisted face has none, so the knob offers nothing."""
    fams = _library_families()
    font = merged_tokens(d).get("font") or {}
    for role in ("display", "body"):
        f = fams.get(font.get(role))
        if f and f.get("personality") != "mono":
            return f["personality"]
    return None


def type_options(d: dict) -> list[dict]:
    """The pairings the Type knob offers for direction d, in library order: same
    personality as its display face, not the pairing it already uses, at most
    TYPE_OPTIONS_MAX (each one is a family or two the page has to load)."""
    group = personality_of(d)
    if not group:
        return []
    fams = _library_families()
    own = merged_tokens(d).get("font") or {}
    out = []
    for pr in font_library().get("pairings") or []:
        if (fams.get(pr["display"]) or {}).get("personality") != group:
            continue
        if (pr["display"], pr["body"]) == (own.get("display"), own.get("body")):
            continue
        out.append({k: pr[k] for k in ("id", "display", "body", "mono") if k in pr})
        if len(out) == TYPE_OPTIONS_MAX:
            break
    return out


def _alt_families(spec: dict) -> list[str]:
    fams = []
    for d in spec["directions"]:
        for pr in type_options(d):
            for role in FONT_ROLES:
                if pr.get(role) and pr[role] not in fams:
                    fams.append(pr[role])
    return fams


def _nearest_weight(weight, have: list[int]) -> str:
    """The family's closest weight to `weight` (ties go heavier): a pairing face with
    fewer weights must not ask the app to register one that doesn't exist."""
    w = int(str(weight))
    return str(min(have, key=lambda x: (abs(x - w), -x)))


def archetype_fonts(skill: str) -> list[str] | None:
    """Every family the design-directions archetype table suggests: the names in
    parentheses in its "Type pairing" column, split on / and +. None when the table
    is missing (the guard reports that rather than passing on nothing)."""
    lines = skill.splitlines()
    head = next((i for i, ln in enumerate(lines) if ln.startswith("|") and "Type pairing" in ln), None)
    if head is None:
        return None
    col = [c.strip() for c in lines[head].strip().strip("|").split("|")].index("Type pairing")
    out = []
    for ln in lines[head + 2 :]:
        if not ln.startswith("|"):
            break
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        for group in re.findall(r"\(([^)]*)\)", cells[col] if col < len(cells) else ""):
            for name in re.split(r"\s*[/+]\s*", group):
                name = name.strip()
                if name and not name.lower().startswith("the "):  # "the system sans"
                    out.append(name)
    return out


def library_errors(lib, skill: str | None = None) -> list[str]:
    """Problems with the type library (and, given its text, the archetype table)."""
    if not isinstance(lib, dict):
        return ["fonts.json: must be an object"]
    p: list[str] = []
    groups = lib.get("personalities")
    if not (isinstance(groups, dict) and groups):
        p.append("personalities: needs at least one personality")
        groups = {}
    fams = lib.get("families")
    if not isinstance(fams, list):
        return p + ["families: must be a list"]
    seen: dict[str, dict] = {}
    for i, f in enumerate(fams):
        name = f.get("family") if isinstance(f, dict) else None
        if not (isinstance(name, str) and FONT_RE.fullmatch(name)):
            p.append(f"families[{i}]: family must be a plain family name")
            continue
        w = f"families[{name}]"
        if name in seen:
            p.append(f"{w}: listed twice")
        seen[name] = f
        if name.lower() in dc.OVERUSED_FONTS:
            p.append(f"{w}: is on check_design.py's OVERUSED_FONTS, so the app's gates would fail it")
        if name.lower() in dc.BUILT_IN:
            p.append(f"{w}: is built into the phone; the library lists only families to load")
        if f.get("license") != "OFL-1.1":
            p.append(f"{w}: license must be OFL-1.1, got {f.get('license')!r}")
        if f.get("rfn") is not False:
            p.append(f"{w}: declares a Reserved Font Name (rfn must be false): drop the family")
        if f.get("personality") not in groups:
            p.append(f"{w}: personality {f.get('personality')!r} is not one of {', '.join(groups)}")
        roles = f.get("roles")
        if not (isinstance(roles, list) and roles and set(roles) <= set(FONT_ROLES)):
            p.append(f"{w}: roles must be a non-empty list of {', '.join(FONT_ROLES)}")
        ws = f.get("weights")
        if not (
            isinstance(ws, list)
            and 400 in ws
            and all(isinstance(x, int) and not isinstance(x, bool) and x in range(100, 1000, 100) for x in ws)
        ):
            p.append(f"{w}: weights must be a list of 100-900 that includes 400")
        if not (isinstance(f.get("source"), str) and FONT_SOURCE_RE.fullmatch(f["source"])):
            p.append(f"{w}: source must be its google/fonts ofl/ folder")
    if not 40 <= len(seen) <= 60:
        p.append(f"families: {len(seen)} listed; the library is curated to about 45")
    pairs = lib.get("pairings")
    if not isinstance(pairs, list):
        return p + ["pairings: must be a list"]
    ids, combos = set(), set()
    for i, pr in enumerate(pairs):
        pid = pr.get("id") if isinstance(pr, dict) else None
        if not (isinstance(pid, str) and ID_RE.match(pid)):
            p.append(f"pairings[{i}]: id must be a lowercase id")
            continue
        w = f"pairings[{pid}]"
        if pid in ids:
            p.append(f"{w}: duplicate id")
        ids.add(pid)
        for k in sorted(set(pr) - {"id", *FONT_ROLES}):
            p.append(f"{w}.{k}: unknown key")
        for role in FONT_ROLES:
            fam = pr.get(role)
            if fam is None and role == "mono":
                continue
            if fam not in seen:
                p.append(f"{w}.{role}: {fam!r} is not a listed family")
            elif role not in (seen[fam].get("roles") or []):
                p.append(f"{w}.{role}: {fam!r} isn't suited to {role} (its roles: {seen[fam].get('roles')})")
        combo = (pr.get("display"), pr.get("body"))
        if combo in combos:
            p.append(f"{w}: same display + body as an earlier pairing")
        combos.add(combo)
    if skill is not None:
        named = archetype_fonts(skill)
        if named is None:
            p.append("design-directions: no archetype table with a Type pairing column")
        for fam in named or []:
            if fam.lower() not in dc.BUILT_IN and fam not in seen:
                p.append(f"design-directions: the archetype table suggests {fam!r}, which is not in fonts.json")
    return p


# ---------------------------------------------------------------- render


def _rev(spec: dict) -> str:
    """Fingerprint of what saved choices could override: defaults and the features."""
    basis = [
        spec.get("defaults"),
        [[f.get("id"), f.get("default")] for f in spec.get("features") or []],
        {d.get("id"): atmosphere_of(d) for d in spec.get("directions") or []},
    ]
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:12]


def _script_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")


def _type_config(d: dict) -> list[dict]:
    own = merged_tokens(d).get("font") or {}
    out = []
    for pr in type_options(d):
        fams = {r: pr.get(r, own.get(r, "System")) for r in FONT_ROLES}
        out.append(
            {
                **pr,
                "label": pairing_label(pr),
                "stacks": {r: _stack(fams[r], r) for r in FONT_ROLES},
            }
        )
    return out


def render(spec: dict, out: str) -> None:
    css = "\n".join([feel_css()] + [direction_css(d) for d in spec["directions"]])
    links, faces = fonts(spec)
    parts = {
        "TITLE": html.escape(tone(spec["app"]["name"]) + " prototype"),
        "FONTS": links,
        "CSS": "\n".join([faces] + [(PROTO / f).read_text() for f in ("page.css", "phone.css")]) + "\n" + css,
        "SPEC": _script_json(spec),
        "CONFIG": _script_json(
            {
                "icons": load_json(str(PROTO / "icons.json"))["icons"],
                "density": list(DENSITY),
                "temperature": list(TEMPERATURE),
                "atmosphere": {
                    "mode": list(ATMO_MODES),
                    "intensity": list(ATMO_INTENSITY),
                    "surface": list(ATMO_SURFACES),
                    "lights": [list(x) for x in ATMO_LIGHTS],
                    "defaults": {d["id"]: atmosphere_of(d) for d in spec["directions"]},
                },
                "components": COMPONENTS,
                "rev": _rev(spec),
                "palettes": {d["id"]: merged_tokens(d)["color"] for d in spec["directions"]},
                "fonts": {
                    d["id"]: merged_tokens(d).get("font", {}).get("display", "System")
                    for d in spec["directions"]
                },
                # The Type knob: each offered pairing with the CSS stacks the runtime
                # swaps into --font-display/--font-body/--font-mono.
                "typeOptions": {d["id"]: _type_config(d) for d in spec["directions"]},
            }
        ),
        "JS": "\n".join(
            (PROTO / f).read_text() for f in ("blocks.js", "fx.js", "panel.js", "runtime.js")
        ),
    }
    shell = (PROTO / "shell.html").read_text()
    page = re.sub(r"\{\{([A-Z]+)\}\}", lambda m: parts[m.group(1)], shell)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(page)


# ---------------------------------------------------------------- freeze


def resolve_choices(spec: dict, ch) -> tuple[dict, list[str]]:
    errs: list[str] = []
    if not isinstance(ch, dict):
        return {}, ["choices: must be a JSON object"]
    allowed = {"direction", "mode", "density", "temperature", "tone", "variants", "features", "atmosphere", "font"}
    for k in sorted(set(ch) - allowed):
        errs.append(f"choices.{k}: unknown key")
    d = spec["defaults"]
    out = {"version": 1}
    dirs = [x["id"] for x in spec["directions"]]
    for key, options in (
        ("direction", dirs),
        ("mode", MODES),
        ("density", tuple(DENSITY)),
        ("temperature", tuple(TEMPERATURE)),
        ("tone", TONES),
    ):
        val = ch.get(key, d[key])
        if val not in options:
            errs.append(f"choices.{key}: {val!r} is not one of {', '.join(options)}")
        out[key] = val
    screens = {s["id"]: s for s in spec["screens"]}
    variants = ch.get("variants", {})
    if not isinstance(variants, dict):
        errs.append("choices.variants: must be an object")
        variants = {}
    for sid in variants:
        if sid not in screens:
            errs.append(f"choices.variants.{sid}: no such screen")
    out["variants"] = {}
    for sid, s in screens.items():
        have = [v["id"] for v in s["variants"]]
        vid = variants.get(sid, have[0])
        if vid not in have:
            errs.append(f"choices.variants.{sid}: no variant {vid!r} (have: {', '.join(have)})")
        out["variants"][sid] = vid
    feats = ch.get("features", {})
    if not isinstance(feats, dict):
        errs.append("choices.features: must be an object")
        feats = {}
    fdefs = {f["id"]: f for f in spec.get("features") or []}
    for fid, val in feats.items():
        if fid not in fdefs:
            errs.append(f"choices.features.{fid}: no such feature")
        elif not isinstance(val, bool):
            errs.append(f"choices.features.{fid}: must be true or false")
    out["features"] = {fid: bool(feats.get(fid, f["default"])) for fid, f in fdefs.items()}
    # Atmosphere knobs: anything left out takes the chosen direction's default.
    atmo = ch.get("atmosphere", {})
    errs += [f"choices.atmosphere{e}" for e in atmo_errors(atmo)]
    base = next((atmosphere_of(x) for x in spec["directions"] if x["id"] == out["direction"]), ATMO_DEFAULT)
    out["atmosphere"] = {**base, **(atmo if isinstance(atmo, dict) else {})}
    out["atmosphere"] = {k: out["atmosphere"][k] for k in ATMO_DEFAULT}
    out["font"] = _resolve_font(spec, out["direction"], ch.get("font"), errs)
    return out, errs


def _resolve_font(spec: dict, did: str, val, errs: list[str]) -> dict:
    """The Type knob's choice, resolved: {pairing, display, body, mono}. Left out (older
    choices) or naming the direction's own faces, it's the direction default; anything
    else must be a pairing the knob offered for that direction, so freeze never writes a
    family the founder didn't see."""
    d = next((x for x in spec["directions"] if x["id"] == did), None)
    own = (merged_tokens(d).get("font") or {}) if d else {}
    default = {"pairing": "default", **{r: own.get(r, "System") for r in FONT_ROLES}}
    if val is None or val == {} or d is None:
        return default
    if not isinstance(val, dict):
        errs.append('choices.font: must be an object, {"display": ..., "body": ...}')
        return default
    for k in sorted(set(val) - {"pairing", *FONT_ROLES}):
        errs.append(f"choices.font.{k}: unknown key")
    disp, body = val.get("display"), val.get("body")
    if (disp, body) == (own.get("display"), own.get("body")):
        picked = default
    else:
        opts = type_options(d)
        hit = next((o for o in opts if (o["display"], o["body"]) == (disp, body)), None)
        if hit is None:
            offered = "; ".join(pairing_label(o) for o in opts) or "none"
            errs.append(
                f"choices.font: {disp!r} + {body!r} is not a pairing the Type knob offers "
                f"for direction {did!r} (offered: {offered})"
            )
            return default
        picked = {"pairing": hit["id"], "display": disp, "body": body, "mono": hit.get("mono", default["mono"])}
    for k in ("mono", "pairing"):
        if k in val and val[k] != picked[k]:
            errs.append(f"choices.font.{k}: {val[k]!r} doesn't match the pairing ({picked[k]!r})")
    return picked


def frozen_tokens(spec: dict, ch: dict) -> dict:
    d = next(x for x in spec["directions"] if x["id"] == ch["direction"])
    t = merged_tokens(d)
    t = {"$schema": load_json(str(TEMPLATE_TOKENS)).get("$schema", ""), **t}
    t["name"], t["version"], t["mode"] = d["id"], 2, ch["mode"]
    f = ch.get("font") or {}
    if f.get("pairing", "default") != "default":
        # The Type knob's pairing replaces the faces; each role keeps its weight unless
        # the new family lacks it (then its nearest, as the prototype rendered it).
        t["font"] = {**(t.get("font") or {}), **{r: f[r] for r in FONT_ROLES}}
        fams = _library_families()
        for spec_ in (t.get("type") or {}).values():
            have = (fams.get(t["font"].get(spec_.get("font", "body"))) or {}).get("weights")
            if have:
                spec_["weight"] = _nearest_weight(spec_.get("weight", "400"), have)
    k = DENSITY[ch["density"]]
    t["space"] = {n: max(1, round(v * k)) for n, v in t.get("space", {}).items()}
    cfg = TEMPERATURE[ch["temperature"]]
    t["radius"] = {
        n: v if n == "pill" else round(v * cfg["radius"]) for n, v in t.get("radius", {}).items()
    }
    motion = t.setdefault("motion", {})
    motion["duration"] = {
        n: round(v * cfg["motion"]) for n, v in motion.get("duration", {}).items()
    }
    motion["pressScale"] = round(1 - (1 - motion.get("pressScale", 0.97)) * cfg["press"], 3)
    motion["spring"] = {
        n: dict(sp, damping=round(sp.get("damping", 20) * cfg["damping"], 1))
        for n, sp in (motion.get("spring") or {}).items()
    }
    if cfg["enter"]:
        motion.setdefault("easing", {})["enter"] = list(cfg["enter"])
    raw = t["color"]
    t["color"] = {m: temper(raw[m], ch["temperature"], m) for m in MODES}
    a = ch.get("atmosphere") or atmosphere_of(d)
    # What the app needs to paint the same light: the choice, plus the resolved colours
    # and the contrast-capped peak alpha per mode, so the app never re-derives them.
    t["atmosphere"] = {
        **a,
        "lights": [list(x) for x in ATMO_LIGHTS],
        # from the untempered palette, exactly as the prototype painted it
        "color": {
            m: dict(atmo_lights(raw[m], m, a["intensity"]), **({"alpha": 0} if a["mode"] == "none" else {}))
            for m in MODES
        },
    }
    return t


def _icon_prop(name: str | None) -> str:
    if not name:
        return ""
    sf, md = icon_native()[name]
    return f' icon={{{{ sf: "{sf}", md: "{md}" }}}}'


def _jsx(b: dict) -> str:
    """The exact components/ui call a block becomes (props the prototype decided)."""
    t, ic = b["type"], _icon_prop(b.get("icon"))
    if t == "header":
        # The eyebrow is a plain dim line (a date, a context), never a tracked uppercase
        # kicker over the title: that's a generated-UI tell (TASTE.md, Anti-slop list).
        parts = (["<Body dim>"] if b.get("eyebrow") else []) + ["<Title>"]
        return " + ".join(parts + (["<Body dim>"] if "subtitle" in b else []))
    if t == "text":
        return "<Body>"
    if t == "list":
        return "<Card> of <ListRow title subtitle value icon onPress> (FlashList if it can outgrow a screen)"
    if t == "card":
        icon = ""
        if b.get("icon"):
            sf, md = icon_native()[b["icon"]]
            icon = f' + <Icon sf="{sf}" md="{md}">'
        return f"<Card{' onPress' if 'action' in b else ''}>{icon}"
    if t == "button":
        variant = b.get("style", "primary")
        return f'<Button variant="{variant}"{ic}>'
    if t == "chips":
        return "<Chip> per option (selected / onPress)"
    if t == "segmented":
        return "<SegmentedControl> (native on iOS / Android)"
    if t == "input":
        return "<FormField> (react-hook-form + zod), or <Field>"
    if t == "stat":
        return f"<StatCard{ic}>"
    if t == "progress":
        return "<ProgressBar>"
    if t == "empty":
        return f"<EmptyState{ic or ' icon'} action={{<Button>}}>" if "action" in b else f"<EmptyState{ic or ' icon'}>"
    if t == "image":
        return f'<Media ratio="{b.get("ratio", "4:3")}">'
    if t == "divider":
        return "<Section title>"
    return "useToast().show()"


def _content(b: dict, tn: str) -> str:
    t = b["type"]
    if t == "list":
        rows = [tone(i["title"], tn) for i in b["items"]]
        head = f"{tone(b['title'], tn)}: " if "title" in b else ""
        return f"{head}{len(rows)} rows ({'; '.join(rows)})"
    if t in ("chips", "segmented"):
        lab = f"{tone(b['label'], tn)}: " if "label" in b else ""
        return lab + " / ".join(tone(o, tn) for o in b["options"])
    if t == "progress":
        return f"{tone(b['label'], tn)} {round(b['value'] * 100)}%"
    if t == "button":
        return f"{tone(b['label'], tn)} ({b['style']})"
    if t == "empty" and "action" in b:
        return f"{tone(b['title'], tn)} · {tone(b['body'], tn)} · CTA \"{tone(b['action']['label'], tn)}\""
    bits = [
        tone(b[k], tn)
        for k in (
            "eyebrow",
            "title",
            "label",
            "value",
            "subtitle",
            "body",
            "text",
            "placeholder",
            "hint",
        )
        if k in b
    ]
    return " · ".join(bits) or "-"


def _action_desc(a: dict | None, tn: str) -> str:
    if not a:
        return ""
    if "go" in a:
        return f"go `{a['go']}`"
    if "sheet" in a:
        return f"sheet `{a['sheet']}`"
    if "back" in a:
        return "back"
    return f"toast \"{_md(tone(a['toast'], tn))}\""


def _md(s: str) -> str:
    """Spec text as one inert Markdown line: whitespace collapsed, and the characters
    that open structure (tables, code, headings, links, emphasis) escaped."""
    s = " ".join(str(s).split())
    return re.sub(r"([\\`*_\[\]|<>#])", r"\\\1", s)


def _block_table(blocks: list, ch: dict, fdefs: dict) -> list[str]:
    tn = ch["tone"]
    rows = [
        "| # | Block | Component (`components/ui`) | Content | Action | v1 |",
        "|---|---|---|---|---|---|",
    ]
    for i, b in enumerate(blocks, 1):
        acts = [_action_desc(a, tn) for a in actions_in(b)]
        f = b.get("feature")
        v1 = "yes" if not f else (f"yes (`{f}`)" if ch["features"][f] else f"**cut** (`{f}` off)")
        rows.append(
            f"| {i} | {b['type']} | `{_jsx(b)}` | {_md(_content(b, tn))} | "
            f"{', '.join(dict.fromkeys(a for a in acts if a))} | {v1} |"
        )
    return rows


def screens_md(spec: dict, ch: dict) -> str:
    tn = ch["tone"]
    d = next(x for x in spec["directions"] if x["id"] == ch["direction"])
    fdefs = {f["id"]: f for f in spec.get("features") or []}
    name = _md(tone(spec["app"]["name"], tn))
    L = [
        f"# {name}: screens (frozen)",
        "",
        "Frozen from `design/prototype.json` by `scripts/prototype.py freeze`. The scaffold",
        "builds these screens one for one. To change one, edit the prototype and re-freeze;",
        "don't hand-edit this file.",
        "",
        "## Choices",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Direction | {_md(tone(d['label'], tn))} (`{d['id']}`): {_md(tone(d['why'], tn))} |",
        f"| Mode (fallback) | {ch['mode']} |",
        f"| Density | {ch['density']} |",
        f"| Temperature | {ch['temperature']} |",
        f"| Copy tone | {ch['tone']} |",
        _type_row(ch),
        "",
        "## Features in / out of v1",
        "",
        "| Feature | v1 | Why |",
        "|---|---|---|",
    ]
    for fid, f in fdefs.items():
        state = "in" if ch["features"][fid] else "**out**"
        L.append(
            f"| {_md(tone(f['label'], tn))} (`{fid}`) | {state} | {_md(tone(f.get('why', '-'), tn))} |"
        )
    if not fdefs:
        L.append("| (none) | - | - |")
    L += ["", "## Navigation", ""]
    tabs = spec.get("tabs") or []
    if tabs:
        L.append(
            "Tabs: "
            + " · ".join(
                f"{_md(tone(t['label'], tn))} (`{t['screen']}`, icon {t['icon']})" for t in tabs
            )
        )
        L.append("")
    edges = []
    for s in spec["screens"]:
        v = next(x for x in s["variants"] if x["id"] == ch["variants"][s["id"]])
        for b in v["blocks"] + (s.get("states") or {}).get("empty", []):
            for a in actions_in(b):
                if "go" in a:
                    edges.append(f"- `{s['id']}` → `{a['go']}`")
                if "sheet" in a:
                    edges.append(f"- `{s['id']}` ⇢ sheet `{a['sheet']}`")
    for sh in spec.get("sheets") or []:
        for b in sh["blocks"]:
            for a in actions_in(b):
                if "go" in a:
                    edges.append(f"- sheet `{sh['id']}` → `{a['go']}`")
                if "sheet" in a:
                    edges.append(f"- sheet `{sh['id']}` ⇢ sheet `{a['sheet']}`")
    L += list(dict.fromkeys(edges)) or ["- (no links)"]
    tab_ids = {t["screen"] for t in tabs}
    for s in spec["screens"]:
        vid = ch["variants"][s["id"]]
        v = next(x for x in s["variants"] if x["id"] == vid)
        others = [f"{_md(tone(x['label'], tn))} (`{x['id']}`)" for x in s["variants"] if x["id"] != vid]
        L += [
            "",
            f"## Screen: {_md(tone(s['title'], tn))} (`{s['id']}`)"
            + (" · tab" if s["id"] in tab_ids else ""),
            "",
            f"Layout: **{_md(tone(v['label'], tn))}** (`{vid}`)"
            + (f"; not chosen: {', '.join(others)}" if others else ""),
            "",
        ]
        L += _block_table(v["blocks"], ch, fdefs)
        empty = (s.get("states") or {}).get("empty")
        L += ["", "States: default (above)" + ("; **empty**:" if empty else "; no empty state")]
        if empty:
            L += [""] + _block_table(empty, ch, fdefs)
    for sh in spec.get("sheets") or []:
        L += [
            "",
            f"## Sheet: {_md(tone(sh['title'], tn))} (`{sh['id']}`)",
            "",
            "Presented as a formSheet route (`SheetHeader`, `closeSheet()`).",
            "",
        ]
        L += _block_table(sh["blocks"], ch, fdefs)
    L += _icons_table(spec, ch)
    L += _platform_and_motion(spec, ch)
    return "\n".join(L) + "\n"


def _type_row(ch: dict) -> str:
    f = ch.get("font") or {}
    if not f.get("display"):
        return "| Type | direction default |"
    which = "direction default" if f.get("pairing", "default") == "default" else f"pairing `{f['pairing']}`"
    return (
        f"| Type | display {_md(f['display'])}, body {_md(f['body'])}, mono {_md(f['mono'])} "
        f"({which}; register each weight in `mobile/lib/fonts.ts`) |"
    )


def _platform_and_motion(spec: dict, ch: dict) -> list[str]:
    """How the prototype's chrome and motion become native code. The prototype is
    HTML imitating the platform; these rows say which native piece does it for real."""
    frozen = frozen_tokens(spec, ch)
    m, at = frozen["motion"], frozen["atmosphere"]
    dur, ease = m["duration"], m.get("easing", {})
    enter = ease.get("enter", [])
    bouncy = ch["temperature"] == "lively"
    return [
        "",
        "## Platform (what the prototype imitates, built natively)",
        "",
        "| Prototype | Build with | Notes |",
        "|---|---|---|",
        "| Tab bar | `NativeTabs` + `NativeTabs.Trigger` (expo-router) | Liquid Glass on iOS 26, "
        "Material 3 on Android; icons from the Icons table |",
        "| Pushed screen | a Stack route (`router.push`) | the platform's own push transition |",
        "| Sheet | a `presentation: \"formSheet\"` route + `SheetHeader` | "
        "`sheetAllowedDetents: \"fitToContents\"` (or up to 3 detents), grabber on iOS |",
        "| Segmented control | `SegmentedControl` | @expo/ui native control on iOS / Android; "
        "themed on web |",
        "| Image | `Media` | expo-image; the placeholder until a real source exists |",
        "| Toast | `useToast()` | one at a time, above the tab bar |",
        "",
        "## Motion (frozen from the prototype's feel)",
        "",
        f"Temperature **{ch['temperature']}**: design/tokens.json → `motion` already carries it "
        "(durations, press scale, enter curve, spring damping), so these calls reproduce what "
        "the founder clicked. Every one honours reduce motion.",
        "",
        "| Prototype motion | Build with (`lib/motion.ts`, `components/ui`) | Frozen value |",
        "|---|---|---|",
        f"| Content rises in, staggered | `entering={{entrance(i)}}` (`Card index={{i}}`) | "
        f"{dur.get('deliberate')}ms, curve `enter` {enter}, 45ms step |",
        f"| Press feedback | `PressableScale` / `Button` (scale + haptic) | "
        f"scale {m.get('pressScale')} |",
        f"| Selection moves (chips, thumb) | `springTo(x, \"snappy\")` | "
        f"damping {m.get('spring', {}).get('snappy', {}).get('damping')}"
        f"{' (overshoots)' if bouncy else ''} |",
        f"| Progress fills | `ProgressBar` (scaleX, UI thread) | {dur.get('deliberate')}ms, curve `enter` |",
        f"| Toast in / out | `useToast()` (FadeInUp / fade out) | {dur.get('screen')}ms in |",
        "| Number counts up | `AnimatedNumber` / `StatCard` | static under reduce motion |",
        "| Payoff moment | `Celebration` + `haptic.success()` | the core loop's reward only |",
        "| Screen change (blur-rise, overlapping) | the Stack transition + `entrance(i)` | "
        "spring `gentle`, critically damped: arrives without overshoot |",
        "",
        f"Atmosphere **{at['mode']}**, intensity {at['intensity']}, grain {'on' if at['grain'] else 'off'}, "
        f"{at['surface']} surfaces: design/tokens.json → `atmosphere` carries the two light colours "
        f"and the contrast-capped alpha per mode (light {at['color']['light']['alpha']}, "
        f"dark {at['color']['dark']['alpha']}). Paint it behind every screen, never over text.",
        "",
        "Haptics follow the commitment ladder in `lib/motion.ts`: selection for chips and "
        "segments, medium for the primary action, success for the payoff.",
    ]


def _icons_used(spec: dict, ch: dict) -> list[str]:
    used = [t["icon"] for t in spec.get("tabs") or []]
    blocks = [b for sh in spec.get("sheets") or [] for b in sh["blocks"]]
    for s in spec["screens"]:
        v = next(x for x in s["variants"] if x["id"] == ch["variants"][s["id"]])
        blocks += v["blocks"] + (s.get("states") or {}).get("empty", [])
    for b in blocks:
        if b.get("feature") and not ch["features"][b["feature"]]:
            continue
        used += [b["icon"]] if "icon" in b else []
        used += [i["icon"] for i in b.get("items") or [] if "icon" in i]
    return list(dict.fromkeys(used))


def _icons_table(spec: dict, ch: dict) -> list[str]:
    used = _icons_used(spec, ch)
    if not used:
        return []
    native = icon_native()
    L = [
        "",
        "## Icons",
        "",
        "Every icon the frozen screens use, as `<Icon sf=… md=… />` props",
        "(`components/ui/Icon.tsx`).",
        "",
        "| Prototype | `sf` (iOS) | `md` (Android, web) |",
        "|---|---|---|",
    ]
    return L + [f"| {n} | `{native[n][0]}` | `{native[n][1]}` |" for n in used]


def freeze(spec: dict, choices: dict, target: Path) -> int:
    ch, errs = resolve_choices(spec, choices)
    if errs:
        for e in errs:
            print(e)
        return 1
    tokens = frozen_tokens(spec, ch)
    bad = cc.check(tokens) + [f"design: {e}" for e in dc.check(tokens)]
    if bad:
        for e in bad:
            print(f"tokens: contrast: {e}")
        return 1
    files = {
        target / "design" / "tokens.json": json.dumps(tokens, indent=2) + "\n",
        target / "docs" / "product" / "SCREENS.md": screens_md(spec, ch),
        target / "design" / "choices.json": json.dumps(ch, indent=2) + "\n",
    }
    # Stage every file first, then rename them into place, so a failure (a target that
    # is a file, a read-only dir) leaves the previous freeze intact, never half of one.
    staged = []
    try:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
            with os.fdopen(fd, "w") as f:
                f.write(text)
            staged.append((tmp, path))
    except OSError as e:
        for tmp, _ in staged:
            os.unlink(tmp)
        print(f"freeze: cannot write under {target}: {e}")
        return 1
    for tmp, path in staged:
        os.replace(tmp, path)
        print(f"wrote {path}")
    return 0


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="write the self-contained prototype HTML")
    r.add_argument("spec")
    r.add_argument("out")
    c = sub.add_parser("check", help="lint the spec; one line per problem")
    c.add_argument("spec")
    f = sub.add_parser("freeze", help="write tokens.json, SCREENS.md, choices.json")
    f.add_argument("spec")
    f.add_argument("choices")
    f.add_argument("--target", required=True, help="repo root to write into")
    fl = sub.add_parser("fonts", help="check the type library (and the archetype table)")
    fl.add_argument("--library", default=str(FONT_LIBRARY))
    fl.add_argument("--skill", default=str(DIRECTIONS_SKILL))
    a = ap.parse_args(argv)
    if a.cmd == "fonts":
        try:
            lib, skill = load_json(a.library), Path(a.skill).read_text()
        except (OSError, json.JSONDecodeError) as e:
            print(f"fonts: cannot read: {e}")
            return 1
        errs = library_errors(lib, skill)
        for e in errs:
            print(e)
        if errs:
            print(f"type library check FAILED: {len(errs)} problem(s)")
            return 1
        print(
            f"type library check passed ({len(lib['families'])} families, "
            f"{len(lib['pairings'])} pairings, all OFL-1.1)"
        )
        return 0
    try:
        spec = load_json(a.spec)
    except (OSError, json.JSONDecodeError) as e:
        print(f"{a.spec}: cannot read spec: {e}")
        return 1
    problems = check(spec)
    if a.cmd == "check":
        for line in problems:
            print(line)
        if problems:
            print(f"prototype check FAILED: {len(problems)} problem(s)")
            return 1
        n_var = sum(len(s["variants"]) for s in spec["screens"])
        print(
            f"prototype check passed ({len(spec['screens'])} screens, {n_var} variants, "
            f"{len(spec.get('sheets') or [])} sheets, {len(spec['directions'])} directions)"
        )
        return 0
    if a.cmd == "render":
        # Render a work-in-progress spec (lints are warnings), but never a malformed one.
        schema: list[str] = []
        _schema(spec, schema)
        if schema:
            for line in schema:
                print(line)
            print(f"refusing to render: {len(schema)} schema error(s)")
            return 1
        for line in problems:
            print(f"warning: {line}")
        render(spec, a.out)
        print(f"wrote {a.out}")
        return 0
    if problems:
        for line in problems:
            print(line)
        print(f"refusing to freeze: fix the {len(problems)} problem(s) `check` reports first")
        return 1
    try:
        choices = load_json(a.choices)
    except (OSError, json.JSONDecodeError) as e:
        print(f"{a.choices}: cannot read choices: {e}")
        return 1
    return freeze(spec, choices, Path(a.target))


if __name__ == "__main__":
    sys.exit(main())
