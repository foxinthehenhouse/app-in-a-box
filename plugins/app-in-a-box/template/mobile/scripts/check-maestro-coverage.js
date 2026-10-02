#!/usr/bin/env node
/**
 * Maestro coverage guard (part of `npm run gates`).
 *
 * Fails when:
 *   1. a route under app/ (a screen or a sheet) has no root testID ending in
 *      `-screen` or `-sheet`. That id is the handle every flow asserts on;
 *   2. no flow under .maestro/ asserts or waits on that id, so the screen has no E2E
 *      coverage at all;
 *   3. a flow targets an `id:` that no component in app/ or components/ renders.
 *      A renamed testID otherwise leaves a flow that can only fail on a device,
 *      which nobody notices until someone runs it.
 *
 * Skipped routes: layouts (`_layout*`), `+` special files, and `.web.tsx` platform
 * variants (the native file next to them is the one that's checked). Opt a route
 * out with a comment in it, naming why:
 *   // maestro-coverage: skip <reason>
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const APP = path.join(ROOT, "app");
const FLOWS = path.join(ROOT, ".maestro");

function walk(dir, test, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules") continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, test, out);
    else if (test(entry.name)) out.push(p);
  }
  return out;
}

const rel = (p) => path.relative(ROOT, p);
const isRoute = (name) =>
  /\.tsx$/.test(name) && !name.startsWith("_layout") && !name.startsWith("+") && !/\.web\.tsx$/.test(name);

const flows = walk(FLOWS, (n) => /\.ya?ml$/.test(n) && n !== "config.yaml");
const flowText = flows.map((f) => fs.readFileSync(f, "utf8")).join("\n");
const flowIds = new Map(); // id -> first flow that targets it
for (const f of flows) {
  for (const m of fs.readFileSync(f, "utf8").matchAll(/^\s*id:\s*["']?([A-Za-z0-9_-]+)["']?\s*$/gm)) {
    if (!flowIds.has(m[1])) flowIds.set(m[1], rel(f));
  }
}

const sources = [...walk(APP, (n) => /\.tsx?$/.test(n)), ...walk(path.join(ROOT, "components"), (n) => /\.tsx?$/.test(n))]
  .filter((f) => !/__tests__|\.test\.tsx?$/.test(f));
const rendered = new Set();
for (const f of sources) {
  for (const m of fs.readFileSync(f, "utf8").matchAll(/testID=["{]["`]?([A-Za-z0-9_-]+)["`]?/g)) rendered.add(m[1]);
}

const problems = [];
if (flows.length === 0) problems.push(".maestro/ has no flows");

for (const route of walk(APP, isRoute)) {
  const src = fs.readFileSync(route, "utf8");
  if (/\/\/\s*maestro-coverage:\s*skip\s+\S/.test(src)) continue;
  const root = src.match(/testID="([a-z0-9-]+-(?:screen|sheet))"/);
  if (!root) {
    problems.push(`${rel(route)}: no root testID ending in -screen or -sheet`);
    continue;
  }
  const id = root[1];
  if (!new RegExp(`^\\s*id:\\s*["']?${id}["']?\\s*$`, "m").test(flowText)) {
    problems.push(`${rel(route)}: no flow in .maestro/ targets "${id}"`);
  }
}

for (const [id, flow] of flowIds) {
  if (!rendered.has(id)) problems.push(`${flow}: targets id "${id}", which nothing in app/ or components/ renders`);
}

if (problems.length) {
  console.error("check-maestro-coverage:\n  " + problems.join("\n  "));
  console.error("Add a flow (docs/qa/MAESTRO.md), fix the testID, or opt the route out with `// maestro-coverage: skip <reason>`.");
  process.exit(1);
}
console.log(`check-maestro-coverage: ${flows.length} flows cover every route; every flow id is rendered.`);
