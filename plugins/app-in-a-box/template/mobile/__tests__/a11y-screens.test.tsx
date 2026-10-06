/**
 * Accessibility, rendered: every route under app/ (found on disk, so a new screen is
 * audited the day it lands) in demo mode, at 100% and 200% text. On each one, every
 * control a person can press or switch must have a role and a name VoiceOver and Voice
 * Control can say, and none may sit inside a subtree hidden from the accessibility tree.
 * The source-level twin is scripts/check-a11y.js; the rule is .agents/rules/mobile-a11y.md.
 *
 * Signed-out routes are the ones under app/(auth)/; every other route is opened signed
 * in. A route needs a root testID ending in -screen or -sheet (check-maestro-coverage
 * asks for the same one). A dynamic segment like [id] is filled from ROUTE_PARAMS; opt a
 * route out with a comment naming why: `// a11y-screens: skip <reason>`.
 *
 * Jest computes no layout, so this can't see text clip at 200%; it proves every screen
 * renders and keeps its names when code branches on the font scale. Clipping is the
 * Maestro / device pass (docs/qa).
 */
import { Dimensions, PixelRatio } from "react-native";
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen } from "expo-router/testing-library";

import { pressWhenEnabled } from "./support/press";

// Node's fs/path, typed by hand: the app's tsconfig has no @types/node (it ships to phones).
interface Dirent {
  name: string;
  isDirectory(): boolean;
}
declare const __dirname: string;
const fs = require("fs") as {
  readdirSync(dir: string, opts: { withFileTypes: true }): Dirent[];
  readFileSync(file: string, enc: "utf8"): string;
};
const path = require("path") as { join(...p: string[]): string; relative(from: string, to: string): string; sep: string };

// Set before the routes (and lib/demo.ts) are required by renderRouter.
process.env.EXPO_PUBLIC_DEMO = "1";
// Required AFTER the env var: a static import is hoisted above it and demo mode loads off.
const { signOut } = require("../lib/session") as typeof import("../lib/session");

/** Values for dynamic segments: `[id]` -> ROUTE_PARAMS.id. Point them at a seeded demo row. */
const ROUTE_PARAMS: Record<string, string> = {};
const INTERACTIVE_ROLES = new Set(["button", "link", "switch", "togglebutton", "checkbox", "radio", "tab", "menuitem"]);
const APP_DIR = path.join(__dirname, "..", "app");

type Node = NonNullable<typeof screen.root>;
interface Route {
  file: string;
  url: string;
  rootId: string;
  signedOut: boolean;
}

function routeFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return routeFiles(p);
    const special = e.name.startsWith("+") && e.name !== "+not-found.tsx";
    return /\.tsx$/.test(e.name) && !e.name.startsWith("_layout") && !special && !/\.web\.tsx$/.test(e.name) ? [p] : [];
  });
}

function toRoute(file: string): Route | null {
  const src = fs.readFileSync(file, "utf8");
  if (/\/\/\s*a11y-screens:\s*skip\s+\S/.test(src)) return null;
  const rel = path.relative(APP_DIR, file).split(path.sep).join("/").replace(/\.tsx$/, "");
  const rootId = src.match(/testID="([a-z0-9-]+-(?:screen|sheet))"/)?.[1] ?? "";
  const segments = rel
    .split("/")
    .filter((s) => !/^\(.*\)$/.test(s) && s !== "index")
    .map((s) => (s === "+not-found" ? "a11y-no-such-route" : s.replace(/^\[(.+)\]$/, (_, k: string) => ROUTE_PARAMS[k] ?? "1")));
  return { file: rel, url: "/" + segments.join("/"), rootId, signedOut: rel.startsWith("(auth)/") };
}

/** Controls audited so far: a run that saw none proved nothing, so it fails. */
let controlsSeen = 0;

const ROUTES = routeFiles(APP_DIR)
  .map(toRoute)
  .filter((r): r is Route => r !== null);

function roleOf(n: Node): string {
  const r: unknown = n.props.accessibilityRole ?? n.props.role;
  return typeof r === "string" ? r : "";
}

function textOf(n: Node | string): string {
  if (typeof n === "string") return n;
  return (n.children as (Node | string)[]).map(textOf).join("");
}

function isHidden(n: Node): boolean {
  const p = n.props;
  return p.accessibilityElementsHidden === true || p.importantForAccessibility === "no-hide-descendants" || p["aria-hidden"] === true;
}

