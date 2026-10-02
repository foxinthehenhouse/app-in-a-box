#!/usr/bin/env node
/**
 * Session replay stays masked. Fails on any PostHog unmask token or API anywhere
 * in app code, comments included. Never "fix" a blurry replay by unmasking. Add
 * an analytics event with the value-level detail you need instead.
 *
 * Two layers, because a literal-substring ban is trivially bypassed by spelling:
 *   - BANNED: known unmask tokens, matched case-insensitively as substrings.
 *   - PATTERNS: any `maskAll*` option whose value is not the literal `true`
 *     (`maskAllTextInputs: false`, `: !hide`, `: MASK`, `: maskSetting`, the
 *     shorthand `{ maskAllImages }`), an empty `sessionReplayConfig: {}` (masking
 *     must be explicit, not inherited), and any `unmask*(` API call.
 * Self-tests: scripts/__tests__/check-replay-unmask.test.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const BANNED = ["ph-no-mask", "posthogunmaskview", "posthognomask", "maskalltextinputs: false", "maskallimages: false"];
// Run against the LOWERCASED file text (so maskAll / MaskAll / maskall all match).
const PATTERNS = [
  [/\bmaskall\w*\s*:(?!\s*true\b)/, "a maskAll* option set to something other than the literal true"],
  [/[{,]\s*maskall\w+\s*[,}]/, "a maskAll* shorthand property (its value is a variable, not the literal true)"],
  [/sessionreplayconfig\s*:\s*\{\s*\}/, "an empty sessionReplayConfig (masking must be set explicitly)"],
  [/\bunmask\w*\s*\(/, "an unmask API call"],
];

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
  for (const [re, why] of PATTERNS) {
    const m = text.match(re);
    if (m) hits.push(`${path.relative(ROOT, f)}: ${why} (${m[0].trim()})`);
  }
}
if (hits.length) {
  console.error("check-replay-unmask FAILED:\n  - " + hits.join("\n  - "));
  process.exit(1);
}
console.log("check-replay-unmask: replay masking intact.");
