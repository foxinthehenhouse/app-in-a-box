#!/usr/bin/env node
/**
 * Design tells in code (part of `npm run gates`): the habits that make an app look
 * generated rather than designed. The token-level twin is ../scripts/check_design.py
 * (fonts, grey neutrals, stock violet accent, overshooting curves in tokens.json).
 * Each rule is in docs/design/TASTE.md; the ideas are adapted from Impeccable's
 * anti-pattern detector (Apache-2.0), rewritten for React Native, where that
 * detector (a web/CSS scanner) can't see.
 *
 *   bounce-easing     Easing.bounce / Easing.elastic / Easing.back, or an
 *                     Easing.bezier(...) whose curve goes past its end. Content and
 *                     screens decelerate; overshoot lives in lib/motion.ts springs.
 *   nested-card       a <Card> inside another <Card>. Use rows, spacing or a divider.
 *   side-stripe       a coloured border on one side wider than 1 (borderLeftWidth: 4).
 *   hard-shadow       a zero-blur offset shadow (shadowRadius: 0, "4px 4px 0").
 *   gradient-text     text filled with a gradient (MaskedView over a LinearGradient).
 *   emoji-ui          an emoji standing in for an icon, bullet or heading: a string
 *                     that starts with one, or one in an icon/title/label value.
 *   raw-pressable     a bare <Pressable> or <Touchable*> outside components/ui/: no
 *                     press scale, no haptic, no pressed tint (docs/design/CRAFT.md).
 *                     Build taps from PressableScale, Button, IconButton or ListRow.
 *
 * Pragmatic regexes, not a parser: it runs with no node_modules (the kit selftest
 * calls it on a fresh render). Escape hatch, with a reason the reviewer can judge:
 * `// design-ignore: <why>` at the end of the line.
 *
 *   node scripts/check-design-tells.js       (scans app/ components/ lib/ locales/)
 * Self-tests: scripts/__tests__/check-design-tells.test.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DIRS = ["app", "components", "lib", "locales"];
const EMOJI = "\\p{Extended_Pictographic}";
const IGNORE = /\/\/\s*design-ignore:\s*\S/;
// The ui kit is where the press feedback is built, so it may hold the raw primitive.
const RAW_PRESS = /<(Pressable|Touchable(Opacity|Highlight|WithoutFeedback|NativeFeedback))\b/;

const LINE_RULES = [
  [/\bEasing\.(bounce|elastic|back)\b/, "bounce-easing", "a bounce/elastic/back curve (content decelerates; use lib/motion.ts)"],
  [/\bborder(Left|Right|Start|End)Width\s*:\s*([2-9]|\d{2,})\b/, "side-stripe", "a thick one-sided border (a callout stripe)"],
  [/\bshadowRadius\s*:\s*0\b/, "hard-shadow", "a zero-blur shadow (use an elevation token)"],
  [/\bboxShadow\s*:\s*["'`]\s*-?[1-9]\d*px\s+-?\d+px\s+0(px)?[\s"'`,]/, "hard-shadow", "a zero-blur offset box shadow"],
  [new RegExp(`["'\`]\\s*${EMOJI}`, "u"), "emoji-ui", "a string that starts with an emoji (use an icon from the set)"],
  [new RegExp(`\\b(icon|title|label|eyebrow)\\s*[:=]\\s*\\{?\\s*["'\`][^"'\`]*${EMOJI}`, "u"), "emoji-ui", "an emoji in an icon/title/label"],
];

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === "__tests__" || e.name.startsWith(".")) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx|js|jsx)$/.test(e.name)) out.push(p);
  }
  return out;
}

/** Character offset -> 1-based line number. */
function lineAt(text, i) {
  return text.slice(0, i).split("\n").length;
}

/** Each `<Card ...>` / `<Card ... />` / `</Card>` in order, reading past `=>` inside {braces}. */
function cardTags(text) {
  const tags = [];
  const re = /<\/Card\s*>|<Card\b/g;
  let m;
  while ((m = re.exec(text))) {
    if (m[0].startsWith("</")) { tags.push({ kind: "close", at: m.index }); continue; }
    let depth = 0, j = m.index + 5;
    for (; j < text.length; j++) {
      const c = text[j];
      if (c === "{") depth++;
      else if (c === "}") depth--;
      else if (c === ">" && depth === 0) break;
    }
    tags.push({ kind: text[j - 1] === "/" ? "self" : "open", at: m.index });
    re.lastIndex = j;
  }
  return tags;
}

const hits = [];
for (const file of DIRS.flatMap((d) => walk(path.join(ROOT, d)))) {
  const rel = path.relative(ROOT, file).split(path.sep).join("/");
  const inKit = rel.startsWith("components/ui/");
  const text = fs.readFileSync(file, "utf8");
  const lines = text.split("\n");
  const ignored = (n) => IGNORE.test(lines[n - 1] || "");
  lines.forEach((line, i) => {
    if (IGNORE.test(line) || /^\s*(\/\/|\*|\/\*)/.test(line)) return;
    for (const [re, rule, why] of LINE_RULES) {
      if (re.test(line)) hits.push(`${rel}:${i + 1}: ${rule}: ${why}`);
    }
    const raw = !inKit && line.match(RAW_PRESS);
    if (raw) hits.push(`${rel}:${i + 1}: raw-pressable: a bare <${raw[1]}> has no press feedback (use PressableScale, Button or ListRow)`);
    const bz = line.match(/\bEasing\.bezier\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)/);
    if (bz && [bz[2], bz[4]].some((y) => Number(y) < -0.1 || Number(y) > 1.1)) {
      hits.push(`${rel}:${i + 1}: bounce-easing: Easing.bezier(${bz.slice(1).join(", ")}) overshoots its end`);
    }
  });
  let depth = 0;
  for (const t of cardTags(text)) {
    if (t.kind === "close") depth = Math.max(0, depth - 1);
    else {
      const n = lineAt(text, t.at);
      if (depth > 0 && !ignored(n)) hits.push(`${rel}:${n}: nested-card: a Card inside a Card (flatten: rows, spacing, a divider)`);
      if (t.kind === "open") depth++;
    }
  }
  const gt = text.match(/<MaskedView\b[\s\S]{0,600}?<LinearGradient\b/);
  if (gt && !ignored(lineAt(text, gt.index))) {
    hits.push(`${rel}:${lineAt(text, gt.index)}: gradient-text: text filled with a gradient (emphasis comes from weight or size)`);
  }
}

if (hits.length) {
  console.error("check-design-tells FAILED (docs/design/TASTE.md Anti-slop list, docs/design/CRAFT.md):\n  - " + hits.join("\n  - "));
  console.error("A deliberate exception? End the line with `// design-ignore: <why>`.");
  process.exit(1);
}
console.log("check-design-tells: no generic-design tells in app/, components/, lib/, locales/.");
