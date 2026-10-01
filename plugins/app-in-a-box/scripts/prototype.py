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

render   one HTML file: phone frame (390x844), working navigation, tabs, sheets,
         toasts, per-screen states, and a control panel (direction, light/dark,
         density, temperature, tone, per-screen variant, feature toggles, screen
         map, annotations, "Copy my choices"). Inline CSS/JS; Google Fonts only.
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
         features: {id: bool}}, and writes under --target:
           design/tokens.json       the chosen direction, density + temperature applied
           docs/product/SCREENS.md  per screen: chosen variant -> components/ui, nav
                                    graph, states, features in/out of v1
           design/choices.json      every selection, resolved (no gaps)

A direction's `tokens` is a tokens v2 object. Its `color` must be complete (light AND
dark); any other top-level key it leaves out (type, space, elevation...) is taken from
template/design/tokens.json, so the frozen file always has every key.

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
        "enter": [0.34, 1.56, 0.64, 1],
        "damping": 0.75,  # springs overshoot a little, like the prototype's pop
    },
}
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
    "header": "Meta + Title + Body",
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
    """The direction's tokens over the template's (colour is never inherited)."""
    base = load_json(str(TEMPLATE_TOKENS))
    base.pop("color", None)
    base.pop("$schema", None)
    return deep_merge(base, direction.get("tokens") or {})


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
        if not (isinstance(col, dict) and all(isinstance(col.get(m), dict) for m in MODES)):
            p.append(f"{w}.tokens.color: needs both color.light and color.dark (tokens v2)")
        else:
            for m in MODES:
                for k in cc.REQUIRED:
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
    for mode in MODES:
        pal = t["color"][mode]
        cv = [f"--{_kebab(k)}: {val};" for k, val in pal.items()]
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
    return "\n".join(out)


def google_fonts(spec: dict) -> str:
    fams = []
    for d in spec["directions"]:
        for fam in (merged_tokens(d).get("font") or {}).values():
            if fam not in SYSTEM_FONTS and fam not in MONO_FONTS and fam not in fams:
                fams.append(fam)
    if not fams:
        return ""
    links = [
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
    ]
    for fam in fams:  # one link per family: a family missing a weight can't sink the rest
        q = fam.replace(" ", "+")
        links.append(
            f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
            f'family={q}:wght@400;500;600;700&amp;display=swap">'
        )
    return "\n".join(links)


# ---------------------------------------------------------------- render


def _rev(spec: dict) -> str:
    """Fingerprint of what saved choices could override: defaults and the features."""
    basis = [spec.get("defaults"), [[f.get("id"), f.get("default")] for f in spec.get("features") or []]]
    return hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()[:12]


def _script_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")


def render(spec: dict, out: str) -> None:
    css = "\n".join([feel_css()] + [direction_css(d) for d in spec["directions"]])
    parts = {
        "TITLE": html.escape(tone(spec["app"]["name"]) + " prototype"),
        "FONTS": google_fonts(spec),
        "CSS": "\n".join((PROTO / f).read_text() for f in ("page.css", "phone.css")) + "\n" + css,
        "SPEC": _script_json(spec),
        "CONFIG": _script_json(
            {
                "icons": load_json(str(PROTO / "icons.json"))["icons"],
                "density": list(DENSITY),
                "temperature": list(TEMPERATURE),
                "components": COMPONENTS,
                "rev": _rev(spec),
                "palettes": {d["id"]: merged_tokens(d)["color"] for d in spec["directions"]},
                "fonts": {
                    d["id"]: merged_tokens(d).get("font", {}).get("display", "System")
                    for d in spec["directions"]
                },
            }
        ),
        "JS": "\n".join((PROTO / f).read_text() for f in ("blocks.js", "panel.js", "runtime.js")),
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
    allowed = {"direction", "mode", "density", "temperature", "tone", "variants", "features"}
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
    return out, errs


def frozen_tokens(spec: dict, ch: dict) -> dict:
    d = next(x for x in spec["directions"] if x["id"] == ch["direction"])
    t = merged_tokens(d)
    t = {"$schema": load_json(str(TEMPLATE_TOKENS)).get("$schema", ""), **t}
    t["name"], t["version"], t["mode"] = d["id"], 2, ch["mode"]
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
    t["color"] = {m: temper(t["color"][m], ch["temperature"], m) for m in MODES}
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
        return "<Meta> + <Title> + <Body dim>" if "subtitle" in b else "<Meta> + <Title>"
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


def _platform_and_motion(spec: dict, ch: dict) -> list[str]:
    """How the prototype's chrome and motion become native code. The prototype is
    HTML imitating the platform; these rows say which native piece does it for real."""
    m = frozen_tokens(spec, ch)["motion"]
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
    bad = cc.check(tokens)
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
    a = ap.parse_args(argv)
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
