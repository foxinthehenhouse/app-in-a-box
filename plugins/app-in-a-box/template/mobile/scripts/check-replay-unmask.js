#!/usr/bin/env node
/**
 * Session replay stays masked. Fails on any PostHog unmask token or API anywhere
 * in app code, comments included. Never "fix" a blurry replay by unmasking. Add
 * an analytics event with the value-level detail you need instead.
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const BANNED = ["ph-no-mask", "posthogunmaskview", "posthognomask", "maskalltextinputs: false", "maskallimages: false"];

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

const hits = [];
for (const f of ["app", "lib", "components"].flatMap((d) => walk(path.join(ROOT, d)))) {
  const text = fs.readFileSync(f, "utf8").toLowerCase();
  for (const token of BANNED) if (text.includes(token)) hits.push(`${path.relative(ROOT, f)}: ${token}`);
}
if (hits.length) {
  console.error("check-replay-unmask FAILED:\n  - " + hits.join("\n  - "));
  process.exit(1);
}
console.log("check-replay-unmask: replay masking intact.");
