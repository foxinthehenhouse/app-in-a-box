#!/usr/bin/env node
/**
 * Shipping-env guard (part of `npm run gates`).
 *
 * Every `process.env.EXPO_PUBLIC_*` read in app code must be available to the
 * builds users actually get. Either it's declared in eas.json's `preview` AND
 * `production` env blocks, or it's listed in EAS_MANAGED (set with
 * `eas env:create`), or it's in ALLOWLIST with a reason its absence is a safe
 * default. Otherwise a feature works on your laptop (.env) and silently does
 * nothing in the App Store build.
 *
 * EXPO_PUBLIC_DEMO (demo mode, lib/demo.ts) fails this check if eas.json sets it
 * for preview/production. This script can't see the EAS env STORE, so also never
 * `eas env:create` it: check with
 *   npx eas-cli env:list --environment production   (and preview)
 * and `eas env:delete` it if it's there. lib/demo.ts ANDs it with __DEV__, so a
 * release build ignores a leaked value, but a preview/dev-client build would not.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
// Set in the EAS env store for preview + production by the provision phase.
const EAS_MANAGED = new Set([
  "EXPO_PUBLIC_SUPABASE_URL",
  "EXPO_PUBLIC_SUPABASE_ANON_KEY",
  "EXPO_PUBLIC_API_URL",
  "EXPO_PUBLIC_POSTHOG_API_KEY",
  "EXPO_PUBLIC_POSTHOG_HOST",
  "EXPO_PUBLIC_SENTRY_DSN",
]);
const ALLOWLIST = {
  EXPO_PUBLIC_ANALYTICS_IN_DEV: "dev-only switch; absent in shipping builds by design",
  EXPO_PUBLIC_DEMO:
    "dev-only demo mode (in-memory fake backend, lib/demo.ts, gated on __DEV__); absent = real backend, the safe default. Never set it in eas.json or the EAS env store",
};

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name.startsWith(".")) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx|js)$/.test(e.name)) out.push(p);
  }
  return out;
}

const used = new Set();
for (const f of ["app", "lib", "components"].flatMap((d) => walk(path.join(ROOT, d)))) {
  for (const m of fs.readFileSync(f, "utf8").matchAll(/process\.env\.(EXPO_PUBLIC_[A-Z0-9_]+)/g)) used.add(m[1]);
}

const eas = JSON.parse(fs.readFileSync(path.join(ROOT, "eas.json"), "utf8"));
const inProfile = (name) => new Set(Object.keys(eas.build?.[name]?.env ?? {}));
const preview = inProfile("preview");
const production = inProfile("production");

// Demo mode swaps the backend for an in-memory fake: it must never reach users.
const demoShipped = ["preview", "production"].filter((p) => {
  const v = eas.build?.[p]?.env?.EXPO_PUBLIC_DEMO;
  return v !== undefined && v !== "" && v !== "0";
});
if (demoShipped.length) {
  console.error(`check-eas-shipping-env FAILED: EXPO_PUBLIC_DEMO is set in eas.json ${demoShipped.join(" + ")}. Demo mode is dev-only.`);
  process.exit(1);
}

const missing = [...used].filter(
  (v) => !EAS_MANAGED.has(v) && !(v in ALLOWLIST) && !(preview.has(v) && production.has(v)),
);
if (missing.length) {
  console.error(
    "check-eas-shipping-env FAILED. These are read in code but won't exist in shipping builds:\n  - " +
      missing.join("\n  - ") +
      "\nAdd each to eas.json preview+production env, or `eas env:create` it and list it in EAS_MANAGED.",
  );
  process.exit(1);
}
console.log(`check-eas-shipping-env: ${used.size} EXPO_PUBLIC_* var(s), all wired for shipping builds.`);
if (used.has("EXPO_PUBLIC_DEMO")) {
  console.log(
    "  note: EXPO_PUBLIC_DEMO must also be absent from the EAS env store: `npx eas-cli env:list --environment production` (and preview).",
  );
}
