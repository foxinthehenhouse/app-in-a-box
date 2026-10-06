/**
 * Atmosphere and glass: design/tokens.json `atmosphere` -> what a screen paints.
 *
 * - The prototype froze two lights (the accent's hue and a neighbour's), their
 *   geometry, and a peak alpha per mode capped so every ink keeps AA on the lit
 *   ground. The app paints exactly that and never re-derives a colour: one that
 *   exists in no token file can't be contrast-checked.
 * - components/ui/ScreenAtmosphere draws it behind every Screen. It holds still
 *   (the prototype's slow drift is decoration the app doesn't need), so Reduce
 *   Motion has nothing to stop. Mode `field` is a WebGL shader in the prototype;
 *   here it paints the glow, as the prototype does without WebGL.
 * - Glass is for chrome only (the tab bar, the sheet header), and only when the
 *   founder chose glass surfaces, the phone has Liquid Glass (iOS 26+), and Reduce
 *   Transparency is off. Otherwise chrome is solid `surface`. Content stays solid.
 *
 * Pure pieces (atmosphereGradient, grainStyle, glassChrome) are exported for tests.
 */
import { useEffect, useState } from "react";
import { AccessibilityInfo, Platform } from "react-native";
import { isLiquidGlassAvailable } from "expo-glass-effect";

import { withAlpha } from "./theme";
import { atmosphere, type Atmosphere, type ColorScheme } from "./tokens";

export { atmosphere, grainTile, type Atmosphere } from "./tokens";

/** 0.78 -> "78%", the way the prototype writes its CSS (no float noise). */
function pct(v: number): string {
  return `${Number((v * 100).toFixed(4))}%`;
}

/**
 * The two lights as one `experimental_backgroundImage` value: the prototype's own
 * radial-gradient()s, each fading to its colour at alpha 0 (not to `transparent`,
 * which is black at 0 and greys the falloff). Null when there's nothing to paint.
 */
export function atmosphereGradient(scheme: ColorScheme, a: Atmosphere = atmosphere): string | null {
  const c = a.color[scheme];
  if (a.mode === "none" || c.alpha <= 0) return null;
  return a.lights
    .slice(0, 2)
    .map(([cx, cy, rx, ry], i) => {
      const hex = i === 0 ? c.light1 : c.light2;
      return `radial-gradient(${pct(rx)} ${pct(ry)} at ${pct(cx)} ${pct(cy)}, ${withAlpha(hex, c.alpha)}, ${withAlpha(hex, 0)})`;
    })
    .join(", ");
}

/** The grain overlay per mode: the prototype's opacity and blend. */
export const GRAIN = {
  light: { opacity: 0.05, mixBlendMode: "soft-light" },
  dark: { opacity: 0.07, mixBlendMode: "overlay" },
} as const;

/** Grain is its own knob (the prototype shows it even with the lights off). */
export function grainStyle(scheme: ColorScheme, a: Atmosphere = atmosphere): (typeof GRAIN)[ColorScheme] | null {
  return a.grain ? GRAIN[scheme] : null;
}

/**
 * The OS "Reduce Transparency" setting (iOS), reactive like useReducedMotion.
 * Always false where the platform has no such setting.
 */
export function useReducedTransparency(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceTransparencyEnabled()
      .then((v) => alive && setReduced(v))
      .catch(() => undefined);
    const sub = AccessibilityInfo.addEventListener("reduceTransparencyChanged", setReduced);
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);
  return reduced;
}

/** Liquid Glass components exist (iOS 26+). Never throws: a missing module means no. */
export function liquidGlassAvailable(): boolean {
  if (Platform.OS !== "ios") return false;
  try {
    return isLiquidGlassAvailable();
  } catch {
    return false;
  }
}

/** Should chrome be glass? Only all three: chosen, available, and transparency allowed. */
export function glassChrome(surface: Atmosphere["surface"], available: boolean, reducedTransparency: boolean): boolean {
  return surface === "glass" && available && !reducedTransparency;
}

/** glassChrome for this phone, right now (re-renders when Reduce Transparency flips). */
export function useGlassChrome(): boolean {
  const reduced = useReducedTransparency();
  return glassChrome(atmosphere.surface, liquidGlassAvailable(), reduced);
}
