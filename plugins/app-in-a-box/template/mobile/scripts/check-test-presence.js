#!/usr/bin/env node
/**
 * Test presence guard (part of `npm run gates`).
 *
 * Every module in components/ui/ and lib/ is imported by at least one test
 * (`*.test.ts(x)`), or is listed below with the reason it needs none. A new
 * primitive or lib module with no test fails here, because "I'll add the test
 * later" is how a kit ends up with untested load-bearing code.
 *
 * This checks presence, not quality: a test that imports a module and asserts
 * nothing still passes. Review judges whether a test checks behaviour; the jest
 * coverage threshold catches a module whose test barely runs it.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const GUARDED = ["components/ui", "lib"];

// module path (relative to mobile/, no extension) -> why it has no test of its own
const NO_TEST_NEEDED = {
  "components/ui/index": "barrel file: re-exports only",
  "components/ui/Icon": "thin wrapper over expo-symbols; rendered by every component test",
  "components/ui/PressableScale": "exercised through Button/Chip/ListRow in components.test.tsx (haptics, disabled)",
  "components/ui/FormField": "react-hook-form binding over Field; covered by lib/__tests__/forms.test.tsx",
  "lib/updates": "expo-updates calls only reachable in a release build; UpdateBanner is tested",
  "lib/use-load": "covered through the screen tests that render loading, error and retry states",
};

function walk(dir, test, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name === "__tests__") continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(p, test, out);
    else if (test(entry.name)) out.push(p);
  }
  return out;
}

function tests(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) tests(p, out);
    else if (/\.test\.tsx?$/.test(entry.name)) out.push(p);
  }
  return out;
}

// A barrel (`import { OfflineBanner } from "../ui"`) counts for the module that
// exports each named import.
const BARREL = "components/ui";
const exportedBy = new Map();
for (const f of walk(path.join(ROOT, BARREL), (n) => /\.tsx?$/.test(n) && n !== "index.ts")) {
  for (const m of fs.readFileSync(f, "utf8").matchAll(/export\s+(?:function|const|class)\s+(\w+)/g)) {
    exportedBy.set(m[1], path.relative(ROOT, f).replace(/\.tsx?$/, ""));
  }
}

// Every module a test imports, resolved to a mobile/-relative path without extension.
const imported = new Set();
for (const t of tests(ROOT)) {
  const src = fs.readFileSync(t, "utf8");
  for (const m of src.matchAll(/(?:import\s+(?:type\s+)?([\s\S]*?)\s+from\s+|require\(\s*|jest\.requireActual\(\s*)["'](\.{1,2}\/[^"']+)["']/g)) {
    const mod = path.relative(ROOT, path.resolve(path.dirname(t), m[2])).replace(/\.(tsx?|js)$/, "");
    imported.add(mod);
    if ((mod === BARREL || mod === `${BARREL}/index`) && m[1]) {
      for (const name of (m[1].match(/\{([^}]*)\}/)?.[1] ?? "").split(",")) {
        const owner = exportedBy.get(name.trim().split(/\s+as\s+/)[0]);
        if (owner) imported.add(owner);
      }
    }
  }
}

const problems = [];
for (const dir of GUARDED) {
  for (const f of walk(path.join(ROOT, dir), (n) => /\.tsx?$/.test(n) && !/\.d\.ts$/.test(n) && !/\.web\.tsx?$/.test(n))) {
    const mod = path.relative(ROOT, f).replace(/\.tsx?$/, "");
    if (imported.has(mod)) {
      if (NO_TEST_NEEDED[mod]) problems.push(`${mod}: has a test now; remove it from NO_TEST_NEEDED`);
      continue;
    }
    if (!NO_TEST_NEEDED[mod]) problems.push(`${mod}: no test imports it`);
  }
}
for (const mod of Object.keys(NO_TEST_NEEDED)) {
  if (!fs.existsSync(path.join(ROOT, `${mod}.ts`)) && !fs.existsSync(path.join(ROOT, `${mod}.tsx`))) {
    problems.push(`${mod}: in NO_TEST_NEEDED but doesn't exist`);
  }
}

if (problems.length) {
  console.error("check-test-presence:\n  " + problems.join("\n  "));
  console.error("Add a behaviour test that imports it, or list it in NO_TEST_NEEDED with the reason.");
  process.exit(1);
}
console.log("check-test-presence: every components/ui and lib module has a test or a stated reason.");
