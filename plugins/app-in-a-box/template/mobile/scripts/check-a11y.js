#!/usr/bin/env node
/**
 * Accessibility in code (part of `npm run gates`): the gaps a screen reader, Voice
 * Control or large text finds first, caught before a reviewer has to notice them.
 * The rendered twin is __tests__/a11y-screens.test.tsx (every route, at 100% and 200%
 * text); the token twin is ../scripts/check_contrast.py. Each rule is in
 * .agents/rules/mobile-a11y.md.
 *
 *   unlabelled-control  a Pressable, PressableScale, TouchableX or TextInput with no
 *                       accessibilityLabel / accessibilityLabelledBy (or aria-label),
 *                       or an empty one.
 *   no-role             a Pressable, PressableScale or TouchableX with no
 *                       accessibilityRole (or role). A TextInput's role is native.
 *   unlabelled-image    an <Image> (react-native or expo-image) with neither a label
 *                       nor accessible={false} (decorative).
 *   label-restates-role a label that ends in its role ("Save button"): VoiceOver
 *                       already says "button", so it hears "Save button, button".
 *   no-font-scaling     allowFontScaling={false}: text that ignores the reader's size.
 *   low-font-cap        maxFontSizeMultiplier below 1.3 outside components/ui (the kit
 *                       caps per role from design/tokens.json `maxScale`).
 *   motion-ignores-os   a Reanimated withTiming / withSpring / withDecay outside
 *                       lib/motion.ts whose config neither uses a lib/motion preset
 *                       (timing(), spring()) nor sets reduceMotion; or an RN Animated
 *                       timing / spring / decay in a file that never asks the OS.
 *
 * components/ui is in scope too, with one allowance: a wrapper that forwards its props
 * (`{...rest}` on the control) gets its role and label from the caller, whose own call
 * site is checked. Pragmatic regexes, not a parser: it runs with no node_modules (the
 * kit selftest calls it on a fresh render). Escape hatch, with a reason the reviewer
 * can judge: `// a11y-ignore: <why>` on the line (or `{/* a11y-ignore: <why> *\/}` on
 * the line above a JSX tag).
 *
 *   node scripts/check-a11y.js       (scans app/ components/ lib/, labels in locales/)
 * Self-tests: scripts/__tests__/check-a11y.test.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DIRS = ["app", "components", "lib"];
const IGNORE = /\/[/*]\s*a11y-ignore:\s*[^\s*]/;
const UI_KIT = /^components\/ui\//;
const MOTION = "lib/motion.ts";

const CONTROL = /<(Pressable|PressableScale|AnimatedPressable|Touchable(?:Opacity|Highlight|WithoutFeedback|NativeFeedback)|TextInput)(?=[\s/>])/g;
const IMAGE = /<(Image|ExpoImage)(?=[\s/>])/g;
const HAS_LABEL = /\b(accessibilityLabel|accessibilityLabelledBy|aria-label|aria-labelledby)\s*=/;
const EMPTY_LABEL = /\baccessibilityLabel\s*=\s*(""|''|\{\s*(""|''|``|undefined)\s*\})/;
const HAS_ROLE = /\b(accessibilityRole|role)\s*=/;
const ROLES = "button|link|tab|image|icon|switch|toggle|checkbox|header|heading|text field";
const RESTATES = new RegExp(`\\s(${ROLES})\\s*$`, "i");
const LABEL_LITERAL = /\baccessibilityLabel\s*=\s*\{?\s*["'`]([^"'`$]*)["'`]/g;
const LOCALE_LABEL = /\b\w*Label\s*:\s*["'`]([^"'`]*)["'`]/g;

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

/** The props text of the JSX tag opening at `at`, up to its `>` (reading past `=>` in {braces}). */
function tagProps(text, at) {
  let depth = 0;
  for (let j = at + 1; j < text.length; j++) {
    const c = text[j];
    if (c === "{") depth++;
    else if (c === "}") depth--;
    else if (c === ">" && depth === 0) return text.slice(at, j + 1);
  }
  return text.slice(at);
}

/** The argument text of the call whose `(` is at `open`. */
function callArgs(text, open) {
  let depth = 0;
  for (let j = open; j < text.length; j++) {
    if (text[j] === "(") depth++;
    else if (text[j] === ")" && --depth === 0) return text.slice(open + 1, j);
  }
  return text.slice(open + 1);
}

function makeFile(file) {
  const rel = path.relative(ROOT, file).split(path.sep).join("/");
  const text = fs.readFileSync(file, "utf8");
  const lines = text.split("\n");
  const ignored = (n) => IGNORE.test(lines[n - 1] || "") || IGNORE.test(lines[n - 2] || "");
  return { rel, text, lines, ignored };
}

