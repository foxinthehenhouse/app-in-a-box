const { test } = require("node:test");
const { runOnTemplate, runOnTree, assertRefuses, assertPasses } = require("./check-helpers");

const GUARD = "check-a11y";

test("passes on the pristine template", () => {
  assertPasses(runOnTemplate(GUARD), "template");
});

test("the house style passes: labelled controls, decorative images, motion presets", () => {
  const tree = {
    "app/(app)/journal.tsx": [
      'import { Image, Pressable, TextInput } from "react-native";',
      'import { animateTo, springTo } from "../../lib/motion";',
      "export default function Journal() {",
      "  return (",
      "    <>",
      '      <Pressable onPress={() => go("/x")} accessibilityRole="button" accessibilityLabel={t("journal.open")}>',
      "        <Body>{t(\"journal.title\")}</Body>",
      "      </Pressable>",
      '      <TextInput accessibilityLabel={t("journal.note")} onChangeText={setNote} />',
      '      <Image source={hero} accessible={false} />',
      '      <Image source={{ uri }} accessibilityLabel={t("journal.photo")} />',
      "    </>",
      "  );",
      "}",
      'x.set(withTiming(1, timing("fast")));',
      "y.set(withSpring(0, { damping: 20, reduceMotion: ReduceMotion.System }));",
    ].join("\n"),
    "components/ui/Tap.tsx": "export function Tap(props: P) {\n  return <Pressable {...props} />;\n}\n",
    "locales/en.ts": 'export default { journal: { openLabel: "Open the journal" } };\n',
  };
  assertPasses(runOnTree(GUARD, tree), "house style");
});

for (const [label, file, code, needle] of [
  ["a Pressable row copied without a label", "app/(app)/home.tsx",
    '<Pressable onPress={() => router.push("/entry")} accessibilityRole="button">\n  <Icon sf="plus" md="add" />\n</Pressable>', /home.tsx:1: unlabelled-control: <Pressable>/],
  ["a TouchableOpacity with a label but no role", "app/(app)/home.tsx",
    '<TouchableOpacity\n  onPress={save}\n  accessibilityLabel="Save entry"\n>', /home.tsx:1: no-role: <TouchableOpacity>/],
  ["a Pressable whose label is an empty string", "app/(app)/home.tsx",
    '<Pressable onPress={open} accessibilityRole="button" accessibilityLabel="" />', /unlabelled-control: <Pressable>/],
  ["a TextInput with only a placeholder", "app/edit-name.tsx",
    '<TextInput placeholder="Your name" value={name} onChangeText={setName} />', /unlabelled-control: <TextInput>/],
  ["a screen-level forwarding Pressable (the wrapper allowance is the kit's only)", "app/(app)/home.tsx",
    "<Pressable {...rowProps} onPress={open} />", /unlabelled-control: <Pressable>/],
  ["a bare <Image> from react-native", "app/(app)/home.tsx",
    'import { Image } from "react-native";\nexport const Hero = () => <Image source={hero} style={s.hero} />;', /home.tsx:2: unlabelled-image/],
  ["an expo-image with neither label nor accessible={false}", "components/ui/Cover.tsx",
    'import { Image } from "expo-image";\nexport const Cover = () => (\n  <Image\n    source={{ uri }}\n    contentFit="cover"\n  />\n);', /Cover.tsx:3: unlabelled-image/],
  ["a label that restates its role", "app/(app)/settings.tsx",
    '<IconButton sf="gear" md="settings" accessibilityLabel="Settings button" onPress={open} />', /label-restates-role: "Settings button"/],
  ["a locale label that restates its role", "locales/en.ts",
    'export default { home: { addLabel: "Add entry button" } };', /locales\/en.ts:1: label-restates-role/],
  ["allowFontScaling={false} on a label", "app/(app)/home.tsx",
    "<RNText allowFontScaling={false}>{count}</RNText>", /no-font-scaling/],
  ["a font cap under 1.3 in a screen", "app/(app)/home.tsx",
    '<Text variant="title" maxFontSizeMultiplier={1.1}>{t("home.title")}</Text>', /low-font-cap: maxFontSizeMultiplier 1.1/],
  ["a hand-rolled withTiming in a screen", "app/(app)/home.tsx",
    "opacity.value = withTiming(1, { duration: 300 });", /motion-ignores-os: withTiming\(\)/],
  ["a withSpring with a raw config in lib", "lib/drawer.ts",
    "export const open = (x: SharedValue<number>) => x.set(withSpring(0, { damping: 12, stiffness: 180 }));", /lib\/drawer.ts:1: motion-ignores-os: withSpring/],
  ["an RN Animated.timing that never asks the OS", "components/ui/Pulse.tsx",
    "Animated.timing(v, { toValue: 1, duration: 600, useNativeDriver: true }).start();", /motion-ignores-os: Animated.timing/],
]) {
  test(`refuses ${label}`, () => {
    assertRefuses(runOnTree(GUARD, { [file]: code + "\n" }), needle, label);
  });
}

test("the kit may cap a role under 1.3 (it already caps from tokens)", () => {
  const code = '<Text variant="meta" maxFontSizeMultiplier={1}>{initials}</Text>\n';
  assertPasses(runOnTree(GUARD, { "components/ui/Badge.tsx": code }), "kit cap");
});

test("an RN Animated.timing gated on Reduce Motion passes", () => {
  const code = "const reduced = useReducedMotion();\nif (!reduced) Animated.timing(v, { toValue: 1, useNativeDriver: true }).start();\n";
  assertPasses(runOnTree(GUARD, { "components/ui/Pulse.tsx": code }), "gated Animated");
});

test("a reasoned a11y-ignore waives one tag; a bare one does not", () => {
  const ok = '{/* a11y-ignore: the whole card is one button; its parent carries the label */}\n<Pressable onPress={open} />\n';
  assertPasses(runOnTree(GUARD, { "app/(app)/home.tsx": ok }), "reasoned ignore");
  const bare = "<Pressable onPress={open} /> // a11y-ignore:\n";
  assertRefuses(runOnTree(GUARD, { "app/(app)/home.tsx": bare }), /unlabelled-control/, "bare ignore");
});
