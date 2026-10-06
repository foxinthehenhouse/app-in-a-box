#!/usr/bin/env node
/**
 * Copy voice lint (part of `npm run gates`): the habits that make an app sound like a
 * form from 2009 instead of a person who wants you to get somewhere. Every rule is in
 * the Copy section of docs/design/TASTE.md. It reads every string in locales/*.ts (and
 * locales/*.json, if you keep any) by its key path, `errors.generic`.
 *
 *   banned-phrase   "Oops", "Whoops", "Error occurred", "Please note", "Invalid", and
 *                   "Click" (people tap); "Something went wrong" with no next step
 *   shouting        an ALL CAPS word over 3 letters, unless it is in ACRONYMS below
 *   exclamation     "!!" anywhere, or any "!" in an error string (it isn't exciting)
 *   no-way-forward  an error string (key path matching /error|failed/) that gives
 *                   neither a reason ("couldn't reach the server") nor a next step
 *                   ("Try again", "Check your connection")
 *
 * Escape hatch, with a reason a reviewer can judge: the locale file's `_copyIgnore` map,
 * `"<key path>": "<why>"` (an export beside the strings in a .ts locale, a top-level key
 * in a .json one). An entry with an empty reason waives nothing.
 *
 * Pragmatic line parsing, not a TypeScript parser: it runs with no node_modules (the kit
 * selftest calls it on a fresh render). Keep one string per key, as en.ts does.
 *
 *   node scripts/check-copy.js
 * Self-tests: scripts/__tests__/check-copy.test.js
 */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const LOCALES = path.join(ROOT, "locales");
// Real acronyms are fine in capitals. Add yours with the word, never a whole phrase.
const ACRONYMS = new Set(["JSON", "HTML", "HTTP", "HTTPS", "GDPR", "CCPA", "HIPAA", "COPPA", "OAUTH", "JPEG", "HEIC", "HEIF", "WEBP"]);
const ERROR_KEY = /error|failed/i;
const NEXT_STEP =
  /(^|[.?:]\s+)(try|check|sign|update|contact|wait|send|enter|turn|use|go|restart|include|copy|tap|open|ask|choose|pick|add|remove|reload|refresh|reconnect|save|type|keep|allow|connect|install)\b|try again|contact support/i;
const REASON =
  /\b(because|couldn't|can't|cannot|isn't|wasn't|didn't|doesn't|won't|hasn't|haven't|expired|offline|unreachable|too many|too long|no longer|already|nothing was|back to what it was|ended|not set up|not available|ran out|is full|is off)\b/i;
const BANNED = [
  [/\b(oops|whoops)\b/i, "an \"Oops\" (say what happened instead)"],
  [/\berror occurred\b/i, "\"Error occurred\" (say what failed and what to do)"],
  [/\bplease note\b/i, "\"Please note\" (just say it)"],
  [/\binvalid\b/i, "\"Invalid\" (say what a good value looks like)"],
  [/\bclick(s|ed|ing)?\b/i, "\"Click\" (people tap; or name the action)"],
];

/** `key: "value"` / `"key.path": 'value'` on one line (or the value on the next line). */
const KEY = /^\s*(?:"([^"]+)"|'([^']+)'|([A-Za-z_$][\w$]*))\s*:\s*/;
const STR = /^(["'`])((?:\\.|(?!\1).)*)\1\s*,?\s*$/;

function unescape(s) {
  return s.replace(/\\(.)/g, "$1");
}

/** A .ts locale -> { strings: [{key, value, line}], ignore: {key: why} }. */
function parseTs(src) {
  const strings = [];
  const ignore = {};
  const stack = [];
  let block = null;
  const lines = src.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const top = line.match(/^export const ([\w$]+)\s*(?::[^=]+)?=\s*\{\s*$/);
    if (top) { block = top[1]; stack.length = 0; continue; }
    if (!block) continue;
    if (/^\s*\}/.test(line)) { if (stack.length) stack.pop(); else block = null; continue; }
    const k = line.match(KEY);
    if (!k) continue;
    const key = k[1] || k[2] || k[3];
    let rest = line.slice(k[0].length);
    if (/^\{\s*$/.test(rest)) { stack.push(key); continue; }
    if (rest.trim() === "" && i + 1 < lines.length) rest = lines[++i].trim();
    const v = rest.match(STR);
    if (!v) continue;
    if (block === "_copyIgnore") ignore[key] = unescape(v[2]);
    else strings.push({ key: [...stack, key].join("."), value: unescape(v[2]), line: i + 1 });
  }
  return { strings, ignore };
}

function parseJson(src) {
  const data = JSON.parse(src);
  const ignore = data._copyIgnore || {};
  const strings = [];
  const flat = (obj, pre) => {
    for (const [k, v] of Object.entries(obj)) {
      if (!pre && k === "_copyIgnore") continue;
      const key = pre ? `${pre}.${k}` : k;
      if (typeof v === "string") strings.push({ key, value: v, line: 0 });
      else if (v && typeof v === "object") flat(v, key);
    }
  };
  flat(data, "");
  return { strings, ignore };
}

/** Every rule a string breaks, as `rule: why`. */
function problems(key, raw) {
  const text = raw.replace(/\{\{\s*[\w.]+\s*\}\}/g, "");
  const out = [];
  const isError = ERROR_KEY.test(key);
  const forward = NEXT_STEP.test(text) || REASON.test(text);
  for (const [re, why] of BANNED) if (re.test(text)) out.push(`banned-phrase: ${why}`);
  if (/something went wrong/i.test(text) && !NEXT_STEP.test(text)) {
    out.push("banned-phrase: \"Something went wrong\" with no next step");
  }
  for (const w of text.match(/\b[A-Z]{4,}\b/g) || []) {
    if (!ACRONYMS.has(w)) out.push(`shouting: "${w}" in capitals (add it to ACRONYMS if it is one)`);
  }
  if (/!!/.test(text)) out.push("exclamation: \"!!\"");
  else if (isError && text.includes("!")) out.push("exclamation: an \"!\" in an error string");
  if (isError && !forward) out.push("no-way-forward: an error with no reason and no next step");
  return out;
}

const hits = [];
const files = fs.existsSync(LOCALES) ? fs.readdirSync(LOCALES).filter((f) => /\.(ts|json)$/.test(f) && !f.startsWith("_")) : [];
for (const f of files.sort()) {
  const src = fs.readFileSync(path.join(LOCALES, f), "utf8");
  const { strings, ignore } = f.endsWith(".json") ? parseJson(src) : parseTs(src);
  for (const { key, value, line } of strings) {
    if (typeof ignore[key] === "string" && ignore[key].trim()) continue;
    for (const p of problems(key, value)) hits.push(`locales/${f}${line ? `:${line}` : ""}: ${key}: ${p}`);
  }
}

if (hits.length) {
  console.error("check-copy FAILED (docs/design/TASTE.md, Copy):\n  - " + hits.join("\n  - "));
  console.error('A deliberate exception? Add it to the locale\'s `_copyIgnore` map: "<key>": "<why>".');
  process.exit(1);
}
console.log(`check-copy: ${files.length} locale file(s) read; the copy is in the house voice.`);
