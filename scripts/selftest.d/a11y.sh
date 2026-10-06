# Accessibility, enforced: the generated app's a11y is a set of checks, not only a review.
# Sourced by selftest.sh with $KIT, $APP, $T and the check/refuses/skip helpers.
#   check-a11y.js          the app's code (gates): each rule passes on the pristine app and
#                          FAILS on a planted violation, naming the rule
#   a11y-screens.test.tsx  every route at font scale 1 and 2 (--mobile: a real Expo app),
#                          and a planted unlabelled Pressable fails it
#   a11y_labels.py         docs/product/ACCESSIBILITY.md, the App Store answers: derived
#                          from that evidence, never claimed without it, drift fails
# Plants go into copies under $T, never into $APP.
A11Y_JS="$KIT/template/mobile/scripts/check-a11y.js"

if command -v node >/dev/null 2>&1; then
  check "a11y code: check-a11y.js passes on the template and its self-tests pass" \
    "cd '$KIT/template/mobile' && node scripts/check-a11y.js && node --test scripts/__tests__/check-a11y.test.js"
  check "a11y code: check-a11y.js passes on the rendered app" "cd '$APP/mobile' && node scripts/check-a11y.js"
  _a11y_plant() {  # <file under mobile/> <code to append> <expected message>: a rendered-app copy must fail on it
    local c="$T/a11y-plant"; rm -rf "$c"; mkdir -p "$c"
    (cd "$APP/mobile" && tar --exclude=node_modules -cf - app components lib locales scripts) | (cd "$c" && tar -xf -) || return 1
    mkdir -p "$c/$(dirname "$1")" && printf '%s\n' "$2" >> "$c/$1"
    local out; out=$(cd "$c" && node scripts/check-a11y.js 2>&1) && { echo "still green"; return 1; }
    printf '%s' "$out" | grep -q -- "$3" || { printf '%s\n' "$out"; return 1; }
  }
  check "a11y code catches: an icon-only Pressable with no label" \
    "_a11y_plant 'app/(app)/index.tsx' 'export const Add = () => <Pressable onPress={add} accessibilityRole=\"button\"><Icon sf=\"plus\" md=\"add\" /></Pressable>;' 'index.tsx:[0-9]*: unlabelled-control: <Pressable>'"
  check "a11y code catches: a TouchableOpacity with no role" \
    "_a11y_plant 'app/(app)/settings.tsx' 'export const Row = () => <TouchableOpacity onPress={open} accessibilityLabel=\"Open profile\" />;' 'settings.tsx:[0-9]*: no-role: <TouchableOpacity>'"
  check "a11y code catches: a TextInput with only a placeholder" \
    "_a11y_plant 'app/edit-name.tsx' 'export const Note = () => <TextInput placeholder=\"Note\" onChangeText={setNote} />;' 'unlabelled-control: <TextInput>'"
  check "a11y code catches: an <Image> with no label and no accessible={false}" \
    "_a11y_plant 'components/ui/Cover.tsx' \$'import { Image } from \"expo-image\";\nexport const Cover = () => <Image source={{ uri }} contentFit=\"cover\" />;' 'Cover.tsx:2: unlabelled-image'"
  check "a11y code catches: a label that restates its role" \
    "_a11y_plant 'app/(app)/index.tsx' 'export const B = () => <IconButton sf=\"gear\" md=\"settings\" accessibilityLabel=\"Settings button\" onPress={go} />;' 'label-restates-role: \"Settings button\"'"
  check "a11y code catches: allowFontScaling={false}" \
    "_a11y_plant 'app/(app)/index.tsx' 'export const N = () => <RNText allowFontScaling={false}>{n}</RNText>;' 'no-font-scaling'"
  check "a11y code catches: maxFontSizeMultiplier under 1.3 outside the ui kit" \
    "_a11y_plant 'app/(app)/index.tsx' 'export const T = () => <Text variant=\"title\" maxFontSizeMultiplier={1.1}>{t(\"x\")}</Text>;' 'low-font-cap: maxFontSizeMultiplier 1.1'"
  check "a11y code catches: a hand-rolled withTiming that ignores Reduce Motion" \
    "_a11y_plant 'lib/drawer.ts' 'export const open = (x: SV) => x.set(withTiming(1, { duration: 300 }));' 'lib/drawer.ts:[0-9]*: motion-ignores-os: withTiming'"
  check "a11y code catches: an RN Animated.spring in a file that never checks Reduce Motion" \
    "_a11y_plant 'components/ui/Pulse.tsx' 'Animated.spring(v, { toValue: 1, useNativeDriver: true }).start();' 'motion-ignores-os: Animated.spring'"
  check "a11y code: a reasoned a11y-ignore waives a line; a bare one does not" \
    "c='$T/a11y-ign'; rm -rf \"\$c\"; mkdir -p \"\$c/app\" \"\$c/scripts\" && cp '$A11Y_JS' \"\$c/scripts/\" \
     && printf '<Pressable onPress={go} /> // a11y-ignore: the parent row carries the label\n' > \"\$c/app/x.tsx\" && (cd \"\$c\" && node scripts/check-a11y.js) \
     && printf '<Pressable onPress={go} /> // a11y-ignore:\n' > \"\$c/app/x.tsx\" && ! (cd \"\$c\" && node scripts/check-a11y.js)"