function isInteractive(n: Node): boolean {
  const p = n.props;
  return typeof p.onPress === "function" || typeof p.onClick === "function" || INTERACTIVE_ROLES.has(roleOf(n)) || n.type === "RCTSwitch";
}

function describeNode(n: Node): string {
  const id = typeof n.props.testID === "string" ? ` testID="${n.props.testID}"` : "";
  const text = textOf(n).trim().slice(0, 40);
  return `<${n.type}${id}>${text ? ` "${text}"` : ""}`;
}

function hiddenByAncestor(n: Node): boolean {
  for (let p = n.parent; p; p = p.parent) if (isHidden(p)) return true;
  return false;
}

/**
 * The visible instance of a route's root: a stack keeps the screens underneath mounted
 * (and hidden from the accessibility tree), so only the one on top is audited.
 */
function visibleRoot(rootId: string): Node | undefined {
  return screen.container.queryAll((n) => n.props.testID === rootId).find((n) => !hiddenByAncestor(n) && !isHidden(n));
}

/** Every pressable/switchable host element in `root` and what's wrong with it, if anything. */
function audit(root: Node, where: string): string[] {
  const problems: string[] = [];
  const visit = (n: Node, hidden: boolean) => {
    const inHidden = hidden || isHidden(n);
    if (n.type === "TextInput" && !n.props.accessibilityLabel && !n.props.accessibilityLabelledBy) {
      problems.push(`${where}: ${describeNode(n)} is a text field with no accessibilityLabel`);
    } else if (isInteractive(n)) {
      controlsSeen++;
      const named = typeof n.props.accessibilityLabel === "string" ? n.props.accessibilityLabel.trim() : textOf(n).trim();
      if (!roleOf(n) && n.type !== "RCTSwitch") problems.push(`${where}: ${describeNode(n)} is pressable with no accessibilityRole`);
      if (!named && !n.props.accessibilityLabelledBy) problems.push(`${where}: ${describeNode(n)} is pressable with no accessibilityLabel or text`);
      if (inHidden) problems.push(`${where}: ${describeNode(n)} is pressable but hidden from the accessibility tree`);
    }
    for (const c of n.children) if (typeof c !== "string") visit(c, inHidden);
  };
  visit(root, false);
  return problems;
}

async function open(route: Route, problems: string[]): Promise<void> {
  if (!route.rootId) {
    problems.push(`app/${route.file}: no root testID ending in -screen or -sheet (or add \`// a11y-screens: skip <why>\`)`);
    return;
  }
  await act(async () => router.navigate(route.url));
  await screen.findByTestId(route.rootId).catch(() => null);
  const root = visibleRoot(route.rootId);
  if (!root) {
    problems.push(`app/${route.file}: ${route.url} never showed a visible "${route.rootId}" (fill ROUTE_PARAMS, or skip with a reason)`);
    return;
  }
  problems.push(...audit(root, `${route.url} (app/${route.file})`));
}

async function signIn(): Promise<void> {
  await fireEvent.changeText(await screen.findByTestId("signin-email-input"), "sam@example.com");
  await pressWhenEnabled("signin-send-button");
  await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
  await pressWhenEnabled("signin-verify-button");
  await screen.findByTestId("home-screen");
}

function setFontScale(fontScale: number): void {
  const window = Dimensions.get("window");
  const screenDims = Dimensions.get("screen");
  Dimensions.set({ window: { ...window, fontScale }, screen: { ...screenDims, fontScale } });
}

it("finds the app's routes on disk", () => {
  expect(ROUTES.length).toBeGreaterThan(0);
  expect(ROUTES.some((r) => r.signedOut)).toBe(true);
});

describe.each([1, 2])("every screen at font scale %d", (fontScale) => {
  beforeAll(() => setFontScale(fontScale));
  afterAll(() => setFontScale(1));
  afterEach(async () => {
    await act(async () => signOut());
  });

  it("names and roles every control, and hides none of them", async () => {
    expect(PixelRatio.getFontScale()).toBe(fontScale); // what Text and useWindowDimensions read
    const problems: string[] = [];
    await renderRouter("./app", { initialUrl: "/" });
    await screen.findByTestId("signin-screen");
    for (const r of ROUTES.filter((x) => x.signedOut)) await open(r, problems);
    await signIn();
    for (const r of ROUTES.filter((x) => !x.signedOut)) await open(r, problems);
    expect([...new Set(problems)]).toEqual([]);
    expect(controlsSeen).toBeGreaterThan(0);
  }, 120000);
});
