#!/usr/bin/env python3
"""Design-token tells: the generic choices that make an app look machine-made.

Runs against design/tokens.json in `npm run gates`, and the kit runs the same code on
every prototype direction (`prototype.py check`), so a direction that would fail the
app's gate never reaches the founder. Each rule is in docs/design/TASTE.md; the rule
ideas are adapted from Impeccable's anti-pattern detector (Apache-2.0, see TASTE.md).

  overused-font     a named family on the overused list (built-in system fonts are
                    fine: on a phone they're the platform's own voice, not a reflex)
  untinted-greys    bg, surface, surfaceRaised and border all pure grey in a mode
  reflex-accent     an accent within a hair of the stock AI indigo/violet
  overshoot-easing  a cubic-bezier curve that goes past its end (bounce/elastic).
                    Springs may overshoot (they drive presses and selections); the
                    easing curves drive content and screens, which never bounce.

Usage: check_design.py design/tokens.json     exit 0 pass, 1 fail, 2 usage
Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# The families every generator reaches for. Mirrors Impeccable's OVERUSED_FONTS.
OVERUSED_FONTS = {
    "inter",
    "roboto",
    "open sans",
    "lato",
    "montserrat",
    "arial",
    "helvetica",
    "fraunces",
    "instrument sans",
    "instrument serif",
    "geist",
    "geist sans",
    "geist mono",
    "mona sans",
    "plus jakarta sans",
    "space grotesk",
    "recoleta",
}
# Built into the phone, so never "chosen": must equal BUILT_IN_FONTS in mobile/lib/fonts.ts.
BUILT_IN = {"system", "sf pro", "roboto", "menlo", "sf mono", "monospace"}
# Tailwind indigo/violet/purple 500-600: the default accent of generated UI.
REFLEX_ACCENTS = ("#6366F1", "#4F46E5", "#8B5CF6", "#7C3AED", "#A855F7", "#9333EA")
REFLEX_DISTANCE = 24  # max per-channel distance that still counts as "the same colour"
NEUTRALS = ("bg", "surface", "surfaceRaised", "border")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _palettes(tokens: dict) -> dict[str, dict]:
    color = tokens.get("color") or {}
    if any(isinstance(v, dict) for v in color.values()):
        return {m: p for m, p in color.items() if isinstance(p, dict)}
    return {"light": color}


def check(tokens: dict) -> list[str]:
    errs: list[str] = []
    for role, fam in (tokens.get("font") or {}).items():
        if isinstance(fam, str) and fam.lower() not in BUILT_IN and fam.lower() in OVERUSED_FONTS:
            errs.append(
                f"overused-font: font.{role} is {fam!r}, the face every generated app uses. "
                "Pick one from the product's world (TASTE.md, Visual 4)."
            )
    for mode, pal in _palettes(tokens).items():
        greys = [
            k
            for k in NEUTRALS
            if isinstance(pal.get(k), str) and HEX.match(pal[k]) and len(set(_rgb(pal[k]))) == 1
        ]
        if len(greys) == len(NEUTRALS):
            errs.append(
                f"untinted-greys: color.{mode} {', '.join(NEUTRALS)} are all pure grey. "
                "Tint the neutrals toward the brand hue (TASTE.md, Visual 1)."
            )
        acc = pal.get("accent")
        if isinstance(acc, str) and HEX.match(acc):
            for ref in REFLEX_ACCENTS:
                if max(abs(a - b) for a, b in zip(_rgb(acc), _rgb(ref), strict=True)) <= REFLEX_DISTANCE:
                    errs.append(
                        f"reflex-accent: color.{mode}.accent {acc} is the stock AI violet "
                        f"({ref}). Choose a hue from the product's meaning (TASTE.md, Visual 1)."
                    )
                    break
    for name, pts in ((tokens.get("motion") or {}).get("easing") or {}).items():
        if (
            isinstance(pts, list)
            and len(pts) == 4
            and all(isinstance(x, (int, float)) for x in pts)
        ) and not (-0.1 <= pts[1] <= 1.1 and -0.1 <= pts[3] <= 1.1):
            errs.append(
                f"overshoot-easing: motion.easing.{name} {pts} bounces past its end. "
                "Content and screens decelerate; overshoot belongs to springs on small "
                "elements (TASTE.md, Motion)."
            )
    return errs


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: check_design.py design/tokens.json")
        return 2
    try:
        tokens = json.loads(Path(argv[0]).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"{argv[0]}: cannot read tokens: {e}")
        return 2
    errs = check(tokens)
    for e in errs:
        print(e)
    if errs:
        print(f"Design check FAILED: {len(errs)} tell(s)")
        return 1
    print("Design check passed (fonts, neutrals, accent, easing).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
