#!/usr/bin/env python3
"""HCT colour (hue, chroma, tone) and tonal palettes: a pure-Python port.

HCT is Google's colour space for Material You. Hue and chroma come from CAM16 (how a
colour looks under standard viewing conditions); tone is CIE L*, which is exactly what
WCAG contrast is computed from. That makes contrast a matter of arithmetic: two
colours whose tones differ enough clear a contrast ratio whatever their hue, so a
palette built from tones is contrast-safe by construction (scripts/palette.py).

Ported from material-color-utilities (TypeScript, commit 5b3618b), Copyright 2021
Google LLC, Apache License 2.0 (licenses/Apache-2.0-material-color-utilities.txt,
THIRD_PARTY_NOTICES.md). What came across, and how it changed:
  utils/color_utils.ts, utils/math_utils.ts   the sRGB / XYZ / L* helpers used below
  hct/viewing_conditions.ts                   the default viewing conditions only
  hct/cam16.ts                                fromInt, fromJch and viewed (to an int)
  hct/hct_solver.ts                           solveToInt, unchanged in substance; the
                                              255 CRITICAL_PLANES are computed from
                                              their definition instead of listed
  hct/hct.ts, palettes/tonal_palette.ts       Hct.from / Hct.fromInt, TonalPalette.tone
Colours are 0xRRGGBB ints (no alpha). JavaScript's Math.round rounds halves up, so
`_round` does too (Python's round() would not). The upstream test values this port
reproduces are pinned in scripts/tests/test_hct.py.

Standard library only.
"""

from __future__ import annotations

import math

# --- utils/color_utils.ts, utils/math_utils.ts ---------------------------------------

SRGB_TO_XYZ = (
    (0.41233895, 0.35762064, 0.18051042),
    (0.2126, 0.7152, 0.0722),
    (0.01932141, 0.11916382, 0.95034478),
)
XYZ_TO_SRGB = (
    (3.2413774792388685, -1.5376652402851851, -0.49885366846268053),
    (-0.9691452513005321, 1.8758853451067872, 0.04156585616912061),
    (0.05562093689691305, -0.20395524564742123, 1.0571799111220335),
)
WHITE_POINT_D65 = (95.047, 100.0, 108.883)


def _round(x: float) -> int:
    return math.floor(x + 0.5)


def _lerp(a: float, b: float, t: float) -> float:
    return (1.0 - t) * a + t * b


def _signum(x: float) -> int:
    return -1 if x < 0 else (0 if x == 0 else 1)


def _clamp_int(lo: int, hi: int, x: int) -> int:
    return lo if x < lo else (hi if x > hi else x)


def sanitize_degrees(deg: float) -> float:
    return deg % 360.0


def _mul(row, matrix) -> list[float]:
    return [row[0] * m[0] + row[1] * m[1] + row[2] * m[2] for m in matrix]


def rgb_from_int(c: int) -> tuple[int, int, int]:
    return (c >> 16) & 255, (c >> 8) & 255, c & 255


def int_from_rgb(r: int, g: int, b: int) -> int:
    return (r & 255) << 16 | (g & 255) << 8 | (b & 255)


def int_from_hex(h: str) -> int:
    return int(h.lstrip("#"), 16)


def hex_from_int(c: int) -> str:
    return f"#{c & 0xFFFFFF:06X}"


def linearized(component: int) -> float:
    """0..255 sRGB channel -> 0..100 linear channel."""
    n = component / 255.0
    return (
        n / 12.92 * 100.0 if n <= 0.040449936 else ((n + 0.055) / 1.055) ** 2.4 * 100.0
    )


def delinearized(component: float) -> int:
    """0..100 linear channel -> 0..255 sRGB channel (rounded, clamped)."""
    n = component / 100.0
    d = n * 12.92 if n <= 0.0031308 else 1.055 * math.pow(n, 1.0 / 2.4) - 0.055
    return _clamp_int(0, 255, _round(d * 255.0))


def int_from_linrgb(linrgb) -> int:
    return int_from_rgb(*(delinearized(c) for c in linrgb))


def int_from_xyz(x: float, y: float, z: float) -> int:
    return int_from_linrgb(_mul((x, y, z), XYZ_TO_SRGB))


def xyz_from_int(c: int) -> list[float]:
    return _mul([linearized(v) for v in rgb_from_int(c)], SRGB_TO_XYZ)