else
  skip "a11y code: check-a11y.js on the template and planted violations" "node"
fi
check "a11y code: check-a11y.js is in the app's npm run gates" \
  "grep -q 'node scripts/check-design-tells.js && node scripts/check-a11y.js' '$KIT/scripts/mobile-deps.sh'"
check "a11y screens: the test renders every route on disk at font scale 1 and 2, and checks roles, names and hiding" \
  "f='$APP/mobile/__tests__/a11y-screens.test.tsx'; grep -q 'describe.each(\[1, 2\])' \"\$f\" && grep -q 'routeFiles(APP_DIR)' \"\$f\" \
   && grep -q 'Dimensions.set' \"\$f\" && grep -q 'hidden from the accessibility tree' \"\$f\" && grep -q 'no accessibilityRole' \"\$f\""

# Accessibility Nutrition Labels.
A11Y_PY="scripts/a11y_labels.py"
check "a11y labels: the pristine render's docs/product/ACCESSIBILITY.md matches its evidence" "cd '$APP' && python3 $A11Y_PY --check"
check "a11y labels: one line per Apple feature; Captions and Audio Descriptions say not applicable without video" \
  "f='$APP/docs/product/ACCESSIBILITY.md'; for x in VoiceOver 'Voice Control' 'Larger Text' 'Sufficient Contrast' 'Reduced Motion' 'Dark Interface' 'Differentiate Without Color Alone' Captions 'Audio Descriptions'; do grep -q \"^- \*\*\$x\*\*: \" \"\$f\" || exit 1; done \
   && grep -q '^- \*\*Captions\*\*: not applicable unless the app has video' \"\$f\" && grep -q '^- \*\*Audio Descriptions\*\*: not applicable unless the app has video' \"\$f\""
check "a11y labels: the pristine render claims no VoiceOver (no SCREENS.md, so no common tasks proven)" \
  "grep -q '^- \*\*VoiceOver\*\*: not yet claimed (missing: docs/product/SCREENS.md' '$APP/docs/product/ACCESSIBILITY.md'"
