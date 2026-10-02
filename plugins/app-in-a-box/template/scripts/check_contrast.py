#!/usr/bin/env python3
"""Validate design/tokens.json: schema + WCAG 2.1 contrast, for EVERY colour mode.

Tokens v2 carry two palettes, `color.light` and `color.dark`. Both are checked with
the same rules, so a theme can't pass in the mode the designer looked at and fail in
the one they didn't. The v1 shape (a single flat `color` map plus `mode`) is still
accepted and checked as that one mode.

Rules per palette (numbers are recomputed from the real hexes, never hand-typed):
  - text:     every token the component library paints as `color:` >= 4.5:1 on EVERY
              surface text can sit on (bg, surface, surfaceRaised, control). That set
              is the ink ramp (ink, inkDim, inkFaint) plus accent and danger: a ghost
              button's label, a link, an error line. When this file sits in a repo
              with mobile/ beside design/, the set is READ from the components
              (components/ui/Text.tsx TONE, components/ui/Button.tsx INK, lib/theme.ts
              TONE_FOR_ROLE) and unioned with that default, so adding a tone to <Text>
              makes the gate check it; a token file checked on its own uses the default.
  - accent:   onAccent >= 4.5:1 on accent (button labels)
  - non-text: accent, success, warning, danger >= 3:1 on every surface (icons, dots,
              borders, focus rings; WCAG 1.4.11). success and warning are NOT text
              tokens: a success message is ink with a glyph, never green text.
Schema: both palettes have the same keys and every required key; each hex is #RRGGBB;
`motion`, `type`, `elevation`, `opacity` (when present) are well-formed.

Usage: check_contrast.py design/tokens.json      exit 0 pass, 1 fail, 2 usage

One implementation: this file ships in every generated repo (scripts/) and the kit
imports it, so the renderer, the prototype and the generated repo's gate can't drift.
Standard library only; runs on Python 3.9+.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

INKS = ("ink", "inkDim", "inkFaint")
SURFACES = ("bg", "surface", "surfaceRaised", "control")
STATUS = ("success", "warning", "danger")
REQUIRED = (*SURFACES, "border", *INKS, "accent", "onAccent", *STATUS)
MODES = ("light", "dark")
AA, NON_TEXT = 4.5, 3.0
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
TYPE_ROLES = ("display", "title", "heading", "body", "secondary", "meta", "mono")
# Tokens the shipped components paint as text. `text_tokens()` widens this from the
# component source when it is available; it never narrows it.
DEFAULT_TEXT = (*INKS, "accent", "danger")
# Tokens that only ever carry meaning as graphics (icon, dot, border, ring).
NON_TEXT_TOKENS = ("accent", *STATUS)

# Where the components declare which palette key they paint as `color:`.
_COMPONENT_MAPS = (
    ("components/ui/Text.tsx", r"const TONE\b[^=]*=\s*\{(.*?)\};"),
    ("components/ui/Button.tsx", r"const INK\b[^=]*=\s*\{(.*?)\};"),
    ("lib/theme.ts", r"const TONE_FOR_ROLE\b[^=]*=\s*\{(.*?)\};"),
)


def _lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_: str) -> float:
    h = hex_.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #RRGGBB, got {hex_!r}")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def palettes(tokens: dict) -> dict[str, dict]:
    """{mode: palette}. v2 -> both modes; v1 (flat `color`) -> just its `mode`.

    Shared with render.py so the renderer and the gate can never disagree on shape.
    """
    color = tokens.get("color", {})
    if not isinstance(color, dict):
        raise ValueError("`color` must be an object")
    nested = {k: v for k, v in color.items() if isinstance(v, dict)}
    if nested:
        stray = sorted(k for k in color if k not in MODES)
        if stray:
            raise ValueError(
                f"`color` mixes the v2 shape (light/dark) with top-level keys {stray}; "
                "put every colour inside color.light and color.dark"
            )
        return {m: color[m] for m in MODES if m in color}
    return {tokens.get("mode", "dark"): color}


def text_tokens(tokens_path: Path | str | None) -> tuple[str, ...]:
    """The palette keys painted as text: DEFAULT_TEXT plus whatever the component
    library beside `tokens_path` maps a tone/variant to. Missing files add nothing."""
    found = set(DEFAULT_TEXT)
    if tokens_path is None:
        return DEFAULT_TEXT
    mobile = Path(tokens_path).resolve().parent.parent / "mobile"
    for rel, pattern in _COMPONENT_MAPS:
        src = mobile / rel
        if not src.is_file():
            continue
        m = re.search(pattern, src.read_text(), re.S)
        if not m:
            continue
        found.update(re.findall(r':\s*"(\w+)"', m.group(1)))
    found.discard("onAccent")  # checked against accent, not against the surfaces
    return tuple(sorted(found))


def _schema(tokens: dict, pals: dict[str, dict]) -> list[str]:
    errs: list[str] = []
    is_v2 = any(isinstance(v, dict) for v in tokens.get("color", {}).values())
    if is_v2:
        for m in MODES:
            if m not in pals:
                errs.append(f"color.{m} is missing (tokens v2 need both light and dark)")
        if len(pals) == 2 and set(pals["light"]) != set(pals["dark"]):
            diff = sorted(set(pals["light"]) ^ set(pals["dark"]))
            errs.append(f"color.light and color.dark have different keys: {diff}")
    for m, pal in pals.items():
        for key in REQUIRED:
            if key not in pal:
                errs.append(f"color.{m}.{key} is missing")
        for key, val in pal.items():
            if not isinstance(val, str) or not HEX.match(val):
                errs.append(f"color.{m}.{key} must be #RRGGBB, got {val!r}")
    motion = tokens.get("motion")
    if motion is not None:
        for name, ms in motion.get("duration", {}).items():
            if not isinstance(ms, int) or not 0 <= ms <= 5000:
                errs.append(f"motion.duration.{name} must be an int of ms in 0..5000")
        for name, pts in motion.get("easing", {}).items():
            if not (
                isinstance(pts, list)
                and len(pts) == 4
                and all(isinstance(x, (int, float)) for x in pts)
            ):
                errs.append(f"motion.easing.{name} must be a cubic-bezier [x1, y1, x2, y2]")
            elif not (0 <= pts[0] <= 1 and 0 <= pts[2] <= 1):
                errs.append(f"motion.easing.{name}: x1 and x2 must be within 0..1")
        for name, cfg in motion.get("spring", {}).items():
            for k in ("damping", "stiffness", "mass"):
                if not isinstance(cfg.get(k), (int, float)) or cfg[k] <= 0:
                    errs.append(f"motion.spring.{name}.{k} must be a positive number")
    type_ = tokens.get("type")
    if type_ is not None:
        for role in TYPE_ROLES:
            spec = type_.get(role)
            if not isinstance(spec, dict):
                errs.append(f"type.{role} is missing")
                continue
            for k in ("size", "lineHeight"):
                if not isinstance(spec.get(k), (int, float)) or spec[k] <= 0:
                    errs.append(f"type.{role}.{k} must be a positive number")
            if isinstance(spec.get("size"), (int, float)) and isinstance(
                spec.get("lineHeight"), (int, float)
            ):
                if spec["lineHeight"] < spec["size"]:
                    errs.append(f"type.{role}.lineHeight < size clips descenders")
            if spec.get("font", "body") not in tokens.get(
                "font", {"display": 1, "body": 1, "mono": 1}
            ):
                errs.append(f"type.{role}.font must name a key of `font`")
            if "maxScale" in spec and not (
                isinstance(spec["maxScale"], (int, float)) and spec["maxScale"] >= 1
            ):
                errs.append(
                    f"type.{role}.maxScale must be >= 1 (it caps Dynamic Type, never shrinks)"
                )
    for name, val in (tokens.get("opacity") or {}).items():
        if not isinstance(val, (int, float)) or not 0 <= val <= 1:
            errs.append(f"opacity.{name} must be within 0..1")
    for name, spec in (tokens.get("elevation") or {}).items():
        if not isinstance(spec, dict) or not isinstance(spec.get("elevation", 0), (int, float)):
            errs.append(f"elevation.{name} must be an object with numeric fields")
    return errs


def _contrast(mode: str, pal: dict, text: tuple[str, ...] = DEFAULT_TEXT) -> list[str]:
    rules: list[tuple[str, str, float, str]] = [(t, s, AA, "text") for t in text for s in SURFACES]
    rules.append(("onAccent", "accent", AA, "text"))
    rules += [(nt, s, NON_TEXT, "non-text") for nt in NON_TEXT_TOKENS for s in SURFACES if nt not in text]
    out = []
    for fg, bg, floor, kind in rules:
        if (
            fg not in pal
            or bg not in pal
            or not HEX.match(str(pal[fg]))
            or not HEX.match(str(pal[bg]))
        ):
            continue  # reported by the schema pass
        r = ratio(pal[fg], pal[bg])
        if r < floor:
            out.append(f"[{mode}] {fg} {pal[fg]} on {bg} {pal[bg]} = {r:.2f}:1 (< {floor} for {kind})")
    return out


def check(tokens: dict, text: tuple[str, ...] = DEFAULT_TEXT) -> list[str]:
    try:
        pals = palettes(tokens)
    except ValueError as e:
        return [str(e)]
    failures = _schema(tokens, pals)
    for mode, pal in pals.items():
        failures += _contrast(mode, pal, text)
    return failures


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 2
    path = args[0]
    with open(path) as f:
        tokens = json.load(f)
    text = text_tokens(path)
    failures = check(tokens, text)
    if failures:
        print("Contrast check FAILED:")
        for line in failures:
            print(f"  - {line}")
        return 1
    parts = []
    for mode, pal in palettes(tokens).items():
        worst = min(ratio(pal[t], pal[s]) for t in text for s in SURFACES)
        parts.append(f"{mode} worst text/surface {worst:.2f}:1")
    print(f"Contrast check passed (text tokens: {', '.join(text)}; " + "; ".join(parts) + ").")
    return 0


if __name__ == "__main__":
    sys.exit(main())