function checkControls(f, hits) {
  for (const m of f.text.matchAll(CONTROL)) {
    const n = lineAt(f.text, m.index);
    if (f.ignored(n)) continue;
    const props = tagProps(f.text, m.index);
    // A kit wrapper forwarding its props: the caller supplies role and label.
    if (UI_KIT.test(f.rel) && /\{\s*\.\.\.\w+\s*\}/.test(props)) continue;
    if (!HAS_LABEL.test(props) || EMPTY_LABEL.test(props)) hits.push(`${f.rel}:${n}: unlabelled-control: <${m[1]}> has no accessibilityLabel (say what it does: "Save changes")`);
    if (m[1] !== "TextInput" && !HAS_ROLE.test(props)) hits.push(`${f.rel}:${n}: no-role: <${m[1]}> has no accessibilityRole ("button", "link", "switch"...)`);
  }
}

function checkImages(f, hits) {
  if (!/from\s+["'](react-native|expo-image)["']/.test(f.text)) return;
  for (const m of f.text.matchAll(IMAGE)) {
    const n = lineAt(f.text, m.index);
    if (f.ignored(n)) continue;
    const props = tagProps(f.text, m.index);
    if (!HAS_LABEL.test(props) && !/\balt\s*=/.test(props) && !/\baccessible\s*=\s*\{\s*false\s*\}/.test(props)) {
      hits.push(`${f.rel}:${n}: unlabelled-image: <${m[1]}> needs accessibilityLabel, or accessible={false} if it is decoration`);
    }
  }
}

function checkLabels(rel, text, re, ignored, hits) {
  for (const m of text.matchAll(re)) {
    const n = lineAt(text, m.index);
    if (!ignored(n) && RESTATES.test(m[1])) {
      hits.push(`${rel}:${n}: label-restates-role: "${m[1]}" (the role is announced already; drop "${m[1].match(RESTATES)[1]}")`);
    }
  }
}

function checkFontScaling(f, hits) {
  f.lines.forEach((line, i) => {
    if (f.ignored(i + 1) || /^\s*(\/\/|\*|\/\*)/.test(line)) return;
    if (/\ballowFontScaling\s*=\s*\{\s*false\s*\}|\ballowFontScaling\s*:\s*false\b/.test(line)) {
      hits.push(`${f.rel}:${i + 1}: no-font-scaling: allowFontScaling={false} ignores the reader's text size`);
    }
    const cap = line.match(/\bmaxFontSizeMultiplier\s*[=:]\s*\{?\s*([\d.]+)/);
    if (cap && Number(cap[1]) < 1.3 && !UI_KIT.test(f.rel)) {
      hits.push(`${f.rel}:${i + 1}: low-font-cap: maxFontSizeMultiplier ${cap[1]} (under 1.3; use <Text variant>, which caps per role)`);
    }
  });
}

function checkMotion(f, hits) {
  if (f.rel === MOTION) return;
  for (const m of f.text.matchAll(/\b(withTiming|withSpring|withDecay)\s*\(/g)) {
    const n = lineAt(f.text, m.index);
    const args = callArgs(f.text, m.index + m[0].length - 1);
    if (f.ignored(n) || /\breduceMotion\b|\b(timing|spring)\s*\(/.test(args)) continue;
    hits.push(`${f.rel}:${n}: motion-ignores-os: ${m[1]}() without Reduce Motion (use animateTo/springTo from lib/motion.ts)`);
  }
  const asksOs = /\b(useReducedMotion|isReduceMotionEnabled)\b/.test(f.text);
  for (const m of f.text.matchAll(/\bAnimated\.(timing|spring|decay)\s*\(/g)) {
    const n = lineAt(f.text, m.index);
    if (!asksOs && !f.ignored(n)) {
      hits.push(`${f.rel}:${n}: motion-ignores-os: Animated.${m[1]}() in a file that never checks Reduce Motion (use lib/motion.ts)`);
    }
  }
}

const hits = [];
for (const file of DIRS.flatMap((d) => walk(path.join(ROOT, d)))) {
  const f = makeFile(file);
  checkControls(f, hits);
  checkImages(f, hits);
  checkLabels(f.rel, f.text, LABEL_LITERAL, f.ignored, hits);
  checkFontScaling(f, hits);
  checkMotion(f, hits);
}
for (const file of walk(path.join(ROOT, "locales"))) {
  const f = makeFile(file);
  checkLabels(f.rel, f.text, LOCALE_LABEL, f.ignored, hits);
}

if (hits.length) {
  console.error("check-a11y FAILED (.agents/rules/mobile-a11y.md):\n  - " + hits.join("\n  - "));
  console.error("A deliberate exception? Add `// a11y-ignore: <why>` on the line.");
  process.exit(1);
}
console.log("check-a11y: controls labelled, images described, text scales, motion honours Reduce Motion.");
