/**
 * Theme runtime. Screens and components read colours, type and spacing from
 * `useTheme()` (or a `makeStyles` hook), never from raw hex values or tokens.ts.
 *
 * - Both palettes come from design/tokens.json (generated into tokens.ts).
 * - The OS appearance picks one; the user can override it in Settings
 *   (persisted). A theme with one palette is locked to it.
 * - Type roles carry `font.*`, size, weight, line height, letter spacing and a
 *   Dynamic Type cap (`maxScale`), applied by <Text role="...">.
 *
 * Pure pieces (resolveScheme, buildTheme) are exported for tests.
 */
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Appearance, Platform, StyleSheet, useColorScheme, type TextStyle, type ViewStyle } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  elevation as elevationTokens,
  font,
  minTapTarget,
  mode,
  motion,
  opacity,
  palettes,
  radius,
  schemes,
  size,
  space,
  typeRoles,
  type ColorScheme,
  type Palette,
} from "./tokens";

export type { ColorName, ColorScheme, Palette } from "./tokens";
export { font, minTapTarget, motion, opacity, radius, size, space };

export type ThemePreference = "system" | ColorScheme;
export type TypeRole = keyof typeof typeRoles;
export type Elevation = keyof typeof elevationTokens;

/** Does this theme ship both palettes? If not, the appearance picker is hidden. */
export const canSwitchScheme = schemes.length > 1;

/**
 * Which palette to render. Order: a locked (single-palette) theme wins, then the
 * user's explicit choice, then the OS, then the theme's default mode.
 */
export function resolveScheme(
  system: string | null | undefined,
  preference: ThemePreference,
  supported: readonly ColorScheme[] = schemes,
  fallback: ColorScheme = mode,
): ColorScheme {
  const only = supported.length === 1 ? supported[0] : undefined;
  if (only) return only;
  if (preference !== "system" && supported.includes(preference)) return preference;
  if ((system === "light" || system === "dark") && supported.includes(system)) return system;
  return supported.includes(fallback) ? fallback : (supported[0] ?? "dark");
}

/** `#RRGGBB` + alpha -> `rgba(...)`, for shadows and tints derived from tokens. */
export function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const n = (i: number) => parseInt(h.slice(i, i + 2), 16);
  return `rgba(${n(0)}, ${n(2)}, ${n(4)}, ${alpha})`;
}

const TONE_FOR_ROLE: Record<TypeRole, keyof Palette> = {
  display: "ink",
  title: "ink",
  heading: "ink",
  body: "ink",
  secondary: "inkDim",
  meta: "inkFaint",
  mono: "ink",
};

function fontFamily(key: keyof typeof font): string | undefined {
  const name = font[key];
  // "System" means the platform font: leave fontFamily unset so iOS uses SF and
  // Android uses Roboto. A named family must be loaded with expo-font first.
  return name === "System" ? undefined : name;
}

export interface Theme {
  scheme: ColorScheme;
  isDark: boolean;
  color: Palette;
  type: Record<TypeRole, TextStyle>;
  /** Dynamic Type cap per role, passed as maxFontSizeMultiplier by <Text>. */
  typeScale: Record<TypeRole, number>;
  elevation: Record<Elevation, ViewStyle>;
  space: typeof space;
  radius: typeof radius;
  size: typeof size;
  motion: typeof motion;
  opacity: typeof opacity;
  minTapTarget: number;
}