def _lab_f(t: float) -> float:
    e, kappa = 216.0 / 24389.0, 24389.0 / 27.0
    return math.pow(t, 1.0 / 3.0) if t > e else (kappa * t + 16) / 116


def _lab_invf(ft: float) -> float:
    e, kappa = 216.0 / 24389.0, 24389.0 / 27.0
    ft3 = ft * ft * ft
    return ft3 if ft3 > e else (116 * ft - 16) / kappa


def y_from_lstar(lstar: float) -> float:
    return 100.0 * _lab_invf((lstar + 16.0) / 116.0)


def lstar_from_y(y: float) -> float:
    return _lab_f(y / 100.0) * 116.0 - 16.0


def lstar_from_int(c: int) -> float:
    return lstar_from_y(xyz_from_int(c)[1])


def int_from_lstar(lstar: float) -> int:
    v = delinearized(y_from_lstar(lstar))
    return int_from_rgb(v, v, v)


# --- hct/viewing_conditions.ts (default conditions) ----------------------------------


class ViewingConditions:
    def __init__(
        self,
        adapting_luminance: float,
        background_lstar: float = 50.0,
        surround: float = 2.0,
        discounting_illuminant: bool = False,
    ) -> None:
        x, y, z = WHITE_POINT_D65
        r_w = x * 0.401288 + y * 0.650173 + z * -0.051461
        g_w = x * -0.250268 + y * 1.204414 + z * 0.045854
        b_w = x * -0.002079 + y * 0.048952 + z * 0.953127
        f = 0.8 + surround / 10.0
        c = (
            _lerp(0.59, 0.69, (f - 0.9) * 10.0)
            if f >= 0.9
            else _lerp(0.525, 0.59, (f - 0.8) * 10.0)
        )
        d = (
            1.0
            if discounting_illuminant
            else f * (1.0 - (1.0 / 3.6) * math.exp((-adapting_luminance - 42.0) / 92.0))
        )
        d = min(1.0, max(0.0, d))
        rgb_d = [d * (100.0 / w) + 1.0 - d for w in (r_w, g_w, b_w)]
        k = 1.0 / (5.0 * adapting_luminance + 1.0)
        k4 = k**4
        k4f = 1.0 - k4
        fl = k4 * adapting_luminance + 0.1 * k4f * k4f * math.pow(
            5.0 * adapting_luminance, 1.0 / 3.0
        )
        n = y_from_lstar(background_lstar) / WHITE_POINT_D65[1]
        nbb = 0.725 / math.pow(n, 0.2)
        factors = [
            math.pow(fl * rd * w / 100.0, 0.42) for rd, w in zip(rgb_d, (r_w, g_w, b_w))
        ]
        rgb_a = [400.0 * fa / (fa + 27.13) for fa in factors]
        self.n, self.nbb, self.ncb, self.c, self.nc = n, nbb, nbb, c, f
        self.aw = (2.0 * rgb_a[0] + rgb_a[1] + 0.05 * rgb_a[2]) * nbb
        self.rgb_d, self.fl, self.fl_root = rgb_d, fl, math.pow(fl, 0.25)
        self.z = 1.48 + math.sqrt(n)


DEFAULT_VC = ViewingConditions((200.0 / math.pi) * y_from_lstar(50.0) / 100.0)


# --- hct/cam16.ts --------------------------------------------------------------------


