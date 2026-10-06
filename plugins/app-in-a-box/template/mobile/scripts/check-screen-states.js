#!/usr/bin/env node
/**
 * States contract (part of `npm run gates`): a signed-in screen that loads data shows
 * the truth in every state, not just the happy one. docs/design/CRAFT.md and the
 * "Honest states" line of docs/design/TASTE.md are the why.
 *
 * Every route under app/(app)/ that loads data (`useLoaded(`, `useQuery(`,
 * `useInfiniteQuery(`) must render all three:
 *   loading   <Skeleton> or <SkeletonCard>   (shape, never a spinner)
 *   error     <ErrorNotice>                  (what happened, a retry, the reference)
 *   empty     <EmptyState>                   (what's missing and the one next step)
 * Offline is the app's job, not each screen's: the cached query keeps the last data on
 * screen and <OfflineBanner> says so.
 *
 * Escape hatch, with a reason a reviewer can judge: a `// states: <why>` comment in the
 * file (a settings list that always has rows, a screen whose error lands in a toast).
 * Layouts and `+` routes are skipped: they render no data of their own.
 *
 * Pragmatic regexes, not a parser: it runs with no node_modules (the kit selftest calls
 * it on a fresh render).
 *
 *   node scripts/check-screen-states.js
 * Self-tests: scripts/__tests__/check-screen-states.test.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const SCREENS = path.join(ROOT, "app", "(app)");
const LOADS = /\buse(Loaded|Query|InfiniteQuery)\s*\(/;
const WAIVER = /\/\/[ \t]*states:[ \t]*\S/;
const STATES = [
  ["loading", /<Skeleton(Card)?\b/, "<Skeleton>/<SkeletonCard> while it loads"],
  ["error", /<ErrorNotice\b/, "<ErrorNotice> when the load fails"],
  ["empty", /<EmptyState\b/, "<EmptyState> when there is nothing yet"],
];

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === "__tests__" || e.name.startsWith(".")) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(tsx|ts|jsx|js)$/.test(e.name) && !/^(_layout|\+)/.test(e.name)) out.push(p);
  }
  return out;
}

/** Blank out comments, so a mention in a doc comment is neither a trigger nor a state. */
function stripComments(src) {
  return src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

const hits = [];
for (const file of walk(SCREENS)) {
  const rel = path.relative(ROOT, file);
  const src = fs.readFileSync(file, "utf8");
  const code = stripComments(src);
  if (!LOADS.test(code) || WAIVER.test(src)) continue;
  const missing = STATES.filter(([, re]) => !re.test(code));
  for (const [state, , want] of missing) hits.push(`${rel}: missing-${state}-state: loads data but never renders ${want}`);
}

if (hits.length) {
  console.error("check-screen-states FAILED (docs/design/CRAFT.md, honest states):\n  - " + hits.join("\n  - "));
  console.error("A screen that genuinely can't be empty or fail? Say why with a `// states: <why>` comment.");
  process.exit(1);
}
console.log("check-screen-states: every data screen under app/(app)/ renders loading, error and empty states.");