_a11y_copy() {  # <dir>: what a11y_labels.py reads, copied from the rendered app
  rm -rf "$1" && mkdir -p "$1" && (cd "$APP" && tar --exclude=node_modules -cf - scripts design docs mobile/app mobile/components mobile/lib mobile/locales mobile/scripts mobile/__tests__ mobile/.maestro) | (cd "$1" && tar -xf -)
}
# _a11y_label <shell edit run in the copy's root> <expected line after regenerating>: the
# check must fail on the old file, and the regenerated file must say the new answer.
_a11y_label() {
  local d="$T/a11y-labels"; _a11y_copy "$d" || return 1
  (cd "$d" && eval "$1") || return 1
  (cd "$d" && python3 $A11Y_PY --check >/dev/null 2>&1) && { echo "--check still green"; return 1; }
  (cd "$d" && python3 $A11Y_PY >/dev/null) && grep -q -- "$2" "$d/docs/product/ACCESSIBILITY.md" || { cat "$d/docs/product/ACCESSIBILITY.md"; return 1; }
}
refuses "a11y labels catch: a feature hand-claimed in ACCESSIBILITY.md" \
  "d='$T/a11y-hand'; _a11y_copy \"\$d\" && sed -i 's/^- \*\*Differentiate Without Color Alone\*\*: not yet claimed.*/- **Differentiate Without Color Alone**: supported/' \"\$d/docs/product/ACCESSIBILITY.md\" && cd \"\$d\" && python3 $A11Y_PY --check" \
  "the answers differ from what the evidence says now"
check "a11y labels: Reduced Motion is unclaimed once lib/motion.ts stops honouring it" \
  "_a11y_label \"sed -i 's/useReducedMotion/useMotionPref/g' mobile/lib/motion.ts\" '^- \*\*Reduced Motion\*\*: not yet claimed (missing: mobile/lib/motion.ts to honour Reduce Motion'"
check "a11y labels: Sufficient Contrast is unclaimed once a text ink drops below AA" \
  "_a11y_label \"python3 -c \\\"import json;d=json.load(open('design/tokens.json'));d['color']['dark']['inkFaint']='#4E525B';json.dump(d,open('design/tokens.json','w'))\\\"\" '^- \*\*Sufficient Contrast\*\*: not yet claimed'"
check "a11y labels: Dark Interface is unclaimed without a dark palette" \
  "_a11y_label \"python3 -c \\\"import json;d=json.load(open('design/tokens.json'));d['color']=d['color']['light'];d['mode']='light';json.dump(d,open('design/tokens.json','w'))\\\"\" '^- \*\*Dark Interface\*\*: not yet claimed'"
check "a11y labels: Larger Text is unclaimed once body text is capped under 200%" \
  "_a11y_label \"sed -i 's/\\\"maxScale\\\": 2.0/\\\"maxScale\\\": 1.5/' design/tokens.json\" '^- \*\*Larger Text\*\*: not yet claimed (missing: body text that scales to 200%'"
check "a11y labels: VoiceOver is unclaimed while a lint finding stands" \
  "_a11y_label \"printf 'export const X = () => <Pressable onPress={go} />;\n' > mobile/app/planted.tsx\" '^- \*\*VoiceOver\*\*: not yet claimed (missing: mobile/scripts/check-a11y.js to pass'"
check "a11y labels: SCREENS.md tasks with flows are claimed; one without a flow unclaims VoiceOver" \
  "d='$T/a11y-tasks'; _a11y_copy \"\$d\" && printf '## Screen: Home (\`home\`)\n\n## Sheet: Edit name (\`edit_name\`)\n' > \"\$d/docs/product/SCREENS.md\" \
   && (cd \"\$d\" && python3 $A11Y_PY >/dev/null) && grep -q '^- \*\*VoiceOver\*\*: supported (evidence: ' \"\$d/docs/product/ACCESSIBILITY.md\" \
   && printf '\n## Screen: Streaks (\`streaks\`)\n' >> \"\$d/docs/product/SCREENS.md\" && ! (cd \"\$d\" && python3 $A11Y_PY --check >/dev/null) \
   && (cd \"\$d\" && python3 $A11Y_PY >/dev/null) && grep -q '^- \*\*VoiceOver\*\*: not yet claimed (missing: a Maestro flow for streaks-screen)' \"\$d/docs/product/ACCESSIBILITY.md\""