class Cam16:
    __slots__ = ("hue", "chroma", "j", "q", "m", "s")

    def __init__(self, hue, chroma, j, q, m, s) -> None:
        self.hue, self.chroma, self.j, self.q, self.m, self.s = hue, chroma, j, q, m, s

    @classmethod
    def from_int(cls, c: int, vc: ViewingConditions = DEFAULT_VC) -> "Cam16":
        x, y, z = xyz_from_int(c)
        r_c = 0.401288 * x + 0.650173 * y - 0.051461 * z
        g_c = -0.250268 * x + 1.204414 * y + 0.045854 * z
        b_c = -0.002079 * x + 0.048952 * y + 0.953127 * z
        adapted = []
        for comp, rd in zip((r_c, g_c, b_c), vc.rgb_d):
            dd = rd * comp
            af = math.pow(vc.fl * abs(dd) / 100.0, 0.42)
            adapted.append(_signum(dd) * 400.0 * af / (af + 27.13))
        r_a, g_a, b_a = adapted
        a = (11.0 * r_a + -12.0 * g_a + b_a) / 11.0
        b = (r_a + g_a - 2.0 * b_a) / 9.0
        u = (20.0 * r_a + 20.0 * g_a + 21.0 * b_a) / 20.0
        p2 = (40.0 * r_a + 20.0 * g_a + b_a) / 20.0
        hue = sanitize_degrees(math.degrees(math.atan2(b, a)))
        ac = p2 * vc.nbb
        j = 100.0 * math.pow(ac / vc.aw, vc.c * vc.z)
        q = (4.0 / vc.c) * math.sqrt(j / 100.0) * (vc.aw + 4.0) * vc.fl_root
        hue_prime = hue + 360 if hue < 20.14 else hue
        e_hue = 0.25 * (math.cos(hue_prime * math.pi / 180.0 + 2.0) + 3.8)
        p1 = (50000.0 / 13.0) * e_hue * vc.nc * vc.ncb
        t = p1 * math.sqrt(a * a + b * b) / (u + 0.305)
        alpha = math.pow(t, 0.9) * math.pow(1.64 - math.pow(0.29, vc.n), 0.73)
        chroma = alpha * math.sqrt(j / 100.0)
        m = chroma * vc.fl_root
        s = 50.0 * math.sqrt(alpha * vc.c / (vc.aw + 4.0))
        return cls(hue, chroma, j, q, m, s)

    def to_int(self, vc: ViewingConditions = DEFAULT_VC) -> int:
        alpha = (
            0.0
            if self.chroma == 0.0 or self.j == 0.0
            else self.chroma / math.sqrt(self.j / 100.0)
        )
        t = math.pow(alpha / math.pow(1.64 - math.pow(0.29, vc.n), 0.73), 1.0 / 0.9)
        h_rad = math.radians(self.hue)
        e_hue = 0.25 * (math.cos(h_rad + 2.0) + 3.8)
        ac = vc.aw * math.pow(self.j / 100.0, 1.0 / vc.c / vc.z)
        p1 = e_hue * (50000.0 / 13.0) * vc.nc * vc.ncb
        p2 = ac / vc.nbb
        h_sin, h_cos = math.sin(h_rad), math.cos(h_rad)
        gamma = (
            23.0 * (p2 + 0.305) * t / (23.0 * p1 + 11.0 * t * h_cos + 108.0 * t * h_sin)
        )
        a, b = gamma * h_cos, gamma * h_sin
        r_a = (460.0 * p2 + 451.0 * a + 288.0 * b) / 1403.0
        g_a = (460.0 * p2 - 891.0 * a - 261.0 * b) / 1403.0
        b_a = (460.0 * p2 - 220.0 * a - 6300.0 * b) / 1403.0
        rgb_f = []
        for comp, rd in zip((r_a, g_a, b_a), vc.rgb_d):
            base = max(0.0, 27.13 * abs(comp) / (400.0 - abs(comp)))
            rgb_f.append(
                _signum(comp) * (100.0 / vc.fl) * math.pow(base, 1.0 / 0.42) / rd
            )
        r_f, g_f, b_f = rgb_f
        x = 1.86206786 * r_f - 1.01125463 * g_f + 0.14918677 * b_f
        y = 0.38752654 * r_f + 0.62144744 * g_f - 0.00897398 * b_f
        z = -0.01584150 * r_f - 0.03412294 * g_f + 1.04996444 * b_f
        return int_from_xyz(x, y, z)


# --- hct/hct_solver.ts ---------------------------------------------------------------

SCALED_DISCOUNT_FROM_LINRGB = (
    (0.001200833568784504, 0.002389694492170889, 0.0002795742885861124),
    (0.0005891086651375999, 0.0029785502573438758, 0.0003270666104008398),
    (0.00010146692491640572, 0.0005364214359186694, 0.0032979401770712076),
)
LINRGB_FROM_SCALED_DISCOUNT = (
    (1373.2198709594231, -1100.4251190754821, -7.278681089101213),
    (-271.815969077903, 559.6580465940733, -32.46047482791194),
    (1.9622899599665666, -57.173814538844006, 308.7233197812385),
)
Y_FROM_LINRGB = (0.2126, 0.7152, 0.0722)
# The linear value halfway between each pair of adjacent 8-bit sRGB values (upstream
# lists all 255; test_hct.py checks the first and last against its table).
CRITICAL_PLANES = tuple(
    100.0 * ((v / 12.92) if v <= 0.040449936 else ((v + 0.055) / 1.055) ** 2.4)
    for v in ((i + 0.5) / 255.0 for i in range(255))
)


