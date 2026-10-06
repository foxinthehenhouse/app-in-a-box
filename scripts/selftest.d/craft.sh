# Craft bar: sourced by selftest.sh with $KIT, $APP (rendered app), $T and the
# check/refuses/skip helpers. The kit's design craft (shape, directions, prototype,
# freeze, TASTE.md) carried through feature work and review. Each mechanical rule passes
# on the pristine template and FAILS, naming its rule, on a planted violation:
#   check-screen-states.js   a data screen under app/(app)/ renders Skeleton, ErrorNotice
#                            and EmptyState, or says why (`// states: <why>`)
#   check-copy.js            TASTE.md's Copy rules over locales/ (`_copyIgnore` waivers)
#   check-design-tells.js    raw-pressable: a bare Pressable/Touchable outside the ui kit
#   docs/design/CRAFT.md     every component it names exists in the app
#   craft-reviewer           a read-only role (it grades, it never edits)
#   scripts/screenshots.sh   the routes a branch changed; a PNG per route and mode in a
#                            real export (--mobile, mobile_check_craft at the bottom)
CR_MOB="$KIT/template/mobile"

_cr_copy() {  # a throwaway copy of the rendered app's mobile guards + sources at $T/cr
  rm -rf "$T/cr"; mkdir -p "$T/cr"
  (cd "$APP/mobile" && tar --exclude=node_modules -cf - app components lib locales scripts) | (cd "$T/cr" && tar -xf -)
}
_cr_guard() {  # <guard> <expected message>: the guard must fail on $T/cr, naming the rule
  local out; out=$(cd "$T/cr" && node "scripts/$1.js" 2>&1) && { echo "still green"; return 1; }
  grep -qF -- "$2" <<<"$out" || { printf '%s\n' "$out"; return 1; }
}

# ---- the three mobile guards: template green, self-tests green, wired into gates --------
if command -v node >/dev/null 2>&1; then
  check "craft: check-screen-states, check-copy and check-design-tells pass on the template, with their self-tests" \
    "cd '$CR_MOB' && node scripts/check-screen-states.js && node scripts/check-copy.js && node scripts/check-design-tells.js \
     && node --test scripts/__tests__/check-screen-states.test.js scripts/__tests__/check-copy.test.js scripts/__tests__/check-design-tells.test.js"

  _cr_states_plant() {
    _cr_copy
    cat > "$T/cr/app/(app)/runs.tsx" <<'TSX'
export default function Runs() {
  const runs = useLoaded(useRuns());
  return <Screen testID="runs-screen">{runs.loading ? <SkeletonCard /> : <RunList runs={runs.data ?? []} />}</Screen>;
}
TSX
    _cr_guard check-screen-states "app/(app)/runs.tsx: missing-error-state" && _cr_guard check-screen-states "missing-empty-state" || return 1
    sed -i '1i // states: a feed that is never empty; errors surface in the shared toast' "$T/cr/app/(app)/runs.tsx"
    (cd "$T/cr" && node scripts/check-screen-states.js >/dev/null)
  }
  check "craft catches: a data screen with no error or empty state (and a reasoned // states: waives it)" "_cr_states_plant"

  _cr_copy_line() {  # <key> <new value> <expected message>: the first `key: "..."` in en.ts
    _cr_copy
    python3 - "$T/cr/locales/en.ts" "$1" "$2" <<'PY' || return 1
import re, sys
p, key, value = sys.argv[1:4]
s = open(p).read()
s, n = re.subn(rf'^(\s*{key}:\s*)".*"', lambda m: m.group(1) + '"' + value + '"', s, count=1, flags=re.M)
assert n == 1, key
open(p, "w").write(s)
PY
    _cr_guard check-copy "$3"
  }
  check "craft catches: an Oops in an error string" \
    '_cr_copy_line generic "Oops! Try again." "errors.generic: banned-phrase: an \"Oops\""'
  check "craft catches: an error with no reason and no next step" \
    '_cr_copy_line pushFailed "Notification error." "settings.pushFailed: no-way-forward"'
  check "craft catches: a shouted button label" \
    '_cr_copy_line restart "RESTART" "update.restart: shouting: \"RESTART\""'

  _cr_press_plant() {
    _cr_copy
    printf 'import { Pressable } from "react-native";\nexport function Row() {\n  return <Pressable onPress={go} accessibilityRole="button" accessibilityLabel={t("x")} />;\n}\n' > "$T/cr/components/Row.tsx"
    _cr_guard check-design-tells "components/Row.tsx:3: raw-pressable"
  }
  check "craft catches: a bare Pressable outside components/ui (no press feedback)" "_cr_press_plant"
