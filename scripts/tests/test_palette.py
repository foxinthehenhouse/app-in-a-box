"""Property test for scripts/palette.py: colour by construction holds for any accent.

Twenty seeded random (accent, neutral hue, neutral chroma) triples each derive a full
tokens v2 palette, which goes into a copy of the template's tokens and through the
real gates as the app runs them: check_contrast.py and check_design.py, by CLI, on the
first try. Neither may fail, so neither the contrast rules nor the reflex-violet /
untinted-grey tells fire on a derived palette.

Run: python3 -m unittest discover -s scripts/tests       (stdlib only)
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[2] / "plugins" / "app-in-a-box"
sys.path.insert(0, str(KIT / "scripts"))
import check_contrast as cc  # noqa: E402
import palette  # noqa: E402

SEEDS = range(20)
# Accents a property run can miss: the stock violet itself, a near-grey, pure
# primaries, near-black and near-white.
EDGE_ACCENTS = (
    "#6366F1",
    "#7C3AED",
    "#808080",
    "#FF0000",
    "#00FF00",
    "#0000FF",
    "#050505",
    "#FAFAFA",
)


def _case(seed: int) -> tuple[str, float | None, float]:
    r = random.Random(seed)
    accent = f"#{r.randrange(1 << 24):06X}"
    hue = (
        None if seed % 4 == 0 else r.uniform(0, 360)
    )  # sometimes default to the accent's
    lo, hi = palette.NEUTRAL_CHROMA_RANGE
    return accent, hue, r.uniform(lo, hi) if seed % 2 else palette.NEUTRAL_CHROMA


class DerivedPalettePassesTheGates(unittest.TestCase):
    def setUp(self) -> None:
        self.base = json.loads(
            (KIT / "template" / "design" / "tokens.json").read_text()
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _gates(self, name: str, color: dict) -> None:
        tokens = dict(self.base, color=color)
        path = Path(self.tmp.name) / f"{name}.json"
        path.write_text(json.dumps(tokens))
        for gate in ("check_contrast.py", "check_design.py"):
            run = subprocess.run(
                [sys.executable, str(KIT / "scripts" / gate), str(path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                run.returncode, 0, f"{name}: {gate} failed:\n{run.stdout}{run.stderr}"
            )

    def test_twenty_random_seeds(self) -> None:
        for seed in SEEDS:
            accent, hue, chroma = _case(seed)
            with self.subTest(
                seed=seed, accent=accent, neutral_hue=hue, neutral_chroma=chroma
            ):
                self._gates(f"seed{seed}", palette.derive_palette(accent, hue, chroma))

    def test_edge_accents(self) -> None:
        for accent in EDGE_ACCENTS:
            with self.subTest(accent=accent):
                self._gates(accent.lstrip("#"), palette.derive_palette(accent))

    def test_shape_and_determinism(self) -> None:
        pal = palette.derive_palette("#BE400C", 60)
        self.assertEqual(set(pal), {"light", "dark"})
        self.assertEqual(set(pal["light"]), set(pal["dark"]))
        self.assertTrue(set(cc.REQUIRED) <= set(pal["light"]))
        self.assertEqual(pal, palette.derive_palette("#BE400C", 60))

    def test_dark_surfaces_step_up_and_light_ones_down(self) -> None:
        pal = palette.derive_palette("#2F7D6B", 150)
        lum = {
            m: [cc.luminance(pal[m][k]) for k in ("bg", "surface", "surfaceRaised")]
            for m in pal
        }
        self.assertEqual(lum["dark"], sorted(lum["dark"]))  # dark: elevation is lighter
        self.assertEqual(
            lum["light"], sorted(lum["light"])
        )  # light: bg sits under white cards

    def test_accent_keeps_its_hue(self) -> None:
        for accent in ("#BE400C", "#2F7D6B", "#1F6FEB", "#C2185B"):
            asked = palette.Hct.from_hex(accent).hue
            for mode in ("light", "dark"):
                got = palette.Hct.from_hex(
                    palette.derive_palette(accent)[mode]["accent"]
                ).hue
                gap = min(abs(got - asked), 360 - abs(got - asked))
                self.assertLess(gap, 4.0, (accent, mode, got, asked))

    def test_stock_violet_is_turned_away_and_said(self) -> None:
        self.assertIsNotNone(palette.nudged("#6366F1"))
        self.assertIsNone(palette.nudged("#BE400C"))

    def test_bad_inputs_refused(self) -> None:
        with self.assertRaises(ValueError):
            palette.derive_palette("orange")
        with self.assertRaises(ValueError):
            palette.derive_palette("#BE400C", 60, 0.0)  # pure grey neutrals


if __name__ == "__main__":
    unittest.main()