def _sanitize_radians(angle: float) -> float:
    return (angle + math.pi * 8) % (math.pi * 2)


def _true_delinearized(component: float) -> float:
    n = component / 100.0
    d = n * 12.92 if n <= 0.0031308 else 1.055 * math.pow(n, 1.0 / 2.4) - 0.055
    return d * 255.0


def _chromatic_adaptation(component: float) -> float:
    af = math.pow(abs(component), 0.42)
    return _signum(component) * 400.0 * af / (af + 27.13)


def _hue_of(linrgb) -> float:
    sd = _mul(linrgb, SCALED_DISCOUNT_FROM_LINRGB)
    r_a, g_a, b_a = (_chromatic_adaptation(v) for v in sd)
    a = (11.0 * r_a + -12.0 * g_a + b_a) / 11.0
    b = (r_a + g_a - 2.0 * b_a) / 9.0
    return math.atan2(b, a)


def _in_cyclic_order(a: float, b: float, c: float) -> bool:
    return _sanitize_radians(b - a) < _sanitize_radians(c - a)


def _set_coordinate(source, coordinate: float, target, axis: int) -> list[float]:
    t = (coordinate - source[axis]) / (target[axis] - source[axis])
    return [s + (tt - s) * t for s, tt in zip(source, target)]


def _nth_vertex(y: float, n: int) -> list[float]:
    k_r, k_g, k_b = Y_FROM_LINRGB
    coord_a = 0.0 if n % 4 <= 1 else 100.0
    coord_b = 0.0 if n % 2 == 0 else 100.0
    if n < 4:
        g, b = coord_a, coord_b
        r = (y - g * k_g - b * k_b) / k_r
        v = [r, g, b] if 0.0 <= r <= 100.0 else None
    elif n < 8:
        b, r = coord_a, coord_b
        g = (y - r * k_r - b * k_b) / k_g
        v = [r, g, b] if 0.0 <= g <= 100.0 else None
    else:
        r, g = coord_a, coord_b
        b = (y - r * k_r - g * k_g) / k_b
        v = [r, g, b] if 0.0 <= b <= 100.0 else None
    return v or [-1.0, -1.0, -1.0]


def _bisect_to_segment(y: float, target_hue: float):
    left = right = [-1.0, -1.0, -1.0]
    left_hue = right_hue = 0.0
    initialized, uncut = False, True
    for n in range(12):
        mid = _nth_vertex(y, n)
        if mid[0] < 0:
            continue
        mid_hue = _hue_of(mid)
        if not initialized:
            left = right = mid
            left_hue = right_hue = mid_hue
            initialized = True
            continue
        if uncut or _in_cyclic_order(left_hue, mid_hue, right_hue):
            uncut = False
            if _in_cyclic_order(left_hue, target_hue, mid_hue):
                right, right_hue = mid, mid_hue
            else:
                left, left_hue = mid, mid_hue
    return left, right


def _bisect_to_limit(y: float, target_hue: float) -> list[float]:
    left, right = _bisect_to_segment(y, target_hue)
    left_hue = _hue_of(left)
    for axis in range(3):
        if left[axis] != right[axis]:
            if left[axis] < right[axis]:
                l_plane = math.floor(_true_delinearized(left[axis]) - 0.5)
                r_plane = math.ceil(_true_delinearized(right[axis]) - 0.5)
            else:
                l_plane = math.ceil(_true_delinearized(left[axis]) - 0.5)
                r_plane = math.floor(_true_delinearized(right[axis]) - 0.5)
            for _ in range(8):
                if abs(r_plane - l_plane) <= 1:
                    break
                m_plane = math.floor((l_plane + r_plane) / 2.0)
                mid = _set_coordinate(left, CRITICAL_PLANES[m_plane], right, axis)
                mid_hue = _hue_of(mid)
                if _in_cyclic_order(left_hue, target_hue, mid_hue):
                    right, r_plane = mid, m_plane
                else:
                    left, left_hue, l_plane = mid, mid_hue, m_plane
    return [(a + b) / 2 for a, b in zip(left, right)]


def _inverse_chromatic_adaptation(adapted: float) -> float:
    base = max(0.0, 27.13 * abs(adapted) / (400.0 - abs(adapted)))
    return _signum(adapted) * math.pow(base, 1.0 / 0.42)


