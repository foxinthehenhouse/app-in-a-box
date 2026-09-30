/**
 * Custom font files, loaded once at startup (app/_layout.tsx holds the splash
 * until they're in). design/tokens.json → `font` names the families; each type
 * role uses one weight of one family. Register every weight the roles use, keyed
 * `<Family>_<weight>`, the way @expo-google-fonts ships one file per weight:
 *
 *   npx expo install @expo-google-fonts/fraunces
 *   import { Fraunces_600SemiBold, Fraunces_700Bold } from "@expo-google-fonts/fraunces";
 *   export const fontAssets = { Fraunces_600: Fraunces_600SemiBold, Fraunces_700: Fraunces_700Bold };
 *
 * An unloaded face fails SILENTLY: the app falls back to the system font (or a
 * faked bold) and stops looking like the prototype the owner approved.
 * `__tests__/fonts.test.ts` fails, naming the missing keys, until every one is here.
 */
import type { FontSource } from "expo-font";

export const fontAssets: Record<string, FontSource> = {};

/** Families the OS already has: never loaded, never registered. Keep in sync with
 * BUILT_IN_FONTS in the kit's scripts/prototype.py (the kit's selftest checks). */
export const BUILT_IN_FONTS = new Set(["System", "SF Pro", "Roboto", "Menlo", "SF Mono", "monospace"]);

/** The registered face for a family at a weight, or undefined for a built-in family. */
export function fontFace(family: string, weight: string, assets: Record<string, FontSource> = fontAssets): string | undefined {
  const key = `${family}_${weight}`;
  return key in assets ? key : undefined;
}
