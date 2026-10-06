#!/usr/bin/env python3
"""Colour by construction: a full tokens v2 palette (light AND dark) from one accent
and one neutral hue.

Every colour is a tone of an HCT tonal palette (scripts/hct.py, ported from Google's
material-color-utilities). Tone is CIE L*, and WCAG contrast depends only on
luminance, so a text colour and the surfaces it sits on are chosen as tones far enough
apart to clear the rule whatever the hue: about 50 tones buys 4.5:1. The tone table
below keeps every text pair the contrast gate checks 51 or more apart (at least 5:1),
and icons further than their 3:1 needs, so the derived palette passes check_contrast.py
on the first try, for any accent. That is what lets a designer pick the hue freely
and stop nudging lightness by hand.

What it derives, per mode:
  neutrals   bg < surface < surfaceRaised step toward the viewer (DOWN in light, UP in
             dark, where shadows vanish), control, border, shadow: all tinted toward
             the neutral hue at a low chroma, never pure grey
  ink ramp   ink, inkDim, inkFaint from the neutral palettes
  accent     the accent's hue and chroma, darker in light mode and lighter in dark,
             with onAccent at the far end of the same palette
  status     success, warning, danger at fixed hues (green, amber, red), toned the
             same way
An accent that would land on the stock AI violet (check_design.py's reflex-accent)
is turned a few degrees of hue away from it until it clears, and `derive` says so.

    palette.py derive --accent "#BE400C" [--neutral-hue 60] [--neutral-chroma 6]
                      [--into design/tokens.json]
    palette.py ramp   --accent "#BE400C" [--neutral-hue 60]

derive   prints {"light": {...}, "dark": {...}} (paste it as a direction's
         tokens.color), or with --into writes it into that tokens file's `color`,
         keeping every other key. --neutral-hue defaults to the accent's own hue.
ramp     prints each tonal palette at tones 0..100, for picking by eye.

A prototype direction can skip the hexes: `"palette": {"accent": "#BE400C",
"neutralHue": 60}` and prototype.py derives the colours with this module.

Exit codes: 0 ok, 1 refused, 2 usage. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_design as dc  # noqa: E402  (sibling module; the reflex-accent list)
from hct import Hct, TonalPalette  # noqa: E402

NEUTRAL_CHROMA = 6.0  # Material's neutral chroma: tinted, never loud
NEUTRAL_CHROMA_RANGE = (4.0, 24.0)  # below 4 the darkest tones round to pure grey
VARIANT_CHROMA = 4 / 3  # inkDim, inkFaint and border carry a little more of the hue
STATUS = {"success": (150.0, 48.0), "warning": (70.0, 56.0), "danger": (22.0, 72.0)}

# key -> (palette, light tone, dark tone). Palettes: n = neutral, nv = neutral variant,
# a = accent, or a STATUS key. Contrast pairs the gate checks, as tone gaps:
#   inks / accent / danger on bg..control   light >= 52 (5.1:1), dark >= 51 (5.8:1)
#   onAccent on accent                      light 58, dark 62
#   success / warning on bg..control        light >= 49 (3:1 needed), dark >= 61
# Change a tone here and the property test (scripts/tests/test_palette.py) says if a
# pair stopped clearing.
TONES = {
    "bg": ("n", 97, 6),
    "surface": ("n", 99, 10),
    "surfaceRaised": ("n", 100, 14),
    "control": ("n", 94, 17),
    "border": ("nv", 87, 26),
    "ink": ("n", 10, 92),
    "inkDim": ("nv", 30, 80),
    "inkFaint": ("nv", 42, 68),
    "accent": ("a", 42, 72),
    "onAccent": ("a", 100, 10),
    "success": ("success", 42, 78),
    "warning": ("warning", 45, 80),
    "danger": ("danger", 42, 70),
    "shadow": ("n", 5, 0),
}
REFLEX_STEP = 3.0  # degrees of hue per nudge away from the stock violet
REFLEX_MAX = 90.0


def _reflex(hex_: str) -> bool:
    rgb = dc._rgb(hex_)
    return any(
        max(abs(a - b) for a, b in zip(rgb, dc._rgb(ref))) <= dc.REFLEX_DISTANCE
        for ref in dc.REFLEX_ACCENTS
    )


def accent_palette(accent: str) -> tuple[TonalPalette, float]:
    """The accent's tonal palette, and the hue it was asked for. The palette's hue
    differs only when the asked-for one would put an accent tone on the stock violet."""
    src = Hct.from_hex(accent)
    for step in range(int(REFLEX_MAX / REFLEX_STEP) + 1):
        for sign in ((1, -1) if step else (1,)):
            pal = TonalPalette(
                (src.hue + sign * step * REFLEX_STEP) % 360.0, src.chroma
            )
            if not any(_reflex(pal.hex(TONES["accent"][i])) for i in (1, 2)):
                return pal, src.hue
    raise ValueError(f"no hue near {accent} clears the stock AI violet")  # unreachable


def derive_palette(
    accent: str,
    neutral_hue: float | None = None,
    neutral_chroma: float = NEUTRAL_CHROMA,
) -> dict[str, dict[str, str]]:
    """{"light": {...}, "dark": {...}}: every key check_contrast.py requires, plus
    shadow. Deterministic: the same inputs give the same hexes."""
    if not (isinstance(accent, str) and dc.HEX.match(accent)):
        raise ValueError(f"accent must be #RRGGBB, got {accent!r}")
    lo, hi = NEUTRAL_CHROMA_RANGE
    if not lo <= neutral_chroma <= hi:
        raise ValueError(
            f"neutral chroma must be within {lo:g}..{hi:g}, got {neutral_chroma!r}"
        )
    a, _ = accent_palette(accent)
    nh = a.hue if neutral_hue is None else float(neutral_hue) % 360.0
    pals = {
        "a": a,
        "n": TonalPalette(nh, neutral_chroma),
        "nv": TonalPalette(nh, neutral_chroma * VARIANT_CHROMA),
        **{k: TonalPalette(h, c) for k, (h, c) in STATUS.items()},
    }
    return {
        mode: {key: pals[p].hex(tones[i]) for key, (p, *tones) in TONES.items()}
        for i, mode in enumerate(("light", "dark"))
    }


def nudged(accent: str) -> tuple[float, float] | None:
    """(asked-for hue, used hue) when derive turned the accent off the stock violet."""
    pal, asked = accent_palette(accent)
    return None if abs(pal.hue - asked) < 1e-9 else (asked, pal.hue)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="palette.py", description=__doc__.split("\n\n")[0]
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("derive", "ramp"):
        p = sub.add_parser(name)
        p.add_argument("--accent", required=True, help="#RRGGBB, the brand accent")
        p.add_argument(
            "--neutral-hue",
            type=float,
            default=None,
            help="0..360 (default: the accent's)",
        )
        p.add_argument("--neutral-chroma", type=float, default=NEUTRAL_CHROMA)
        if name == "derive":
            p.add_argument("--into", help="a tokens.json whose `color` to replace")
    args = ap.parse_args(argv)
    try:
        pal = derive_palette(args.accent, args.neutral_hue, args.neutral_chroma)
    except ValueError as e:
        print(f"palette.py: {e}", file=sys.stderr)
        return 1
    turn = nudged(args.accent)
    if turn:
        print(
            f"palette.py: accent hue {turn[0]:.0f} sits on the stock AI violet; "
            f"used hue {turn[1]:.0f} instead",
            file=sys.stderr,
        )
    if args.cmd == "ramp":
        a, _ = accent_palette(args.accent)
        nh = a.hue if args.neutral_hue is None else args.neutral_hue
        rows = {"accent": a, "neutral": TonalPalette(nh, args.neutral_chroma)}
        rows.update({k: TonalPalette(h, c) for k, (h, c) in STATUS.items()})
        for name, tp in rows.items():
            print(
                f"{name:8} " + " ".join(f"{t}:{tp.hex(t)}" for t in range(0, 101, 10))
            )
        return 0
    if args.into:
        path = Path(args.into)
        try:
            tokens = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"palette.py: cannot read {path}: {e}", file=sys.stderr)
            return 1
        tokens["color"] = pal
        path.write_text(json.dumps(tokens, indent=2) + "\n")
        print(f"palette.py: wrote color.light and color.dark into {path}")
        return 0
    print(json.dumps(pal, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
