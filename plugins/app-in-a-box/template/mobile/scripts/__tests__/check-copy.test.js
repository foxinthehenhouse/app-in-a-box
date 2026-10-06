const { test } = require("node:test");
const { runOnTemplate, runOnTree, assertRefuses, assertPasses } = require("./check-helpers");

const GUARD = "check-copy";

/** A locale file in en.ts's shape, with `extra` lines dropped into its `errors` group. */
function locale(extra, ignore = "") {
  return [
    "export const en = {",
    "  common: {",
    '    save: "Save",',
    '    export: "Download your data as a JSON file",',
    "  },",
    "  errors: {",
    '    offline: "You\'re offline. Changes sync when you reconnect.",',
    '    generic: "Something went wrong. Try again.",',
    "    misconfigured:",
    '      "This version can\'t reach its server. Update the app.",',
    ...extra.map((l) => `    ${l}`),
    "  },",
    "} as const;",
    "",
    "export const _copyIgnore = {",
    ignore,
    "} as const;",
    "",
  ].join("\n");
}
const tree = (extra, ignore) => ({ "locales/en.ts": locale(extra, ignore) });

test("passes on the pristine template", () => {
  assertPasses(runOnTemplate(GUARD), "template");
});

test("the house voice passes: a reason or a next step, acronyms, a wrapped value", () => {
  assertPasses(runOnTree(GUARD, tree(['saveFailed: "Couldn\'t save your entry. It\'s back to what it was.",'])), "house voice");
});

for (const [label, line, needle] of [
  ["an Oops", 'load: "Oops! Couldn\'t load your runs.",', /errors.load: banned-phrase: an "Oops"/],
  ["Error occurred", 'save: "An error occurred while saving. Try again.",', /errors.save: banned-phrase: "Error occurred"/],
  ["Click, from a web port", 'stale: "Click here to refresh the page.",', /banned-phrase: "Click"/],
  ["Please note", 'note: "Please note: sync is paused. Try again later.",', /banned-phrase: "Please note"/],
  ["Invalid", 'email: "Invalid email. Enter it again.",', /banned-phrase: "Invalid"/],
  ["a bare Something went wrong", 'boom: "Something went wrong.",', /errors.boom: banned-phrase: "Something went wrong" with no next step/],
  ["a shouted word", 'limit: "STOP. Too many tries, wait a minute.",', /shouting: "STOP"/],
  ["an exclamation run", 'cheer: "Saved!! Nice one.",', /exclamation: "!!"/],
  ["an exclamation in an error", 'upload: "Upload failed! Check your connection.",', /errors.upload: exclamation: an "!" in an error string/],
  ["an error with no way forward", 'sync: "Sync problem.",', /errors.sync: no-way-forward/],
  ["a value prettier wrapped onto the next line", 'sync:\n      "Sync problem.",', /errors.sync: no-way-forward/],
]) {
  test(`refuses ${label}`, () => {
    assertRefuses(runOnTree(GUARD, tree([line])), needle, label);
  });
}

test("a failed-key outside `errors` is an error string too", () => {
  const src = locale([]).replace('save: "Save",', 'save: "Save",\n    saveFailed: "Not saved.",');
  assertRefuses(runOnTree(GUARD, { "locales/en.ts": src }), /common.saveFailed: no-way-forward/, "failed key");
});

test("a JSON locale is read too, with its own top-level _copyIgnore", () => {
  const bad = JSON.stringify({ errors: { boom: "Whoops." } });
  assertRefuses(runOnTree(GUARD, { "locales/de.json": bad }), /locales\/de.json: errors.boom: banned-phrase/, "json");
  const waived = JSON.stringify({ errors: { boom: "Whoops." }, _copyIgnore: { "errors.boom": "a brand mascot's catchphrase" } });
  assertPasses(runOnTree(GUARD, { "locales/de.json": waived }), "json waiver");
});

test("a reasoned _copyIgnore entry waives one key; an empty reason does not", () => {
  const line = 'confirm: "Type DELETE to confirm. Nothing was removed yet.",';
  assertPasses(runOnTree(GUARD, tree([line], '  "errors.confirm": "DELETE is the word the user types",')), "reasoned");
  assertRefuses(runOnTree(GUARD, tree([line], '  "errors.confirm": "",')), /shouting: "DELETE"/, "empty reason");
});
