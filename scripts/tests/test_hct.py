"""The HCT port (plugins/app-in-a-box/scripts/hct.py) against upstream's own tests.

Every expected value below is copied from material-color-utilities' TypeScript test
suite at commit 5b3618b (Apache-2.0, Google LLC):
  typescript/hct/hct_test.ts          'CAM to ARGB', 'CAM to ARGB to CAM', 'ARGB to
                                      HCT', 'viewing conditions', 'CamSolver'
  typescript/palettes/palettes_test.ts  'TonalPalette' (blue), 'CorePalette' a2 (blue)
  typescript/hct/hct_solver.ts        the CRITICAL_PLANES table's ends
Tolerances follow upstream: toBeCloseTo(x, 3) is |diff| < 0.0005, (x, 2) is < 0.005.

Run: python3 -m unittest discover -s scripts/tests       (stdlib only)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "plugins" / "app-in-a-box" / "scripts")
)
import hct  # noqa: E402

RED, GREEN, BLUE, WHITE, BLACK = 0xFF0000, 0x00FF00, 0x0000FF, 0xFFFFFF, 0x000000


class Cam16Reference(unittest.TestCase):
    # hct_test.ts, describe('CAM to ARGB'): hue, chroma, j, m, s, q
    CASES = {
        RED: (27.408, 113.358, 46.445, 89.494, 91.890, 105.989),
        GREEN: (142.140, 108.410, 79.332, 85.588, 78.605, 138.520),
        BLUE: (282.788, 87.231, 25.466, 68.867, 93.675, 78.481),
        WHITE: (209.492, 2.869, 100.0, 2.265, 12.068, 155.521),
        BLACK: (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    }

    def test_cam_from_int(self) -> None:
        for argb, want in self.CASES.items():
            cam = hct.Cam16.from_int(argb)
            got = (cam.hue, cam.chroma, cam.j, cam.m, cam.s, cam.q)
            for name, g, w in zip(("hue", "chroma", "j", "m", "s", "q"), got, want):
                self.assertLess(abs(g - w), 0.0005, f"{argb:06X} {name}: {g} != {w}")

    def test_cam_round_trip(self) -> None:  # describe('CAM to ARGB to CAM')
        for argb in (RED, GREEN, BLUE):
            self.assertEqual(hct.Cam16.from_int(argb).to_int(), argb)

    def test_default_viewing_conditions(self) -> None:  # describe('viewing conditions')
        vc = hct.DEFAULT_VC
        got = (
            vc.n,
            vc.aw,
            vc.nbb,
            vc.ncb,
            vc.c,
            vc.nc,
            *vc.rgb_d,
            vc.fl,
            vc.fl_root,
            vc.z,
        )
        want = (
            0.184,
            29.981,
            1.017,
            1.017,
            0.69,
            1.0,
            1.021,
            0.986,
            0.934,
            0.388,
            0.789,
            1.909,
        )
        for g, w in zip(got, want):
            self.assertLess(abs(g - w), 0.0005, (got, want))


class HctReference(unittest.TestCase):
    def test_argb_to_hct(self) -> None:  # describe('ARGB to HCT')
        for argb, want in (
            (GREEN, (142.139, 108.410, 87.737)),
            (BLUE, (282.788, 87.230, 32.302)),
        ):
            h = hct.Hct(argb)
            for g, w in zip((h.hue, h.chroma, h.tone), want):
                self.assertLess(abs(g - w), 0.005, (argb, g, w))

    def test_blue_tone_90(self) -> None:
        h = hct.Hct.from_hct(282.788, 87.230, 90.0)
        for g, w in zip((h.hue, h.chroma, h.tone), (282.239, 19.144, 90.035)):
            self.assertLess(abs(g - w), 0.005, (g, w))

    def test_solver_returns_a_sufficiently_close_color(
        self,
    ) -> None:  # describe('CamSolver')
        def on_boundary(c: int) -> bool:
            return any(v in (0, 255) for v in hct.rgb_from_int(c))

        for hue in range(15, 360, 30):
            for chroma in range(0, 101, 10):
                for tone in range(20, 81, 10):
                    h = hct.Hct.from_hct(hue, chroma, tone)
                    if chroma > 0:
                        self.assertLessEqual(abs(h.hue - hue), 4.0)
                    self.assertTrue(0 <= h.chroma <= chroma + 2.5)
                    if h.chroma < chroma - 2.5:
                        self.assertTrue(on_boundary(h.argb), (hue, chroma, tone))
                    self.assertLessEqual(abs(h.tone - tone), 0.5)

    def test_critical_planes_match_upstream_table(self) -> None:
        self.assertEqual(len(hct.CRITICAL_PLANES), 255)
        self.assertEqual(hct.CRITICAL_PLANES[0], 0.015176349177441876)
        self.assertEqual(hct.CRITICAL_PLANES[1], 0.045529047532325624)
        self.assertEqual(hct.CRITICAL_PLANES[-1], 99.55452497210776)


class TonalPaletteReference(unittest.TestCase):
    TONES = (100, 95, 90, 80, 70, 60, 50, 40, 30, 20, 10, 0)

    def test_blue(self) -> None:  # palettes_test.ts, describe('TonalPalette') 'of blue'
        want = (
            0xFFFFFF,
            0xF1EFFF,
            0xE0E0FF,
            0xBEC2FF,
            0x9DA3FF,
            0x7C84FF,
            0x5A64FF,
            0x343DFF,
            0x0000EF,
            0x0001AC,
            0x00006E,
            0x000000,
        )
        pal = hct.TonalPalette.from_int(BLUE)
        self.assertEqual([pal.tone(t) for t in self.TONES], list(want))

    def test_blue_at_chroma_16(
        self,
    ) -> None:  # 'CorePalette' ofBlue, a2 = hue at chroma 16
        want = (
            0xFFFFFF,
            0xF1EFFF,
            0xE1E0F9,
            0xC5C4DD,
            0xA9A9C1,
            0x8F8FA6,
            0x75758B,
            0x5C5D72,
            0x444559,
            0x2E2F42,
            0x191A2C,
            0x000000,
        )
        pal = hct.TonalPalette(hct.Hct(BLUE).hue, 16.0)
        self.assertEqual([pal.tone(t) for t in self.TONES], list(want))


if __name__ == "__main__":
    unittest.main()
