/**
 * Shared harness for the guard self-tests (node:test, no node_modules).
 *
 * Each guard resolves its project root as `path.resolve(__dirname, "..")`, so to run one
 * against a planted tree we copy scripts/ into a temp dir and lay the fixture beside it.
 * Two controls per guard, always:
 *   - positive: the guard passes on the pristine template (this very mobile/ folder);
 *   - negative: a planted violation, written the way a future editor would write it
 *     (copied from an older screen, a "reasonable" refactor), not in the regex's own
 *     words, fails AND names the rule that fired. A plant that fails for an unrelated
 *     reason (a syntax error, a missing file) must not read as "caught".
 */
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const MOBILE = path.resolve(__dirname, "..", "..");
const SCRIPTS = path.join(MOBILE, "scripts");

/** Run a guard in place against the real template. */
function runOnTemplate(guard, args = []) {
  return run(path.join(SCRIPTS, `${guard}.js`), args, MOBILE);
}

/** Build a temp project from `files` ({ "lib/x.ts": "..." }) plus the real guard scripts, then run `guard`. */
function runOnTree(guard, files, args = []) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "guard-"));
  fs.mkdirSync(path.join(root, "scripts"));
  for (const f of fs.readdirSync(SCRIPTS)) {
    if (f.endsWith(".js")) fs.copyFileSync(path.join(SCRIPTS, f), path.join(root, "scripts", f));
  }
  for (const [rel, content] of Object.entries(files)) {
    const p = path.join(root, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, content);
  }
  try {
    return run(path.join(root, "scripts", `${guard}.js`), args, root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function run(script, args, cwd) {
  const r = spawnSync(process.execPath, [script, ...args], { cwd, encoding: "utf8" });
  return { status: r.status, out: `${r.stdout}\n${r.stderr}` };
}

/** The guard must exit non-zero AND its output must name the rule (`needle`). */
function assertRefuses(result, needle, label) {
  assert.notEqual(result.status, 0, `${label}: expected the guard to fail, but it passed:\n${result.out}`);
  assert.match(result.out, needle instanceof RegExp ? needle : new RegExp(escape(needle)), `${label}: failed, but not on the expected rule:\n${result.out}`);
}

function assertPasses(result, label) {
  assert.equal(result.status, 0, `${label}: expected the guard to pass:\n${result.out}`);
}

function escape(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

module.exports = { MOBILE, runOnTemplate, runOnTree, assertRefuses, assertPasses };
