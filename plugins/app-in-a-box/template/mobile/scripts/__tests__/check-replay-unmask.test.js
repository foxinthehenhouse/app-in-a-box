const { test } = require("node:test");
const { runOnTemplate, runOnTree, assertRefuses, assertPasses } = require("./check-helpers");

const GUARD = "check-replay-unmask";
const ok = (replay) => ({
  "lib/analytics.ts": `export const posthog = new PostHog(KEY, {\n  enableSessionReplay: false,\n  sessionReplayConfig: ${replay},\n});\n`,
});

test("passes on the pristine template", () => {
  assertPasses(runOnTemplate(GUARD), "template");
});

test("the masked default passes", () => {
  assertPasses(runOnTree(GUARD, ok("{ maskAllTextInputs: true, maskAllImages: true }")), "masked");
});

for (const [label, replay, needle] of [
  ["the literal false", "{ maskAllTextInputs: false, maskAllImages: true }", /maskAll\* option set to something other than the literal true/],
  ["a negated flag from props", "{ maskAllTextInputs: !showText, maskAllImages: true }", /other than the literal true/],
  ["a constant", "{ maskAllTextInputs: true, maskAllImages: MASK_IMAGES }", /other than the literal true/],
  ["the shorthand property", "{ maskAllTextInputs, maskAllImages: true }", /shorthand property/],
  ["an empty config (inherits the SDK default instead of stating it)", "{}", /empty sessionReplayConfig/],
]) {
  test(`refuses ${label}`, () => {
    assertRefuses(runOnTree(GUARD, ok(replay)), needle, label);
  });
}

test("refuses an unmask API call anywhere in app code", () => {
  const tree = { ...ok("{ maskAllTextInputs: true, maskAllImages: true }"), "components/ui/Field.tsx": "posthog?.unmaskView(ref.current);\n" };
  assertRefuses(runOnTree(GUARD, tree), /unmask API call/, "unmask call");
});
