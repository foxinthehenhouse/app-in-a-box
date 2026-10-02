const { test } = require("node:test");
const { runOnTemplate, runOnTree, assertRefuses, assertPasses } = require("./check-helpers");

const GUARD = "check-hardcoded-strings";
const screen = (jsx) => ({
  "app/(app)/index.tsx": `import { Text } from "react-native";\nexport default function Home({ name, ok, label }: Props) {\n  return (\n    <Text>\n      ${jsx}\n    </Text>\n  );\n}\n`,
});

test("passes on the pristine template", () => {
  assertPasses(runOnTemplate(GUARD), "template");
});

for (const [label, jsx, needle] of [
  ["a template literal as JSX text", "{`Welcome back`}", "template literal as JSX text"],
  ["a template literal with a placeholder and copy", "{`Hi ${name}, welcome back`}", "template literal as JSX text"],
  ["string concatenation", '{"Hello, " + name}', "string literal in a JSX expression"],
  ["a conditional with two literals", '{ok ? "Saved" : "Failed"}', "string literal in a JSX expression"],
  ["a conditional with one literal branch", '{ok ? "Saved" : label}', "string literal in a JSX expression"],
]) {
  test(`refuses ${label}`, () => {
    assertRefuses(runOnTree(GUARD, screen(jsx)), needle, label);
  });
}

test("a template literal that is only a glyph plus data passes", () => {
  assertPasses(runOnTree(GUARD, screen("{`✓ ${label}`}")), "glyph + placeholder");
});

test("a non-user-facing prop picking between token names passes", () => {
  const tree = {
    "components/ui/Tab.tsx": 'import { Text } from "./Text";\nexport function Tab({ on, label }: P) {\n  return <Text tone={on ? "default" : "dim"}>{label}</Text>;\n}\n',
  };
  assertPasses(runOnTree(GUARD, tree), "token-name ternary in a prop");
});