else
  skip "craft: the mobile guards and their plants" "node"
fi
check "craft: check-screen-states and check-copy run in the app's npm run gates" \
  "grep -q 'node scripts/check-design-tells.js && node scripts/check-screen-states.js && node scripts/check-copy.js' '$KIT/scripts/mobile-deps.sh'"

# ---- CRAFT.md names real components; TASTE.md holds the copy rules ---------------------
_cr_names() {  # <CRAFT.md> <app>: every `Component` / `lib/x.ts` it names exists in the app
  python3 - "$1" "$2" <<'PY'
import re, sys, pathlib
craft, app = pathlib.Path(sys.argv[1]).read_text(), pathlib.Path(sys.argv[2])
exports = (app / "mobile/components/ui/index.ts").read_text()
rows = [ln for ln in craft.splitlines() if re.match(r"^\| \d+ \|", ln)]
assert len(rows) >= 8, f"only {len(rows)} rubric rows"
missing = []
for ln in rows:
    cells = ln.split("|")
    assert re.search(r"`[^`]+`", cells[-2]), f"row without a delivering component: {ln[:60]}"
    for name in re.findall(r"`([A-Z][A-Za-z]+)(?=[` ])", cells[-2]):
        if not re.search(rf"\b{name}\b", exports):
            missing.append(name)
    for f in re.findall(r"`((?:lib|scripts|app)/[\w./+()-]+\.(?:ts|tsx|js))`", ln):
        if not (app / "mobile" / f).exists():
            missing.append(f)
assert not missing, f"CRAFT.md names what the app doesn't have: {missing}"
PY
}
check "craft: CRAFT.md ships in the app, and every component and file it names exists" \
  "[ -f '$APP/docs/design/CRAFT.md' ] && _cr_names '$APP/docs/design/CRAFT.md' '$APP'"
check "craft catches: CRAFT.md naming a component the app doesn't have" \
  "sed 's/\`Skeleton\`, \`SkeletonCard\`/\`ShimmerList\`/' '$APP/docs/design/CRAFT.md' > '$T/craft-bad.md' && ! _cr_names '$T/craft-bad.md' '$APP' 2>'$T/craft-bad.out' && grep -q ShimmerList '$T/craft-bad.out'"
check "craft: TASTE.md's Copy section holds every rule check-copy enforces" \
  "for w in Oops Whoops 'Error occurred' 'Please note' Invalid Click 'Something went wrong' 'ALL CAPS' '!!' _copyIgnore; do grep -qF -- \"\$w\" '$APP/docs/design/TASTE.md' || { echo \"TASTE.md lacks: \$w\"; exit 1; }; done"

# ---- the path rule, the reviewer, the skills -------------------------------------------
check "craft: the craft rule is injected on a screen edit and listed for Codex" \
  "printf '{\"tool_input\":{\"file_path\":\"%s/mobile/app/(app)/index.tsx\"},\"session_id\":\"cr%s\"}' '$APP' \$RANDOM | CLAUDE_PROJECT_DIR='$APP' python3 '$APP/.claude/hooks/inject-path-rules.py' | grep -q 'craft.md' \
   && grep -q '\`.agents/rules/craft.md\`' '$APP/AGENTS.md'"
_cr_rule_unlisted() {  # the harness lint must fail when the rule drops out of AGENTS.md's table
  rm -rf "$T/cr-app"; mkdir -p "$T/cr-app"
  (cd "$APP" && tar --exclude=.venv --exclude=.git --exclude=node_modules -cf - .) | (cd "$T/cr-app" && tar -xf -)
  sed -i 's/, `.agents\/rules\/craft.md`//' "$T/cr-app/AGENTS.md"
  local out; out=$(cd "$T/cr-app" && "$APP/.venv/bin/python" -m pytest -q -p no:cacheprovider tests/harness/test_rules_lint.py -k listed 2>&1) && return 1
  grep -q "craft.md is not in AGENTS.md's path-rule table" <<<"$out"
}
check "craft catches: the craft rule missing from AGENTS.md's path-rule table (harness lint)" "_cr_rule_unlisted"

