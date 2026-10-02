/**
 * The design-token contrast gate (../scripts/check_contrast.py at the repo root, run by
 * `npm run gates` from mobile/). Positive control: the repo's own tokens pass. Negative
 * controls, written as a designer or a future component author would:
 *   - a brighter brand orange for the light accent (sub-AA as text on a control);
 *   - `success` added back to <Text>'s tones (the gate must then hold it to 4.5:1).
 */
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

const MOBILE = path.resolve(__dirname, "..", "..");
const REPO = path.resolve(MOBILE, "..");
const GATE = path.join(REPO, "scripts", "check_contrast.py");
const TOKENS = path.join(REPO, "design", "tokens.json");

function gate(tokensPath) {
  const r = spawnSync("python3", [GATE, tokensPath], { encoding: "utf8" });
  return { status: r.status, out: `${r.stdout}\n${r.stderr}` };
}

/** A copy of the repo's design/ + the component files the gate reads, with `edit` applied. */
function repoCopy(edit) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "contrast-"));
  fs.mkdirSync(path.join(root, "design"));
  for (const rel of ["components/ui/Text.tsx", "components/ui/Button.tsx", "lib/theme.ts"]) {
    fs.mkdirSync(path.dirname(path.join(root, "mobile", rel)), { recursive: true });
    fs.copyFileSync(path.join(MOBILE, rel), path.join(root, "mobile", rel));
  }
  const tokens = JSON.parse(fs.readFileSync(TOKENS, "utf8"));
  edit(tokens, root);
  fs.writeFileSync(path.join(root, "design", "tokens.json"), JSON.stringify(tokens));
  return path.join(root, "design", "tokens.json");
}

test("the repo's tokens pass, checking accent and danger as text", () => {
  const r = gate(TOKENS);
  assert.equal(r.status, 0, r.out);
  assert.match(r.out, /text tokens: .*accent.*danger/);
});

test("a brighter light accent fails as TEXT on a control, not just as an icon", () => {
  const r = gate(repoCopy((t) => (t.color.light.accent = "#E8590C")));
  assert.equal(r.status, 1, r.out);
  assert.match(r.out, /\[light\] accent #E8590C on control .*\(< 4\.5 for text\)/);
});

test("adding success as a <Text> tone makes the gate hold success to 4.5:1", () => {
  const r = gate(
    repoCopy((_t, root) => {
      const p = path.join(root, "mobile", "components", "ui", "Text.tsx");
      const src = fs.readFileSync(p, "utf8");
      assert.ok(src.includes('danger: "danger",'), "Text.tsx TONE map moved; update this test");
      fs.writeFileSync(p, src.replace('danger: "danger",', 'danger: "danger",\n  success: "success",'));
    }),
  );
  assert.equal(r.status, 1, r.out);
  assert.match(r.out, /\[light\] success .* on control .*\(< 4\.5 for text\)/);
});
