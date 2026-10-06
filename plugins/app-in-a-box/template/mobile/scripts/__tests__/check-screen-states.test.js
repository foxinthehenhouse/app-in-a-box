const { test } = require("node:test");
const { runOnTemplate, runOnTree, assertRefuses, assertPasses } = require("./check-helpers");

const GUARD = "check-screen-states";

// A data screen the way the template writes one: each state through its component.
const honest = [
  "export default function Runs() {",
  "  const runs = useLoaded(useRuns());",
  "  return (",
  "    <Screen testID=\"runs-screen\">",
  "      {runs.loading ? (",
  "        <SkeletonCard testID=\"runs-skeleton\" />",
  "      ) : runs.error && !runs.data ? (",
  "        <ErrorNotice message={runs.error} onRetry={runs.reload} />",
  "      ) : runs.data?.length ? (",
  "        <RunList runs={runs.data} />",
  "      ) : (",
  "        <EmptyState icon={ICON} title={t(\"runs.emptyTitle\")} body={t(\"runs.emptyBody\")} />",
  "      )}",
  "    </Screen>",
  "  );",
  "}",
].join("\n");

test("passes on the pristine template", () => {
  assertPasses(runOnTemplate(GUARD), "template");
});

test("a screen with all three states passes, and so does one that loads nothing", () => {
  assertPasses(runOnTree(GUARD, { "app/(app)/runs.tsx": honest }), "honest screen");
  const still = "export default function About() {\n  return <Screen><Body>{t(\"about.body\")}</Body></Screen>;\n}\n";
  assertPasses(runOnTree(GUARD, { "app/(app)/about.tsx": still }), "no data");
});

for (const [label, from, to, needle] of [
  ["a spinner instead of a skeleton", '<SkeletonCard testID="runs-skeleton" />', "<ActivityIndicator />", /runs.tsx: missing-loading-state/],
  ["an error that renders nothing", "<ErrorNotice message={runs.error} onRetry={runs.reload} />", "null", /runs.tsx: missing-error-state/],
  ["an empty list left blank", '<EmptyState icon={ICON} title={t("runs.emptyTitle")} body={t("runs.emptyBody")} />', "<RunList runs={[]} />", /runs.tsx: missing-empty-state/],
]) {
  test(`refuses ${label}`, () => {
    assertRefuses(runOnTree(GUARD, { "app/(app)/runs.tsx": honest.replace(from, to) }), needle, label);
  });
}

test("a raw useQuery counts as loading data, even in a nested route", () => {
  const code = "export default function Day() {\n  const q = useQuery({ queryKey: [\"day\"], queryFn: getDay });\n  return <DayView day={q.data} />;\n}\n";
  assertRefuses(runOnTree(GUARD, { "app/(app)/days/[id].tsx": code }), /days\/\[id\].tsx: missing-loading-state/, "nested useQuery");
});

test("a state named only in a comment doesn't count", () => {
  const code = honest.replace('<EmptyState icon={ICON} title={t("runs.emptyTitle")} body={t("runs.emptyBody")} />', "null /* <EmptyState> later */");
  assertRefuses(runOnTree(GUARD, { "app/(app)/runs.tsx": code }), /missing-empty-state/, "comment mention");
});

test("a reasoned `// states:` waives the file; a bare one does not", () => {
  const bare = honest.replace("<ErrorNotice message={runs.error} onRetry={runs.reload} />", "null");
  const waived = "// states: errors surface as a toast from the shared mutation hook\n" + bare;
  assertPasses(runOnTree(GUARD, { "app/(app)/runs.tsx": waived }), "reasoned waiver");
  assertRefuses(runOnTree(GUARD, { "app/(app)/runs.tsx": "// states:\n" + bare }), /missing-error-state/, "bare waiver");
});

test("layouts and screens outside app/(app)/ are not checked", () => {
  const code = "export default function L() {\n  const q = useLoaded(useMe());\n  return <Slot />;\n}\n";
  assertPasses(runOnTree(GUARD, { "app/(app)/_layout.tsx": code, "app/edit-name.tsx": code }), "skipped files");
});