_cr_readonly() {  # <role .md>: a grader that can edit is a reviewer that "fixes" taste
  local tools; tools=$(sed -n 's/^tools: *//p' "$1")
  [ -n "$tools" ] && ! grep -qE '\b(Edit|Write|MultiEdit|NotebookEdit)\b' <<<"$tools"
}
check "craft: craft-reviewer is read-only, advisory, grades against CRAFT.md + TASTE.md + the frozen design, and has its Codex adapter" \
  "R='$APP/.agents/agents/craft-reviewer.md'; _cr_readonly \"\$R\" && grep -q 'docs/design/CRAFT.md' \"\$R\" && grep -q 'docs/design/TASTE.md' \"\$R\" \
   && grep -q 'design/tokens.json' \"\$R\" && grep -qi 'advisory' \"\$R\" && grep -q 'Must-fix' \"\$R\" && [ -f '$APP/.codex/agents/craft-reviewer.toml' ]"
check "craft catches: a craft-reviewer that can edit files" \
  "sed 's/^tools: .*/tools: Read, Grep, Glob, Bash, Edit/' '$APP/.agents/agents/craft-reviewer.md' > '$T/cr-role.md' && ! _cr_readonly '$T/cr-role.md'"
check "craft: pr-review shoots changed screens light + dark and spawns craft-reviewer, advisory (never a blocker)" \
  "P='$APP/.agents/skills/pr-review/SKILL.md'; grep -q 'scripts/screenshots.sh --changed' \"\$P\" && grep -q 'craft-reviewer' \"\$P\" \
   && grep -q 'light-<route>.png' \"\$P\" && grep -q 'dark-<route>.png' \"\$P\" && grep -q 'never count as blockers' \"\$P\" && grep -q '^Craft:' \"\$P\""
check "craft: build-feature stops at planning without a states table, and its definition of done cites CRAFT.md" \
  "B='$APP/.agents/skills/build-feature/SKILL.md'; grep -q 'States table, or stop' \"\$B\" && grep -q 'loading, empty, error, offline, success' \"\$B\" \
   && grep -q '## Definition of done' \"\$B\" && sed -n '/## Definition of done/,/## Never/p' \"\$B\" | grep -q 'docs/design/CRAFT.md' \
   && grep -q 'docs/design/CRAFT.md' '$APP/.agents/agents/design-a11y-reviewer.md'"
check "craft: feature-discovery's spec requires a states table and 3-5 reference screens per flow (Mobbin, else named apps)" \
  "F='$APP/.agents/skills/feature-discovery/SKILL.md'; grep -q 'rows loading, empty, error, offline, success' \"\$F\" && grep -q '## References' \"\$F\" \
   && grep -q '3–5 named reference screens per flow' \"\$F\" && grep -q 'Mobbin MCP' \"\$F\""
_cr_eval_seeds() {  # the eval's workspace really has a spec with no states table
  local w="$T/cr-eval"; rm -rf "$w"; mkdir -p "$w"
  (cd "$w" && bash "$APP/.agents/evals/08-build-feature-stops-without-states/setup.sh") >/dev/null 2>&1 || return 1
  local spec="$w/docs/product/specs/12-streak-history.md"
  [ -f "$spec" ] && grep -q '^## UX' "$spec" && ! sed -n '/^## UX/,/^## Data/p' "$spec" | grep -qi '| *loading'
}
check "craft: an eval case grades build-feature stopping on a spec with no states table (and seeds one)" \
  "E='$APP/.agents/evals/08-build-feature-stops-without-states'; grep -q '/build-feature' \"\$E/prompt.md\" && grep -q 'offline' \"\$E/graders/stops-and-asks.md\" && _cr_eval_seeds"

