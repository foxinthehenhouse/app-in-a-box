/**
 * i18n: the pseudo-locale (en-XA) proves screens really go through t(). Every
 * piece of text on the rendered screens must come out bracketed ⟦…⟧; a string
 * that stays plain English was hardcoded. User data and the app's brand strings
 * are the only exceptions (they're not translatable copy).
 */
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen } from "expo-router/testing-library";

import { APP } from "../lib/app";
import { PSEUDO_LOCALE, SUPPORTED_LANGUAGES, i18n, pseudoLocalize, setLanguage } from "../lib/i18n";
import { en } from "../locales/en";

process.env.EXPO_PUBLIC_DEMO = "1";

type Node = NonNullable<typeof screen.root>;

const DATA = new Set<string>([APP.name, APP.oneLiner, "Sam", "sam@example.com"]);

function leaves(value: unknown, path: string[] = []): [string, string][] {
  if (typeof value === "string") return [[path.join("."), value]];
  return Object.entries(value as Record<string, unknown>).flatMap(([k, v]) => leaves(v, [...path, k]));
}

/** Every string a user can see or hear: text children and accessibility labels. */
function visibleStrings(root: Node): string[] {
  const out: string[] = [];
  const walk = (node: Node | string) => {
    if (typeof node === "string") {
      out.push(node);
      return;
    }
    for (const key of ["accessibilityLabel", "placeholder", "accessibilityHint"] as const) {
      const v: unknown = node.props?.[key];
      if (typeof v === "string") out.push(v);
    }
    for (const child of node.children as (Node | string)[]) walk(child);
  };
  walk(root);
  return out.filter((s) => /[A-Za-z]{2,}/.test(s) && !DATA.has(s.trim()));
}

function untranslated(): string[] {
  const root = screen.root;
  if (!root) throw new Error("nothing rendered");
  return [...new Set(visibleStrings(root).filter((s) => !s.includes("⟦")))];
}

describe("pseudoLocalize", () => {
  it("accents, pads ~35% and brackets, keeping {{placeholders}} intact", () => {
    const out = pseudoLocalize("Hi, {{name}}");
    expect(out.startsWith("⟦") && out.endsWith("⟧")).toBe(true);
    expect(out).toContain("{{name}}");
    expect(out).toContain("Ĥí");
    expect(out.length).toBeGreaterThan("Hi, {{name}}".length);
  });

  it("covers every English key", () => {
    expect(SUPPORTED_LANGUAGES).toEqual(expect.arrayContaining(["en", PSEUDO_LOCALE]));
    for (const [key] of leaves(en)) {
      expect(i18n.getResource(PSEUDO_LOCALE, "translation", key)).toMatch(/^⟦.*⟧$/s);
    }
  });
});

describe("screens in the pseudo-locale", () => {
  beforeAll(async () => {
    await setLanguage(PSEUDO_LOCALE);
  });
  afterAll(async () => {
    await setLanguage("en");
  });

  it("render no hardcoded English on sign-in, home, settings and the sheets", async () => {
    await renderRouter("./app", { initialUrl: "/" });
    await screen.findByTestId("signin-screen");
    expect(untranslated()).toEqual([]);

    await fireEvent.changeText(screen.getByTestId("signin-email-input"), "sam@example.com");
    await fireEvent.press(screen.getByTestId("signin-send-button"));
    await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
    expect(untranslated()).toEqual([]);
    await fireEvent.press(screen.getByTestId("signin-verify-button"));

    await screen.findByTestId("home-screen");
    await screen.findByText(i18n.t("home.greeting", { name: "Sam" }));
    expect(untranslated()).toEqual([]);

    await act(async () => router.navigate("/settings"));
    await screen.findByTestId("settings-screen");
    expect(untranslated()).toEqual([]);

    await act(async () => router.push("/edit-name"));
    await screen.findByTestId("edit-name-input");
    expect(untranslated()).toEqual([]);

    await act(async () => router.back());
    await act(async () => router.push("/delete-account"));
    await screen.findByTestId("delete-account-sheet");
    expect(untranslated()).toEqual([]);
  }, 30000);
});
