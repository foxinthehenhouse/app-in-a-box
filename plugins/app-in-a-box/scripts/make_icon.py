#!/usr/bin/env python3
"""Generate the app icon, Android adaptive icon, splash mark and favicon from tokens.

Standard library only (zlib + struct PNG writer), so it runs anywhere the renderer
runs. The mark is the app's initial as a geometric monoline letter (round caps,
analytic anti-aliasing) in `onAccent` on `accent`: the one pair the contrast gate
already guarantees at 4.5:1. It is a good placeholder, not a brand: drop a real
1024x1024 PNG at design/icon.png and the renderer copies that instead.

    make_icon.py --tokens design/tokens.json --out mobile/assets/brand [--glyph L]

Writes icon.png (1024, full bleed; iOS masks the corners), adaptive-icon.png
(1024, transparent, mark inside Android's 66% safe zone), splash-icon.png (1024,
rounded tile, shown by expo-splash-screen at imageWidth) and favicon.png (196).
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import struct
import sys
import zlib
from pathlib import Path

# Glyphs as polylines in a box ~0.9 wide x 1 tall, y down. arc() samples curves.
Seg = list[tuple[float, float]]


def arc(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, n: int = 48) -> Seg:
    return [
        (
            cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
            cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)),
        )
        for i in range(n + 1)
    ]


GLYPHS: dict[str, list[Seg]] = {
    "A": [[(0, 1), (0.42, 0), (0.84, 1)], [(0.16, 0.64), (0.68, 0.64)]],
    "B": [
        [(0.45, 0.5), (0, 0.5), (0, 0), (0.42, 0)],
        arc(0.42, 0.25, 0.25, 0.25, -90, 90),
        [(0, 0.5), (0, 1), (0.46, 1)],
        arc(0.46, 0.75, 0.25, 0.25, -90, 90),
        [(0.42, 0.5), (0.46, 0.5)],
    ],
    "C": [arc(0.47, 0.5, 0.45, 0.5, 45, 315)],
    "D": [[(0.3, 0), (0, 0), (0, 1), (0.3, 1)], arc(0.3, 0.5, 0.5, 0.5, -90, 90)],
    "E": [[(0.72, 0), (0, 0), (0, 1), (0.72, 1)], [(0, 0.5), (0.58, 0.5)]],
    "F": [[(0.72, 0), (0, 0), (0, 1)], [(0, 0.5), (0.58, 0.5)]],
    "G": [arc(0.47, 0.5, 0.45, 0.5, 0, 315), [(0.5, 0.5), (0.92, 0.5)]],
    "H": [[(0, 0), (0, 1)], [(0.76, 0), (0.76, 1)], [(0, 0.5), (0.76, 0.5)]],
    "I": [[(0, 0), (0, 1)]],
    "J": [[(0.62, 0), (0.62, 0.68)], arc(0.31, 0.68, 0.31, 0.32, 0, 180)],
    "K": [[(0, 0), (0, 1)], [(0.72, 0), (0, 0.62)], [(0.26, 0.42), (0.76, 1)]],
    "L": [[(0, 0), (0, 1), (0.66, 1)]],
    "M": [[(0, 1), (0, 0), (0.46, 0.66), (0.92, 0), (0.92, 1)]],
    "N": [[(0, 1), (0, 0), (0.76, 1), (0.76, 0)]],
    "O": [arc(0.47, 0.5, 0.47, 0.5, 0, 360, 64)],
    "P": [[(0, 1), (0, 0), (0.4, 0)], arc(0.4, 0.27, 0.3, 0.27, -90, 90), [(0.4, 0.54), (0, 0.54)]],
    "Q": [arc(0.47, 0.5, 0.47, 0.5, 0, 360, 64), [(0.58, 0.7), (0.94, 1.04)]],
    "R": [
        [(0, 1), (0, 0), (0.4, 0)],
        arc(0.4, 0.27, 0.3, 0.27, -90, 90),
        [(0.4, 0.54), (0, 0.54)],
        [(0.36, 0.54), (0.74, 1)],
    ],
    "S": [arc(0.4, 0.26, 0.36, 0.26, -25, -270), arc(0.4, 0.76, 0.38, 0.24, -90, 155)],
    "T": [[(0, 0), (0.84, 0)], [(0.42, 0), (0.42, 1)]],
    "U": [[(0, 0), (0, 0.6)], arc(0.38, 0.6, 0.38, 0.4, 180, 0), [(0.76, 0.6), (0.76, 0)]],
    "V": [[(0, 0), (0.42, 1), (0.84, 0)]],
    "W": [[(0, 0), (0.24, 1), (0.48, 0.34), (0.72, 1), (0.96, 0)]],
    "X": [[(0, 0), (0.78, 1)], [(0.78, 0), (0, 1)]],
    "Y": [[(0, 0), (0.42, 0.52), (0.84, 0)], [(0.42, 0.52), (0.42, 1)]],
    "Z": [[(0, 0), (0.76, 0), (0, 1), (0.76, 1)]],
}
RING: list[Seg] = [arc(0.5, 0.5, 0.5, 0.5, 0, 360, 64)]  # any glyph we can't draw


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class Canvas:
    def __init__(self, size: int) -> None:
        self.size = size
        self.px = bytearray(size * size * 4)  # RGBA, transparent

    def fill_rounded(self, rgb: tuple[int, int, int], radius_frac: float) -> None:
        s = self.size
        r = radius_frac * s
        for y in range(s):
            for x in range(s):
                if r > 0:
                    dx = max(r - (x + 0.5), 0, (x + 0.5) - (s - r))
                    dy = max(r - (y + 0.5), 0, (y + 0.5) - (s - r))
                    cov = min(1.0, max(0.0, r - math.hypot(dx, dy) + 0.5)) if dx or dy else 1.0
                else:
                    cov = 1.0
                if cov:
                    self._blend(x, y, rgb, cov)

    def stroke(
        self, segs: list[Seg], rgb: tuple[int, int, int], height: float, width: float
    ) -> None:
        """Draw polylines scaled so the glyph is `height` px tall, centred, `width` px strokes."""
        pts = [p for seg in segs for p in seg]
        minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
        miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
        scale = height / max(maxy - miny, 1e-6)
        ox = (self.size - (maxx - minx) * scale) / 2 - minx * scale
        oy = (self.size - (maxy - miny) * scale) / 2 - miny * scale
        cov = [0.0] * (self.size * self.size)
        half = width / 2
        for seg in segs:
            for (x0, y0), (x1, y1) in zip(seg, seg[1:]):
                ax, ay, bx, by = x0 * scale + ox, y0 * scale + oy, x1 * scale + ox, y1 * scale + oy
                vx, vy = bx - ax, by - ay
                ll = vx * vx + vy * vy or 1e-9
                lo_x, hi_x = int(max(0, min(ax, bx) - half - 1)), int(
                    min(self.size, max(ax, bx) + half + 2)
                )
                lo_y, hi_y = int(max(0, min(ay, by) - half - 1)), int(
                    min(self.size, max(ay, by) + half + 2)
                )
                for y in range(lo_y, hi_y):
                    py = y + 0.5
                    row = y * self.size
                    for x in range(lo_x, hi_x):
                        px = x + 0.5
                        t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / ll))
                        d = math.hypot(px - (ax + t * vx), py - (ay + t * vy))
                        c = half - d + 0.5
                        if c > 0:
                            i = row + x
                            if c > cov[i]:
                                cov[i] = min(1.0, c)
        for i, c in enumerate(cov):
            if c:
                self._blend(i % self.size, i // self.size, rgb, c)

    def _blend(self, x: int, y: int, rgb: tuple[int, int, int], a: float) -> None:
        i = (y * self.size + x) * 4
        da = self.px[i + 3] / 255
        oa = a + da * (1 - a)
        for k in range(3):
            src, dst = rgb[k], self.px[i + k]
            self.px[i + k] = round((src * a + dst * da * (1 - a)) / oa) if oa else 0
        self.px[i + 3] = round(oa * 255)

    def png(self) -> bytes:
        s = self.size
        raw = b"".join(b"\x00" + bytes(self.px[y * s * 4 : (y + 1) * s * 4]) for y in range(s))

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", s, s, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )


def grain_png(size: int = 48, seed: int = 7) -> bytes:
    """A tileable film-grain square: greyscale noise around mid-grey, the same every run.
    The app lays it over its atmosphere at a few percent (components/ui/ScreenAtmosphere),
    as the prototype does with its SVG noise."""
    x, rows = seed, []
    for _ in range(size):
        row = bytearray(b"\x00")
        for _ in range(size):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF  # LCG: deterministic, no imports
            row.append(64 + (x >> 16) % 128)
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + kind + data + crc

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def icon_pair(tokens: dict) -> tuple[str, str]:
    """(background, foreground) hexes: accent/onAccent of the default mode's palette."""
    color = tokens.get("color", {})
    pal = color.get(tokens.get("mode", "dark")) if isinstance(color.get("dark"), dict) else color
    pal = pal or next(iter(color.values()))
    return pal["accent"], pal["onAccent"]