# ---- screenshots.sh: the routes it picks, and a clear skip without a browser -----------
_cr_routes() {  # a branch that changed one screen shoots that route; a component change, all
  local w="$T/cr-git"; rm -rf "$w"; mkdir -p "$w"
  (cd "$APP" && tar --exclude=.venv --exclude=.git --exclude=node_modules -cf - .) | (cd "$w" && tar -xf -)
  cd "$w" && git init -q -b main && git -c core.hooksPath=/dev/null add -A \
    && git -c core.hooksPath=/dev/null -c user.email=t@example.com -c user.name=t commit -qm base && git switch -qc feat/x || return 1
  local G="git -c core.hooksPath=/dev/null -c user.email=t@example.com -c user.name=t"
  echo "// x" >> "mobile/app/(app)/settings.tsx" && $G commit -qam screen || return 1
  [ "$(bash scripts/screenshots.sh --changed main --list)" = "/settings" ] || { echo "screen change: $(bash scripts/screenshots.sh --changed main --list)"; return 1; }
  echo "// x" >> mobile/components/ui/Button.tsx && $G commit -qam kit || return 1
  local all; all="$(bash scripts/screenshots.sh --changed main --list | tr '\n' ' ')"
  for r in / /settings /sign-in /gallery; do grep -q -- " $r " <<<" $all" || { echo "component change missed $r: $all"; return 1; }; done
  grep -q '_layout\|+not-found\|(app)' <<<"$all" && { echo "a layout or group leaked: $all"; return 1; }
  git checkout -q main && git switch -qc feat/y && echo "# x" >> backend/main.py && $G commit -qam api || return 1
  bash scripts/screenshots.sh --changed main 2>&1 | grep -q 'nothing to shoot'
}
check "craft: screenshots.sh shoots the changed route, every route on a component change, nothing for a backend-only branch" "_cr_routes"
check "craft: screenshots.sh / .mjs parse, and with no Playwright it exits 3 and says what to do instead" \
  "bash -n '$APP/scripts/screenshots.sh' && node --check '$APP/scripts/screenshots.mjs' && mkdir -p '$T/cr-dist' && echo '<html></html>' > '$T/cr-dist/index.html' \
   && { cd '$T' && npm_config_prefix='$T/no-npm' node '$APP/scripts/screenshots.mjs' '$T/cr-dist' '$T/cr-shots' / > '$T/cr-skip.out' 2>&1; [ \$? -eq 3 ]; } \
   && grep -q \"Playwright isn't installed\" '$T/cr-skip.out'"

# --mobile: a real Expo app, exported for web in demo mode and shot in a real browser.
# Needs Playwright (or playwright-core + a system Chrome). Missing locally, it SKIPS and
# says so; in CI (CI=true) a missing browser is a failure, so kit CI can't skip it.
_cr_png() { [ -s "$1" ] && [ "$(head -c 8 "$1" | od -An -tx1 | tr -d ' \n')" = "89504e470d0a1a0a" ]; }
mobile_check_craft() {
  local out="$T/cr-mshots" dist="$T/cr-web" rc
  rm -rf "$out" "$dist"
  printf 'export default function Boom(): never {\n  throw new Error("planted crash");\n}\n' > app/cr-boom.tsx
  EXPO_PUBLIC_DEMO=1 CI=1 npx expo export --platform web --dev --output-dir "$dist" > "$T/cr-export.log" 2>&1; rc=$?
  rm -f app/cr-boom.tsx
  if [ "$rc" -ne 0 ]; then bad "craft screenshots: expo export --platform web failed"; tail -20 "$T/cr-export.log" | sed 's/^/        | /'; return; fi
  bash ../scripts/screenshots.sh --dist "$dist" --out "$out" / /settings /sign-in > "$T/cr-shots.out" 2>&1; rc=$?
  if [ "$rc" -eq 3 ]; then
    if [ -n "${CI:-}" ]; then bad "craft screenshots: no Playwright/Chrome in CI ($(tail -1 "$T/cr-shots.out"))"
    else skip "craft screenshots: a PNG per route, light and dark, from a real web export" "Playwright + Chromium (npm i -g playwright && npx playwright install chromium)"; fi
    return
  fi
  check "craft screenshots: a real web export gives a PNG per route, light and dark (demo sign-in, client-side routes)" \
    "[ $rc -eq 0 ] && for m in light dark; do for r in index settings sign-in; do _cr_png '$out/'\$m-\$r.png || { echo \"missing \$m-\$r.png\"; cat '$T/cr-shots.out'; exit 1; }; done; done"
  refuses "craft screenshots catch: a route that crashes is reported, not shot" \
    "bash ../scripts/screenshots.sh --dist '$dist' --out '$out-boom' /cr-boom" "/cr-boom: the screen crashed into the error boundary"
}
