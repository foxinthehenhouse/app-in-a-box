#!/usr/bin/env node
/**
 * Hardcoded-string guard (part of `npm run gates`).
 *
 * Every user-facing string in app/** and components/** goes through t() (lib/i18n.ts, strings in
 * locales/en.ts), so the app can be translated and the pseudo-locale test can
 * prove it. This fails on:
 *   1. JSX text with letters:            <Text>Save</Text>
 *   2. a user-facing prop set to a literal: label="Save", accessibilityLabel={"Close"}
 *   3. a user-facing object key in app code: { label: "System" }, { title: "Home" }
 *   4. a literal passed to toast.*(), announceForAccessibility(), Alert.alert()
 *   5. a literal rendered through a JSX expression: {`Welcome back`}, {"Hello, " + name},
 *      {ok ? "Saved" : "Failed"} (the expression must sit where JSX text would, right
 *      after a tag's `>`; `${placeholders}` are stripped before the letter test, so
 *      {`✓ ${label}`} is fine)
 *
 * Pragmatic regexes, not a parser: it runs with no node_modules (the kit
 * selftest calls it on a fresh render). Escape hatches, each needing a reason:
 *   - `// i18n-ignore` at the end of a line (brand names, format strings)
 *   - a file in ALLOWLIST below (dev-only screens)
 * Data (user names, APP.name) is not a string literal, so it never trips this.
 *
 *   node scripts/check-hardcoded-strings.js [dir...]   (default: app/ components/)
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
// Screens AND the component library (a label baked into a component ships on every screen).
const TARGETS = (process.argv.length > 2 ? process.argv.slice(2) : ["app", "components"]).map((d) => path.resolve(ROOT, d));

// file (relative to mobile/) -> why it may hold literals
const ALLOWLIST = {
  "app/gallery.tsx": "dev-only component gallery (route guarded by __DEV__), never shown to users",
};

const PROPS =
  "label|title|subtitle|body|hint|placeholder|accessibilityLabel|accessibilityHint|message|announce|headerTitle|tabBarLabel|dialogTitle";
const LETTER = /[A-Za-z]{2,}/;

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name.startsWith(".") || e.name === "__tests__") continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(tsx|ts)$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

/** Blank out comments but keep line numbers (and `i18n-ignore` markers, handled per line first). */
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, (m, pre) => pre + " ".repeat(m.length - pre.length));
}

function lineOf(src, index) {
  return src.slice(0, index).split("\n").length;
}

const RULES = [
  {
    name: "JSX text",
    // text right after a tag's `>` (not `=>`/`->`) up to a closing tag or an expression
    re: /(?<![=\-])>([^<>{}]*?)(?=<\/|\{)/g,
    bad: (m) => LETTER.test(m[1]) && !/[()=;|&]/.test(m[1]) && m[1].trim().length > 0,
  },
  {
    name: "JSX text before a child element",
    re: /(?<![=\-])>([^<>{}]*?)(?=<[A-Z])/g,
    // `\w$`: text glued to the `<` is a TS generic (`extends Omit<Props`), not JSX
    bad: (m) => LETTER.test(m[1]) && !/[()=;|&:,]/.test(m[1]) && !/\w$/.test(m[1]) && m[1].trim().length > 0,
  },
  {
    name: "user-facing prop",
    re: new RegExp(`\\b(?:${PROPS})=(?:\\{\\s*)?(["'\`])([^"'\`]*)\\1`, "g"),
    bad: (m) => LETTER.test(m[2]),
  },
  {
    name: "user-facing object key",
    re: new RegExp(`\\b(?:${PROPS})\\s*:\\s*(["'\`])([^"'\`]*)\\1`, "g"),
    bad: (m) => LETTER.test(m[2]),
  },
  {
    name: "literal in toast/announce/alert",
    re: /\b(?:toast\.(?:success|error|info|show)|announceForAccessibility|Alert\.alert)\(\s*(["'`])([^"'`]*)\1/g,
    bad: (m) => LETTER.test(m[2]),
  },
  {
    name: "template literal as JSX text",
    // {`...`} directly where JSX text would go (after a tag's `>`, not an arrow's)
    re: /(?<=(?<![=\-])>\s*)\{\s*`([^`]*)`\s*\}/g,
    bad: (m) => LETTER.test(m[1].replace(/\$\{[^}]*\}/g, "")),
  },
  {
    name: "string literal in a JSX expression",
    // {"Hello, " + name} / {ok ? "Saved" : "Failed"} / {ok ? "Saved" : label}: any quoted
    // literal with letters inside a brace-free expression rendered as JSX text
    re: /(?<=(?<![=\-])>\s*)\{[^{}]*[+?:][^{}]*\}/g,
    bad: (m) => [...m[0].matchAll(/(["'`])([^"'`]*)\1/g)].some((q) => LETTER.test((q[2] ?? "").replace(/\$\{[^}]*\}/g, ""))),
  },
];

const problems = [];
for (const file of TARGETS.flatMap((d) => walk(d))) {
  const rel = path.relative(ROOT, file).split(path.sep).join("/");
  if (ALLOWLIST[rel]) continue;
  const raw = fs.readFileSync(file, "utf8");
  if (/i18n-ignore-file/.test(raw)) {
    problems.push(`${rel}: 'i18n-ignore-file' is not allowed; add the file to ALLOWLIST with a reason`);
    continue;
  }
  const ignored = new Set(raw.split("\n").flatMap((l, i) => (/i18n-ignore/.test(l) ? [i + 1] : [])));
  const src = stripComments(raw);
  for (const rule of RULES) {
    for (const m of src.matchAll(rule.re)) {
      if (!rule.bad(m)) continue;
      const line = lineOf(src, m.index + 1);
      if (ignored.has(line)) continue;
      problems.push(`${rel}:${line}  ${rule.name}: ${m[0].trim().slice(0, 70)}`);
    }
  }
}

if (problems.length) {
  console.error(
    "check-hardcoded-strings FAILED. User-facing text must go through t() (lib/i18n.ts, strings in locales/en.ts):\n  - " +
      problems.join("\n  - ") +
      "\nMove the text to locales/en.ts and render t(\"key\"). Brand/data exceptions: end the line with // i18n-ignore (say why).",
  );
  process.exit(1);
}
console.log(
  `check-hardcoded-strings: ${TARGETS.map((d) => `${path.relative(ROOT, d) || "."}/`).join(" ")} clean (every user-facing string goes through t()).`,
);