check "a11y labels: an app with video gets Captions as not yet claimed, never supported" \
  "_a11y_label \"printf 'import { VideoView } from \\\"expo-video\\\";\n' > mobile/components/Clip.tsx\" '^- \*\*Captions\*\*: not yet claimed'"
check "a11y labels: notes outside the markers survive a rewrite" \
  "d='$T/a11y-notes'; _a11y_copy \"\$d\" && echo 'Checked by hand on an iPhone.' >> \"\$d/docs/product/ACCESSIBILITY.md\" && (cd \"\$d\" && python3 $A11Y_PY >/dev/null && python3 $A11Y_PY --check >/dev/null) && grep -q 'Checked by hand on an iPhone.' \"\$d/docs/product/ACCESSIBILITY.md\""

# Wiring and instructions.
check "a11y wiring: CI's mobile job runs the labels --check after the gates; pre-commit runs it" \
  "python3 -c \"import yaml,sys; s=yaml.safe_load(open('$APP/.github/workflows/ci.yml'))['jobs']['mobile']['steps']; r=[str(x.get('run','')) for x in s]; g=[i for i,x in enumerate(r) if 'npm run gates' in x]; l=[i for i,x in enumerate(r) if 'a11y_labels.py --check' in x]; sys.exit(0 if g and l and l[0]>g[0] else 1)\" \
   && grep -q 'python3 scripts/a11y_labels.py --check' '$APP/.githooks/pre-commit'"
check "a11y wiring: the wiring test notices the labels check going unwired" \
  "cd '$APP' && ./.venv/bin/python -m pytest -q tests/harness/test_guards_wired.py -k 'a11y' tests/test_a11y_labels.py"
check "a11y docs: ship lists the label answers and never claims beyond them; build-feature requires the checks" \
  "grep -q 'docs/product/ACCESSIBILITY.md' '$APP/.agents/skills/ship/SKILL.md' && grep -q 'Never claim a' '$APP/.agents/skills/ship/SKILL.md' \
   && grep -q 'mobile/scripts/check-a11y.js' '$APP/.agents/skills/build-feature/SKILL.md' && grep -q 'a11y-screens.test.tsx' '$APP/.agents/skills/build-feature/SKILL.md'"
check "a11y docs: the mobile-a11y rule names the lint and the escape hatch; AGENTS.md points at it within 150 lines" \
  "grep -q 'mobile/scripts/check-a11y.js' '$APP/.agents/rules/mobile-a11y.md' && grep -q 'a11y-ignore: <why>' '$APP/.agents/rules/mobile-a11y.md' \
   && grep -q 'check-a11y.js' '$APP/AGENTS.md' && [ \$(wc -l < '$APP/AGENTS.md') -le 150 ]"

# With --mobile: the rendered-screen test in a real Expo app passes, and fails on a planted
# unlabelled Pressable with its own message (not a crash).
mobile_check_a11y() {
  check "a11y screens: every route passes at font scale 1 and 2 (real Expo app)" \
    "npx jest --ci __tests__/a11y-screens.test.tsx"
  local f="app/(app)/settings.tsx"
  cp "$f" "$T/a11y-settings.bak"
  python3 - "$f" <<'PYEOF'
import sys
p = sys.argv[1]; s = open(p).read()
s = s.replace("import { Button,", 'import { Pressable } from "react-native";\nimport { Button,', 1)
i = s.index('testID="settings-screen"'); j = s.index(">", i) + 1
s = s[:j] + '\n      <Pressable onPress={() => undefined} testID="planted-press" />' + s[j:]
open(p, "w").write(s)
PYEOF
  refuses "a11y screens catch: a planted unlabelled Pressable on a screen" \
    "npx jest --ci __tests__/a11y-screens.test.tsx" 'is pressable with no accessibilityLabel or text'
  cp "$T/a11y-settings.bak" "$f"
}