def _find_result_by_j(hue_radians: float, chroma: float, y: float) -> int | None:
    j = math.sqrt(y) * 11.0
    vc = DEFAULT_VC
    t_inner = 1 / math.pow(1.64 - math.pow(0.29, vc.n), 0.73)
    e_hue = 0.25 * (math.cos(hue_radians + 2.0) + 3.8)
    p1 = e_hue * (50000.0 / 13.0) * vc.nc * vc.ncb
    h_sin, h_cos = math.sin(hue_radians), math.cos(hue_radians)
    for round_ in range(5):
        j_norm = j / 100.0
        alpha = 0.0 if chroma == 0.0 or j == 0.0 else chroma / math.sqrt(j_norm)
        t = math.pow(alpha * t_inner, 1.0 / 0.9)
        ac = vc.aw * math.pow(j_norm, 1.0 / vc.c / vc.z)
        p2 = ac / vc.nbb
        gamma = (
            23.0 * (p2 + 0.305) * t / (23.0 * p1 + 11 * t * h_cos + 108.0 * t * h_sin)
        )
        a, b = gamma * h_cos, gamma * h_sin
        r_a = (460.0 * p2 + 451.0 * a + 288.0 * b) / 1403.0
        g_a = (460.0 * p2 - 891.0 * a - 261.0 * b) / 1403.0
        b_a = (460.0 * p2 - 220.0 * a - 6300.0 * b) / 1403.0
        scaled = [_inverse_chromatic_adaptation(v) for v in (r_a, g_a, b_a)]
        linrgb = _mul(scaled, LINRGB_FROM_SCALED_DISCOUNT)
        if min(linrgb) < 0:
            return None
        fnj = sum(k * v for k, v in zip(Y_FROM_LINRGB, linrgb))
        if fnj <= 0:
            return None
        if round_ == 4 or abs(fnj - y) < 0.002:
            if max(linrgb) > 100.01:
                return None
            return int_from_linrgb(linrgb)
        j = j - (fnj - y) * j / (2 * fnj)  # Newton's method, 2 * fn(j) / j as fn'(j)
    return None


def solve_to_int(hue: float, chroma: float, lstar: float) -> int:
    """The sRGB colour closest to (hue, chroma, tone): exact hue and tone, and the
    requested chroma or the most the gamut allows at that hue and tone."""
    if chroma < 0.0001 or lstar < 0.0001 or lstar > 99.9999:
        return int_from_lstar(lstar)
    hue_radians = math.radians(sanitize_degrees(hue))
    y = y_from_lstar(lstar)
    exact = _find_result_by_j(hue_radians, chroma, y)
    if exact is not None:
        return exact
    return int_from_linrgb(_bisect_to_limit(y, hue_radians))


# --- hct/hct.ts, palettes/tonal_palette.ts -------------------------------------------


class Hct:
    __slots__ = ("hue", "chroma", "tone", "argb")

    def __init__(self, c: int) -> None:
        cam = Cam16.from_int(c)
        self.hue, self.chroma, self.tone, self.argb = (
            cam.hue,
            cam.chroma,
            lstar_from_int(c),
            c,
        )

    @classmethod
    def from_hct(cls, hue: float, chroma: float, tone: float) -> "Hct":
        return cls(solve_to_int(hue, chroma, tone))

    @classmethod
    def from_hex(cls, h: str) -> "Hct":
        return cls(int_from_hex(h))

    @property
    def hex(self) -> str:
        return hex_from_int(self.argb)


def is_yellow(hue: float) -> bool:
    return 105 <= hue < 125


class TonalPalette:
    """Every tone (0 black .. 100 white) of one hue at one chroma."""

    def __init__(self, hue: float, chroma: float) -> None:
        self.hue, self.chroma = hue, chroma
        self._cache: dict[float, int] = {}

    @classmethod
    def from_int(cls, c: int) -> "TonalPalette":
        h = Hct(c)
        return cls(h.hue, h.chroma)

    def tone(self, t: float) -> int:
        if t not in self._cache:
            if t == 99 and is_yellow(self.hue):  # upstream: yellows go muddy at 99
                a, b = rgb_from_int(self.tone(98)), rgb_from_int(self.tone(100))
                self._cache[t] = int_from_rgb(
                    *(_round((x + y) / 2) for x, y in zip(a, b))
                )
            else:
                self._cache[t] = solve_to_int(self.hue, self.chroma, t)
        return self._cache[t]

    def hex(self, t: float) -> str:
        return hex_from_int(self.tone(t))
