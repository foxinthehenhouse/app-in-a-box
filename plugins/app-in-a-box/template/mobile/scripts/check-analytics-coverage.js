#!/usr/bin/env node
/**
 * Analytics coverage guard (part of `npm run gates`).
 *
 * Fails when:
 *   1. a helper defined on `export const analytics = { ... }` in lib/analytics.ts
 *      has no call site anywhere else (an event nobody calls never fires, but it
 *      reads as coverage in review);
 *   2. a screen under app/(app)/ makes zero `analytics.` calls (a screen with no
 *      event is invisible in the product data).
 *
 * The success+failure pairing for mutations is a review-time judgement: a regex
 * can't verify it without a high false-positive rate, so this script doesn't try.
 *
 * Allowlist a helper temporarily (with a reason naming what will call it) below.
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
const corpus = files.map((f) => fs.readFileSync(f, "utf8")).join("\n");

const problems = [];
for (const h of helpers) {
  if (DEAD_EVENT_ALLOWLIST[h]) continue;
  if (!new RegExp(`analytics\\.${h}\\(`).test(corpus)) problems.push(`dead helper: analytics.${h} has no call site`);
}
for (const f of walk(path.join(ROOT, "app", "(app)"))) {
  if (path.basename(f).startsWith("_")) continue; // layouts
  if (!/analytics\.\w+\(/.test(fs.readFileSync(f, "utf8"))) {
    problems.push(`screen with no analytics: ${path.relative(ROOT, f)}`);
  }
}

if (problems.length) {
  console.error("check-analytics-coverage FAILED:\n  - " + problems.join("\n  - "));
  process.exit(1);
}
console.log(`check-analytics-coverage: ${helpers.length} helpers, all called; every app screen instrumented.`);
