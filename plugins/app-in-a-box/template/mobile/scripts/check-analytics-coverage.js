#!/usr/bin/env node
/**
 * Analytics coverage guard (part of `npm run gates`).
 *
 * Fails when:
 *   1. a helper defined on `export const analytics = { ... }` in lib/analytics.ts
 *      has no call site anywhere else (an event nobody calls never fires, but it
 *      reads as coverage in review);
 *   2. a route under app/ (any group, sheets included; layouts `_*` and the `+*`
 *      router files are not screens) makes zero `analytics.` calls (a screen with
 *      no event is invisible in the product data);
 *   3. a TAB screen (directly under app/(app)/) fires `analytics.screenViewed` inside
 *      `useEffect`: native tabs mount every tab at launch, so a mount-time event logs
 *      the other tab as "viewed" on every cold start and never logs a tab switch. Use
 *      `useFocusEffect` (app/(app)/index.tsx is the pattern).
 *
 * Comments are blanked before counting, so `// analytics.screenViewed(...)` is not a
 * call site and a helper named only in a comment is still dead.
 *
 * The success+failure pairing for mutations is a review-time judgement: a regex
 * can't verify it without a high false-positive rate, so this script doesn't try.
 *
 * Allowlist a helper temporarily (with a reason naming what will call it) below.
 * Self-tests (positive + planted violations): scripts/__tests__/check-analytics-coverage.test.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const ANALYTICS = path.join(ROOT, "lib", "analytics.ts");
const DEAD_EVENT_ALLOWLIST = {
  // helperName: "reason + ticket that adds the call site",
};

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) out.push(p);
  }
  return out;
}

/** Blank out comments but keep line numbers, so a commented-out call is not a call. */
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, (m, pre) => pre + " ".repeat(m.length - pre.length));
}

/** A route file that is a screen: not a layout (`_layout*`) and not a router file (`+not-found`, `+native-intent`, `+html`). */
function isScreen(file) {
  const base = path.basename(file);
  return !base.startsWith("_") && !base.startsWith("+");
}

const src = fs.readFileSync(ANALYTICS, "utf8");
const block = src.match(/export const analytics = \{([\s\S]*?)\n\};/);
if (!block) {
  console.error("check-analytics-coverage: could not find `export const analytics = {...}` in lib/analytics.ts");
  process.exit(1);
}
const helpers = [...block[1].matchAll(/^\s{2}(\w+):/gm)].map((m) => m[1]);
const files = [...walk(path.join(ROOT, "app")), ...walk(path.join(ROOT, "lib")), ...walk(path.join(ROOT, "components"))].filter(
  (f) => f !== ANALYTICS,
);
const corpus = files.map((f) => stripComments(fs.readFileSync(f, "utf8"))).join("\n");

const problems = [];
for (const h of helpers) {
  if (DEAD_EVENT_ALLOWLIST[h]) continue;
  if (!new RegExp(`analytics\\.${h}\\(`).test(corpus)) problems.push(`dead helper: analytics.${h} has no call site`);
}
const TABS_DIR = path.join(ROOT, "app", "(app)");
for (const f of walk(path.join(ROOT, "app"))) {
  if (!isScreen(f)) continue;
  const text = stripComments(fs.readFileSync(f, "utf8"));
  const rel = path.relative(ROOT, f);
  if (!/analytics\.\w+\(/.test(text)) {
    problems.push(`screen with no analytics: ${rel}`);
    continue;
  }
  // Tab screens: directly under app/(app)/. Both mount at launch, so "viewed" must mean focused.
  if (path.dirname(f) === TABS_DIR && /useEffect\(\s*\(\)\s*=>\s*\{[^}]*\banalytics\.screenViewed\(/.test(text)) {
    problems.push(
      `${rel}: analytics.screenViewed fires in useEffect (on mount). Native tabs mount every tab at launch; use useFocusEffect so it fires when the tab is actually shown (see app/(app)/index.tsx)`,
    );
  }
}

if (problems.length) {
  console.error("check-analytics-coverage FAILED:\n  - " + problems.join("\n  - "));
  process.exit(1);
}
console.log(`check-analytics-coverage: ${helpers.length} helpers, all called; every app screen instrumented (tab views on focus).`);
