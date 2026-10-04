const { test } = require("node:test");
const { runOnTemplate, runOnTree, assertRefuses, assertPasses } = require("./check-helpers");

const GUARD = "check-design-tells";

test("passes on the pristine template", () => {
  assertPasses(runOnTemplate(GUARD), "template");
});

test("the house style passes: tokens, springs, a Card holding rows", () => {
  const tree = {
    "components/ui/Panel.tsx": [
      'import { springTo } from "../../lib/motion";',
      "export function Panel() {",
      "  return (",
      '    <Card onPress={() => go("x")} style={{ borderWidth: 1, shadowRadius: 12 }}>',
      "      <ListRow title={t(\"home.recent\")} />",
      "      <Divider />",
      "    </Card>",
      "  );",
      "}",
      "const ease = Easing.bezier(0.16, 1, 0.3, 1);",
    ].join("\n"),
    "locales/en.ts": 'export default { home: { streak: "Seven days in a row 🔥 keep going" } };\n',
  };
  assertPasses(runOnTree(GUARD, tree), "house style");
});

for (const [label, file, code, needle] of [
  ["Easing.bounce on an entrance", "components/ui/Reveal.tsx", "withTiming(1, { duration: 400, easing: Easing.bounce })", /bounce-easing/],
  ["Easing.back copied from a tutorial", "app/(app)/home.tsx", "const enter = FadeInUp.easing(Easing.back(1.7));", /bounce-easing/],
  ["a hand-rolled overshoot bezier", "lib/anim.ts", "export const pop = Easing.bezier(0.34, 1.56, 0.64, 1);", /bounce-easing: Easing.bezier\(0.34, 1.56/],
  ["a coloured callout stripe", "components/ui/Callout.tsx", "const s = StyleSheet.create({ box: { borderLeftWidth: 4, borderColor: colors.accent } });", /side-stripe/],
  ["a neobrutal hard shadow", "components/ui/Tile.tsx", "const s = { shadowOffset: { width: 4, height: 4 }, shadowRadius: 0, shadowOpacity: 1 };", /hard-shadow/],
  ["a hard box shadow string", "components/ui/Tile.tsx", 'const s = { boxShadow: "4px 4px 0px #000" };', /hard-shadow/],
  ["an emoji as a list bullet in copy", "locales/en.ts", 'export default { tips: { one: "✅ Drink water" } };', /emoji-ui: a string that starts with an emoji/],
  ["an emoji as an icon prop", "app/(app)/home.tsx", '<StatCard icon="🔥" value={streak} />', /emoji-ui/],
]) {
  test(`refuses ${label}`, () => {
    assertRefuses(runOnTree(GUARD, { [file]: code + "\n" }), needle, label);
  });
}

test("refuses a Card nested in a Card, even with arrow functions in the props", () => {
  const code = [
    "export default function Home() {",
    "  return (",
    '    <Card onPress={() => router.push("/a")}>',
    "      <Body>{t(\"home.today\")}</Body>",
    '      <Card tone="raised" onPress={() => open()}>',
    "        <Body>{t(\"home.inner\")}</Body>",
    "      </Card>",
    "    </Card>",
    "  );",
    "}",
  ].join("\n");
  assertRefuses(runOnTree(GUARD, { "app/(app)/home.tsx": code }), /home.tsx:5: nested-card/, "nested card");
});

test("siblings are not nesting: two Cards one after another pass", () => {
  const code = "<>\n  <Card><Body /></Card>\n  <Card onPress={() => x()}><Body /></Card>\n  <Card />\n</>\n";
  assertPasses(runOnTree(GUARD, { "app/(app)/home.tsx": code }), "siblings");
});

test("refuses gradient text", () => {
  const code = '<MaskedView maskElement={<Title>{t("hero")}</Title>}>\n  <LinearGradient colors={[colors.accent, colors.success]} />\n</MaskedView>\n';
  assertRefuses(runOnTree(GUARD, { "components/ui/Hero.tsx": code }), /gradient-text/, "gradient text");
});

test("a reasoned design-ignore waives one line; a bare one does not", () => {
  const ok = "const s = { borderLeftWidth: 3 }; // design-ignore: timeline rail, not a callout\n";
  assertPasses(runOnTree(GUARD, { "components/ui/Timeline.tsx": ok }), "reasoned ignore");
  const bare = "const s = { borderLeftWidth: 3 }; // design-ignore:\n";
  assertRefuses(runOnTree(GUARD, { "components/ui/Timeline.tsx": bare }), /side-stripe/, "bare ignore");
});