export function buildTheme(scheme: ColorScheme): Theme {
  const color = palettes[scheme];
  const isDark = scheme === "dark";
  const type = {} as Record<TypeRole, TextStyle>;
  const typeScale = {} as Record<TypeRole, number>;
  for (const role of Object.keys(typeRoles) as TypeRole[]) {
    const spec: {
      font: string;
      size: number;
      lineHeight: number;
      weight: string;
      letterSpacing: number;
      maxScale: number;
      uppercase?: boolean;
    } = typeRoles[role];
    type[role] = {
      fontFamily: fontFamily(spec.font as keyof typeof font),
      fontSize: spec.size,
      lineHeight: spec.lineHeight,
      fontWeight: spec.weight as TextStyle["fontWeight"],
      letterSpacing: spec.letterSpacing,
      color: color[TONE_FOR_ROLE[role]],
      ...(spec.uppercase ? { textTransform: "uppercase" as const } : null),
      ...(role === "mono" ? { fontVariant: ["tabular-nums" as const] } : null),
    };
    typeScale[role] = spec.maxScale;
  }
  const elevation = {} as Record<Elevation, ViewStyle>;
  for (const name of Object.keys(elevationTokens) as Elevation[]) {
    const e: { elevation: number; shadowOpacity: number; shadowRadius: number; shadowOffsetY: number } =
      elevationTokens[name];
    // Shadows read as mud on dark grounds; a hairline border carries elevation there.
    elevation[name] =
      e.shadowOpacity === 0
        ? {}
        : isDark
          ? { borderWidth: StyleSheet.hairlineWidth, borderColor: color.border }
          : {
              boxShadow: `0px ${e.shadowOffsetY}px ${e.shadowRadius}px ${withAlpha(
                // `shadow` is optional in tokens.json; fall back to the ink.
                (color as Readonly<Record<string, string>>)["shadow"] ?? color.ink,
                e.shadowOpacity,
              )}`,
            };
  }
  return { scheme, isDark, color, type, typeScale, elevation, space, radius, size, motion, opacity, minTapTarget };
}

const THEMES: Record<ColorScheme, Theme> = { light: buildTheme("light"), dark: buildTheme("dark") };

interface ThemeContextValue {
  theme: Theme;
  preference: ThemePreference;
  setPreference: (p: ThemePreference) => void;
  ready: boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);
const STORAGE_KEY = "appbox.theme-preference";

function isPreference(v: unknown): v is ThemePreference {
  return v === "system" || v === "light" || v === "dark";
}

/** Mirror the choice into native chrome (tab bar, sheets, keyboard, alerts). */
function applyNativeAppearance(p: ThemePreference): void {
  if (Platform.OS === "web" || !canSwitchScheme) return;
  try {
    Appearance.setColorScheme(p === "system" ? "unspecified" : p);
  } catch {
    // older runtimes: the JS palette still follows the preference
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [preference, setPref] = useState<ThemePreference>("system");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    AsyncStorage.getItem(STORAGE_KEY)
      .then((v) => {
        if (!alive) return;
        if (isPreference(v)) {
          setPref(v);
          applyNativeAppearance(v);
        }
      })
      .catch(() => undefined)
      .finally(() => alive && setReady(true));
    return () => {
      alive = false;
    };
  }, []);

  const setPreference = useCallback((p: ThemePreference) => {
    setPref(p);
    applyNativeAppearance(p);
    AsyncStorage.setItem(STORAGE_KEY, p).catch(() => undefined);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme: THEMES[resolveScheme(system, preference)], preference, setPreference, ready }),
    [system, preference, setPreference, ready],
  );
  return createElement(ThemeContext.Provider, { value }, children);
}

/** Force a scheme for a subtree (the gallery renders both side by side). */
export function ThemeScope({ scheme, children }: { scheme: ColorScheme; children: ReactNode }) {
  const parent = useContext(ThemeContext);
  const value = useMemo<ThemeContextValue>(
    () => ({
      theme: THEMES[scheme],
      preference: parent?.preference ?? "system",
      setPreference: parent?.setPreference ?? (() => undefined),
      ready: true,
    }),
    [scheme, parent],
  );
  return createElement(ThemeContext.Provider, { value }, children);
}

export function useTheme(): Theme {
  const ctx = useContext(ThemeContext);
  const system = useColorScheme();
  return ctx?.theme ?? THEMES[resolveScheme(system, "system")];
}

export function useThemePreference(): Pick<ThemeContextValue, "preference" | "setPreference" | "ready"> {
  const ctx = useContext(ThemeContext);
  return {
    preference: ctx?.preference ?? "system",
    setPreference: ctx?.setPreference ?? (() => undefined),
    ready: ctx?.ready ?? true,
  };
}

/**
 * Themed StyleSheet hook. Styles are built once per scheme at import time, so a
 * render only picks the right sheet:
 *
 *   const useStyles = makeStyles((t) => ({ card: { backgroundColor: t.color.surface } }));
 *   const s = useStyles();
 */
export function makeStyles<S extends StyleSheet.NamedStyles<S>>(factory: (t: Theme) => S): () => S {
  const sheets: Record<ColorScheme, S> = {
    light: StyleSheet.create(factory(THEMES.light)),
    dark: StyleSheet.create(factory(THEMES.dark)),
  };
  return function useStyles(): S {
    return sheets[useTheme().scheme];
  };
}