def render_icons(tokens: dict, out: Path, glyph: str) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    bg, fg = (hex_rgb(h) for h in icon_pair(tokens))
    segs = GLYPHS.get(glyph.upper()[:1], RING)
    written = []

    def save(
        name: str, size: int, tile_radius: float | None, glyph_h: float, stroke: float
    ) -> None:
        c = Canvas(size)
        if tile_radius is not None:
            c.fill_rounded(bg, tile_radius)
        c.stroke(segs, fg, glyph_h * size, stroke * size)
        (out / name).write_bytes(c.png())
        written.append(str(out / name))

    save("icon.png", 1024, 0.0, 0.44, 0.1)
    save("adaptive-icon.png", 1024, None, 0.3, 0.07)
    save("splash-icon.png", 1024, 0.225, 0.44, 0.1)
    save("favicon.png", 196, 0.225, 0.46, 0.11)
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--tokens", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--glyph", default="")
    p.add_argument(
        "--custom", default="", help="a user-supplied 1024px PNG to use as icon.png instead"
    )
    a = p.parse_args(argv)
    tokens = json.loads(Path(a.tokens).read_text())
    glyph = a.glyph or tokens.get("icon", {}).get("glyph") or tokens.get("name", "A")[:1]
    written = render_icons(tokens, Path(a.out), glyph)
    if a.custom and Path(a.custom).is_file():
        shutil.copyfile(a.custom, Path(a.out) / "icon.png")
    print("Wrote", *written, sep="\n  - ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
