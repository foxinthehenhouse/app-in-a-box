const { test } = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runOnTemplate, runOnTree, assertRefuses, assertPasses } = require("./check-helpers");

const GUARD = "check-eas-shipping-env";
const eas = (profiles = {}) =>
  JSON.stringify({
    build: {
      development: { developmentClient: true, ...profiles.development },
      preview: { env: {}, ...profiles.preview },
      production: { env: {}, ...profiles.production },
    },
  });
const base = { "eas.json": eas(), "lib/api.ts": 'const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "";\n' };

test("passes on the pristine template and prints the store-diff commands", () => {
  const r = runOnTemplate(GUARD);
  assertPasses(r, "template");
  if (!/eas-cli env:list --environment preview --format json/.test(r.out)) throw new Error(`no verification command printed:\n${r.out}`);
});

test("refuses an EXPO_PUBLIC_* read that no shipping profile or store entry provides", () => {
  const tree = { ...base, "lib/flags.ts": 'export const BETA = process.env.EXPO_PUBLIC_BETA === "1";\n' };
  assertRefuses(runOnTree(GUARD, tree), "EXPO_PUBLIC_BETA", "unwired var");
});

test("refuses demo mode in the development profile too (a dev-client build honours it)", () => {
  const tree = { ...base, "eas.json": eas({ development: { env: { EXPO_PUBLIC_DEMO: "1" } } }) };
  assertRefuses(runOnTree(GUARD, tree), /EXPO_PUBLIC_DEMO is set in eas\.json development/, "demo in development");
});

test("--eas-env: a store listing missing a claimed EAS_MANAGED name fails naming it", () => {
  const store = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "eas-")), "preview.json");
  // What `eas env:list --format json` returns, minus the API URL someone forgot to create.
  fs.writeFileSync(
    store,
    JSON.stringify([
      { name: "EXPO_PUBLIC_SUPABASE_URL", value: "https://x.supabase.co", environments: ["preview"] },
      { name: "EXPO_PUBLIC_SUPABASE_ANON_KEY", value: "eyJ", environments: ["preview"] },
      { name: "EXPO_PUBLIC_POSTHOG_API_KEY", value: "phc", environments: ["preview"] },
      { name: "EXPO_PUBLIC_POSTHOG_HOST", value: "https://us.i.posthog.com", environments: ["preview"] },
      { name: "EXPO_PUBLIC_SENTRY_DSN", value: "https://o.ingest.sentry.io/1", environments: ["preview"] },
    ]),
  );
  assertRefuses(runOnTree(GUARD, base, ["--eas-env", store]), /does not list them:\n\s+- EXPO_PUBLIC_API_URL/, "store gap");
});

test("--eas-env: a complete store listing passes and says it was verified", () => {
  const store = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "eas-")), "production.json");
  const names = ["EXPO_PUBLIC_SUPABASE_URL", "EXPO_PUBLIC_SUPABASE_ANON_KEY", "EXPO_PUBLIC_API_URL", "EXPO_PUBLIC_POSTHOG_API_KEY", "EXPO_PUBLIC_POSTHOG_HOST", "EXPO_PUBLIC_SENTRY_DSN"];
  fs.writeFileSync(store, JSON.stringify(names.map((name) => ({ name, value: "x", environments: ["production"] }))));
  const r = runOnTree(GUARD, base, ["--eas-env", store]);
  assertPasses(r, "complete store");
  if (!/verified against/.test(r.out)) throw new Error(`expected a verified line:\n${r.out}`);
});
