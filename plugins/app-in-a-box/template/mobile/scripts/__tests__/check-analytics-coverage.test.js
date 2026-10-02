const { test } = require("node:test");
const { runOnTemplate, runOnTree, assertRefuses, assertPasses } = require("./check-helpers");

const GUARD = "check-analytics-coverage";

/** A self-consistent minimal project: two helpers, both called; one tab screen on focus; one sheet. */
const base = {
  "lib/analytics.ts": [
    "export const analytics = {",
    '  screenViewed: (screen: string) => capture("screen_viewed", { screen }),',
    '  sheetOpened: (sheet: string) => capture("sheet_opened", { sheet }),',
    "};",
    "",
  ].join("\n"),
  "app/(app)/index.tsx": [
    'import { useCallback } from "react";',
    'import { useFocusEffect } from "expo-router";',
    'import { analytics } from "../../lib/analytics";',
    "export default function Home() {",
    '  useFocusEffect(useCallback(() => { analytics.screenViewed("home"); }, []));',
    "  return null;",
    "}",
    "",
  ].join("\n"),
  "app/edit-name.tsx": [
    'import { useEffect } from "react";',
    'import { analytics } from "../lib/analytics";',
    "export default function Sheet() {",
    '  useEffect(() => { analytics.sheetOpened("edit_name"); }, []);',
    "  return null;",
    "}",
    "",
  ].join("\n"),
  "app/_layout.tsx": "export default function Root() { return null; }\n",
  "app/+not-found.tsx": "export default function NotFound() { return null; }\n",
};

test("passes on the pristine template", () => {
  assertPasses(runOnTemplate(GUARD), "template");
});

test("passes on the minimal fixture (layouts and +files are not screens)", () => {
  assertPasses(runOnTree(GUARD, base), "fixture");
});

test("a commented-out call is not a call site: the screen is uninstrumented", () => {
  // A future editor stubs the screen and leaves the event as a reminder.
  const planted = {
    ...base,
    "app/(app)/stats.tsx": [
      'import { analytics } from "../../lib/analytics";',
      "export default function Stats() {",
      '  // TODO: analytics.screenViewed("stats") once the layout settles',
      "  return null;",
      "}",
      "",
    ].join("\n"),
  };
  assertRefuses(runOnTree(GUARD, planted), "screen with no analytics: app/(app)/stats.tsx", "comment-only call");
});

test("a helper named only in a comment is dead", () => {
  const planted = {
    ...base,
    "lib/analytics.ts": base["lib/analytics.ts"].replace("};", '  exportStarted: () => capture("export_started"),\n};'),
    "lib/export.ts": "/** Fires analytics.exportStarted() before the download. */\nexport function download() {}\n",
  };
  assertRefuses(runOnTree(GUARD, planted), "dead helper: analytics.exportStarted", "comment-only helper reference");
});

test("widened scope: a signed-out route with no event fails too", () => {
  const planted = { ...base, "app/(auth)/reset-password.tsx": "export default function Reset() { return null; }\n" };
  assertRefuses(runOnTree(GUARD, planted), "screen with no analytics: app/(auth)/reset-password.tsx", "route outside (app)");
});

test("a tab screen that logs its view on mount (useEffect) fails: both tabs mount at launch", () => {
  // Exactly how the screens were written before: copy-pasted from an older tab.
  const planted = {
    ...base,
    "app/(app)/settings.tsx": [
      'import { useEffect } from "react";',
      'import { analytics } from "../../lib/analytics";',
      "export default function Settings() {",
      "  useEffect(() => {",
      '    analytics.screenViewed("settings");',
      "  }, []);",
      "  return null;",
      "}",
      "",
    ].join("\n"),
  };
  assertRefuses(runOnTree(GUARD, planted), /settings\.tsx: analytics\.screenViewed fires in useEffect/, "mount-time tab view");
});

test("the same useEffect pattern on a NON-tab route (a sheet) is fine", () => {
  const planted = {
    ...base,
    "app/about.tsx": [
      'import { useEffect } from "react";',
      'import { analytics } from "../lib/analytics";',
      "export default function About() {",
      '  useEffect(() => { analytics.screenViewed("about"); }, []);',
      "  return null;",
      "}",
      "",
    ].join("\n"),
  };
  assertPasses(runOnTree(GUARD, planted), "mount-time view on a stack route");
});
