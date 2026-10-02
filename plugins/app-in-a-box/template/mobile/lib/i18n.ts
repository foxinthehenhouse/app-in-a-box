/**
 * i18n: i18next + react-i18next, language from the device (expo-localization).
 *
 *   const t = useT();              // in a component
 *   t("home.greeting", { name })   // keys are typed: a typo fails tsc
 *   i18n.t("errors.generic")       // outside React (lib code)
 *
 * Every user-facing string in app/** goes through t(). The gates run
 * scripts/check-hardcoded-strings.js, which fails on a literal in JSX text, a
 * user-facing prop (label, title, accessibilityLabel...) or a toast call.
 *
 * Add a language: copy locales/en.ts to locales/<code>.ts (`satisfies Messages`),
 * add it to RESOURCES below. `en-XA` is a PSEUDO-locale (accented, bracketed,
 * ~35% longer) that proves screens use t() and survive longer strings: switch
 * to it in a test (see __tests__/i18n-pseudo.test.tsx) or with setLanguage("en-XA").
 */
import { getLocales } from "expo-localization";
import { createInstance } from "i18next";
import { initReactI18next, useTranslation } from "react-i18next";

import { en, type Messages } from "../locales/en";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: { translation: typeof en };
  }
}

export const PSEUDO_LOCALE = "en-XA";

const ACCENTS: Record<string, string> = {
  a: "á", b: "ƀ", c: "ç", d: "ď", e: "é", f: "ƒ", g: "ĝ", h: "ĥ", i: "í", j: "ĵ", k: "ķ", l: "ĺ", m: "ɱ",
  n: "ñ", o: "ó", p: "þ", q: "ǫ", r: "ŕ", s: "š", t: "ţ", u: "ú", v: "ṽ", w: "ŵ", x: "ẋ", y: "ý", z: "ž",
  A: "Á", B: "Ɓ", C: "Ç", D: "Ď", E: "É", F: "Ƒ", G: "Ĝ", H: "Ĥ", I: "Í", J: "Ĵ", K: "Ķ", L: "Ĺ", M: "Ṁ",
  N: "Ñ", O: "Ó", P: "Þ", Q: "Ǫ", R: "Ŕ", S: "Š", T: "Ţ", U: "Ú", V: "Ṽ", W: "Ŵ", X: "Ẋ", Y: "Ý", Z: "Ž",
};

/** Pseudo-localise one string: accents, ~35% padding, brackets. Keeps {{placeholders}} intact. */
export function pseudoLocalize(s: string): string {
  const parts = s.split(/(\{\{[^}]+\}\})/g);
  const body = parts.map((p) => (p.startsWith("{{") ? p : [...p].map((ch) => ACCENTS[ch] ?? ch).join(""))).join("");
  const letters = s.replace(/\{\{[^}]+\}\}/g, "").length;
  return `⟦${body}${"·".repeat(Math.ceil(letters * 0.35))}⟧`;
}

function mapStrings<T>(value: T, fn: (s: string) => string): T {
  if (typeof value === "string") return fn(value) as T;
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = mapStrings(v, fn);
  return out as T;
}

const RESOURCES: Record<string, { translation: Messages }> = {
  en: { translation: en },
  [PSEUDO_LOCALE]: { translation: mapStrings<Messages>(en, pseudoLocalize) },
};

export const SUPPORTED_LANGUAGES = Object.keys(RESOURCES);

/** The best supported language for the device, falling back to English. */
export function deviceLanguage(): string {
  try {
    for (const l of getLocales()) {
      if (l.languageTag && RESOURCES[l.languageTag]) return l.languageTag;
      if (l.languageCode && RESOURCES[l.languageCode]) return l.languageCode;
    }
  } catch {
    // no native module (some test/web contexts): English
  }
  return "en";
}

/** The app's own i18next instance (not the global default, so tests and libraries can't clash). */
const i18n = createInstance();
if (!i18n.isInitialized) {
  void i18n.use(initReactI18next).init({
    resources: RESOURCES,
    lng: deviceLanguage(),
    fallbackLng: "en",
    initAsync: false, // resources are bundled: initialise synchronously, no flash of keys
    interpolation: { escapeValue: false }, // React escapes already
    returnNull: false,
  });
}

export function setLanguage(code: string): Promise<unknown> {
  return i18n.changeLanguage(code);
}

/** The typed t() for components. */
export function useT() {
  return useTranslation().t;
}

/** Translate a key that is only known at runtime (e.g. a zod message); unknown keys pass through. */
export function translate(key: string, options?: Record<string, unknown>): string {
  if (!i18n.exists(key)) return key;
  // i18next accepts an untyped key when a defaultValue is given: no cast needed.
  return i18n.t(key, { ...options, defaultValue: key });
}

export { i18n };
