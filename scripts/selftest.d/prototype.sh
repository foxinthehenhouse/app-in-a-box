# Prototype renderer: sourced by selftest.sh with $KIT, $APP, $T and the
# check/refuses helpers. Python + (optionally) node only; no browser, no network.
# Every negative control asserts BOTH a non-zero exit AND the specific message, so a
# lint that silently stops firing (or a mutant that fails to write) fails the check.
PROTO_PY="$KIT/scripts/prototype.py"
PROTO_FIX="$KIT/../../scripts/fixtures/prototype.json"   # test-only spec, not an example
PROTO_OUT="$T/proto-out"

cat > "$T/proto_mutate.py" <<'PYEOF'
import json, sys
src, name, out = sys.argv[1:4]
s = json.load(open(src))
home = next(x for x in s["screens"] if x["id"] == "home")
blocks = home["variants"][0]["blocks"]
if name == "dangling":
    blocks[-1]["action"] = {"go": "nowhere"}
elif name == "dangling-sheet":
    blocks[-1]["action"] = {"sheet": "nosheet"}
elif name == "two-primaries":
    blocks.append({"type": "button", "label": "Also primary", "style": "primary"})
elif name == "lorem":
    blocks[0]["subtitle"] = "Lorem ipsum dolor sit amet"
elif name == "todo":
    blocks[0]["title"] = "TODO write the headline"
elif name == "xxx":
    blocks[2]["items"][0]["meta"] = "xxx"
elif name == "no-empty":
    del home["states"]
elif name == "dim-ink":
    s["directions"][1]["tokens"]["color"]["dark"]["inkFaint"] = "#4E525B"
elif name == "six-tabs":
    s["tabs"] += [dict(t, label=t["label"] + " 2") for t in s["tabs"]]
elif name == "unused-feature":
    s["features"].append({"id": "extra", "label": "Extra", "default": False})
elif name == "unreachable":
    s["screens"].append({"id": "orphan", "title": "Orphan", "variants": [
        {"id": "a", "label": "A", "blocks": [{"type": "text", "body": "Nobody links here."}]}]})
elif name == "gated-primary":
    next(x for x in blocks if x.get("style") == "primary")["feature"] = "reminders"
elif name == "bad-icon":
    blocks[2]["items"][0]["icon"] = "rocket"
elif name == "style-inject":
    s["directions"][0]["tokens"]["color"]["light"]["evil"] = "red;}</style><script>alert(1)</script><style>"
elif name == "space-inject":
    s["directions"][0]["tokens"]["space"] = {"xs": "1px;}</style><script>alert(1)</script>"}
elif name == "no-accent":
    del s["directions"][0]["tokens"]["color"]["light"]["accent"]
elif name == "newline-title":
    home["title"] = "Home\n\n## Sheet: injected"
elif name == "script-in-copy":
    blocks[0]["subtitle"] = "Ends </script><!-- here"
elif name == "md-chars":
    home["title"] = "Home ## `x` | *y*"
elif name == "schema":
    blocks[0]["type"] = "carousel"
else:
    sys.exit(f"unknown mutation {name}")
json.dump(s, open(out, "w"))
PYEOF

# _proto_catches <mutation> <expected message>: check must exit 1 AND name the problem.
_proto_catches() {
  local out rc
  python3 "$T/proto_mutate.py" "$PROTO_FIX" "$1" "$T/pm-$1.json" || return 1
  out=$(python3 "$PROTO_PY" check "$T/pm-$1.json"); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q -- "$2"
}

# No <script src>, and every src/href/url()/@import that leaves the file is Google Fonts.
_proto_self_contained() {
  python3 - "$PROTO_OUT/prototype.html" <<'PYEOF'
import re, sys
page = open(sys.argv[1]).read()
assert not re.search(r"<script[^>]*\bsrc\s*=", page, re.I), "external <script src>"
refs = re.findall(r"""(?:src|href)\s*=\s*["']?((?:https?:)?//[^"'\s>]+)""", page, re.I)
refs += re.findall(r"""(?:url\(|@import\s+)["']?((?:https?:)?//[^"')\s]+)""", page, re.I)
bad = [r for r in refs if not re.match(r"(?:https?:)?//fonts\.(googleapis|gstatic)\.com(/|$)", r)]
assert not bad, f"external refs: {bad}"
PYEOF
}

# Both embedded JSON blocks parse, and the spec round-trips unchanged.
_proto_json_valid() {
  python3 - "$PROTO_OUT/prototype.html" "$PROTO_FIX" <<'PYEOF'
import json, re, sys
page = open(sys.argv[1]).read()
blocks = dict(re.findall(r'<script type="application/json" id="(proto-\w+)">(.*?)</script>', page, re.S))
assert set(blocks) == {"proto-spec", "proto-config"}, blocks.keys()
assert json.loads(blocks["proto-spec"]) == json.load(open(sys.argv[2]))
cfg = json.loads(blocks["proto-config"])
assert {"icons", "palettes", "components"} <= set(cfg)
PYEOF
}

_proto_js_parses() {
  # node is required: a check that passes where it can't run guards nothing. Without
  # node the caller records a visible SKIP (see below), never a PASS.
  command -v node >/dev/null 2>&1 || { echo "node missing"; return 1; }
  python3 -c "import re,sys; p=open(sys.argv[1]).read(); open(sys.argv[2],'w').write(re.findall(r'<script>(.*?)</script>', p, re.S)[-1])" \
    "$PROTO_OUT/prototype.html" "$T/proto-inline.js" && node --check "$T/proto-inline.js"
}

rm -rf "$PROTO_OUT" && mkdir -p "$PROTO_OUT"
check "prototype: fixture spec passes check" "python3 '$PROTO_PY' check '$PROTO_FIX'"
check "prototype: render writes exactly one HTML file" \
  "python3 '$PROTO_PY' render '$PROTO_FIX' '$PROTO_OUT/prototype.html' && [ \"\$(ls '$PROTO_OUT' | wc -l)\" -eq 1 ]"
check "prototype: html has phone, control panel, variant switcher, feature toggles, choices button" \
  "grep -q 'id=\"phone\"' '$PROTO_OUT/prototype.html' && grep -q 'id=\"panel\"' '$PROTO_OUT/prototype.html' \
   && grep -q 'api.setVariant' '$PROTO_OUT/prototype.html' && grep -q 'role: \"switch\"' '$PROTO_OUT/prototype.html' \
   && grep -q 'api.setFeature' '$PROTO_OUT/prototype.html' && grep -q 'text: \"Copy my choices\"' '$PROTO_OUT/prototype.html'"
check "prototype: phone honours prefers-reduced-motion (CSS stops animation, JS skips waits)" \
  "grep -A1 '@media (prefers-reduced-motion: reduce)' '$PROTO_OUT/prototype.html' | grep -q '^  \\.phone \\*, .*animation: none !important' \
   && grep -q 'matchMedia(\"(prefers-reduced-motion: reduce)\")' '$PROTO_OUT/prototype.html'"
check "prototype: no external script/src other than Google Fonts" "_proto_self_contained"
check "prototype: embedded spec + config JSON are valid (spec round-trips)" "_proto_json_valid"
if command -v node >/dev/null 2>&1; then
  check "prototype: inline JS parses (node --check)" "_proto_js_parses"
else
  skip "prototype: inline JS parses (node --check)" "node"
fi
_proto_palettes() {  # one CSS palette block per direction x mode, carrying that palette's bg
  python3 - "$PROTO_OUT/prototype.html" "$PROTO_FIX" <<'PYEOF'
import json, sys
page, spec = open(sys.argv[1]).read(), json.load(open(sys.argv[2]))
for d in spec["directions"]:
    for m in ("light", "dark"):
        want = '.phone[data-direction="%s"][data-mode="%s"] { --bg: %s;' % (d["id"], m, d["tokens"]["color"][m]["bg"])
        assert want in page, want
PYEOF
}
check "prototype: per-direction x mode palettes emitted as CSS variables" "_proto_palettes"
_proto_render_refuses() {
  python3 "$T/proto_mutate.py" "$PROTO_FIX" schema "$T/pm-render.json" || return 1
  rm -f "$T/never.html"
  ! python3 "$PROTO_PY" render "$T/pm-render.json" "$T/never.html" >/dev/null && [ ! -e "$T/never.html" ]
}
check "prototype: render refuses a malformed spec (writes nothing)" "_proto_render_refuses"

check "prototype check catches: unknown block type (schema)" "_proto_catches schema 'unknown block type'"
check "prototype check catches: dangling go target" "_proto_catches dangling \"dangling go target 'nowhere'\""
check "prototype check catches: dangling sheet target" "_proto_catches dangling-sheet \"dangling sheet target 'nosheet'\""
check "prototype check catches: 2 primary buttons in one variant" "_proto_catches two-primaries '2 primary buttons'"
check "prototype check catches: lorem ipsum" "_proto_catches lorem \"placeholder text 'Lorem'\""
check "prototype check catches: TODO" "_proto_catches todo \"placeholder text 'TODO'\""
check "prototype check catches: xxx" "_proto_catches xxx \"placeholder text 'xxx'\""
check "prototype check catches: list without an empty state" "_proto_catches no-empty 'has a list but no states.empty'"
check "prototype check catches: a direction with a dim inkFaint (contrast)" "_proto_catches dim-ink 'directions\\[athletic\\]: contrast: \\[dark\\] inkFaint'"
check "prototype check catches: 6 tabs" "_proto_catches six-tabs 'tabs: 6 tabs'"
check "prototype check catches: feature no block references" "_proto_catches unused-feature 'features\\[extra\\]: defined but no block'"
check "prototype check catches: unreachable screen" "_proto_catches unreachable 'screens\\[orphan\\]: unreachable'"

# freeze: the JSON "Copy my choices" emits -> tokens.json, SCREENS.md, choices.json
FRZ="$T/proto-frozen"
cat > "$T/proto-choices.json" <<'EOF'
{"direction": "athletic", "mode": "dark", "density": "compact", "temperature": "lively",
 "tone": "playful", "variants": {"home": "cards"}, "features": {"reminders": true, "insights": false}}
EOF
rm -rf "$FRZ"
check "prototype: freeze writes tokens.json, SCREENS.md, choices.json" \
  "python3 '$PROTO_PY' freeze '$PROTO_FIX' '$T/proto-choices.json' --target '$FRZ' \
   && [ -f '$FRZ/design/tokens.json' ] && [ -f '$FRZ/docs/product/SCREENS.md' ] && [ -f '$FRZ/design/choices.json' ]"
check "prototype: frozen tokens pass check_contrast.py" "python3 '$KIT/scripts/check_contrast.py' '$FRZ/design/tokens.json'"
check "prototype: frozen tokens apply density + temperature (compact space, lively motion)" \
  "python3 -c \"import json;d=json.load(open('$FRZ/design/tokens.json'));assert d['name']=='athletic' and d['mode']=='dark' and d['space']['md']==12 and d['motion']['duration']['fast']==102 and d['motion']['pressScale']<0.96 and d['motion']['easing']['enter'][1]>1\""
check "prototype: SCREENS.md names each screen's chosen variant" \
  "grep -q 'Layout: \\*\\*Cards\\*\\* (\`cards\`)' '$FRZ/docs/product/SCREENS.md' \
   && [ \"\$(grep -c '^Layout: \\*\\*' '$FRZ/docs/product/SCREENS.md')\" -eq 4 ] && [ \"\$(grep -c '^## Screen: ' '$FRZ/docs/product/SCREENS.md')\" -eq 4 ]"
check "prototype: SCREENS.md lists features in and out of v1, and cuts off-feature blocks" \
  "grep -q '| Reminders (\`reminders\`) | in |' '$FRZ/docs/product/SCREENS.md' \
   && grep -q '| Insights (\`insights\`) | \\*\\*out\\*\\* |' '$FRZ/docs/product/SCREENS.md' \
   && grep -q '\\*\\*cut\\*\\* (\`insights\` off)' '$FRZ/docs/product/SCREENS.md' && grep -q '^## Navigation' '$FRZ/docs/product/SCREENS.md'"
check "prototype: choices.json records every screen and feature" \
  "python3 -c \"import json;c=json.load(open('$FRZ/design/choices.json'));assert c['variants']=={'home':'cards','detail':'default','insights':'default','settings':'default'} and c['features']=={'reminders':True,'insights':False} and c['tone']=='playful'\""

_proto_freeze_refuses() {  # <choices json> <expected message>
  local out rc
  printf '%s' "$1" > "$T/proto-bad-choices.json"
  rm -rf "$T/proto-frz-bad"
  out=$(python3 "$PROTO_PY" freeze "$PROTO_FIX" "$T/proto-bad-choices.json" --target "$T/proto-frz-bad"); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q -- "$2" && [ ! -e "$T/proto-frz-bad/design/tokens.json" ]
}
check "prototype: freeze refuses a variant id that doesn't exist (writes nothing)" \
  "_proto_freeze_refuses '{\"variants\": {\"home\": \"grid\"}}' \"choices.variants.home: no variant 'grid'\""
check "prototype: freeze refuses an unknown feature and direction" \
  "_proto_freeze_refuses '{\"direction\": \"neon\", \"features\": {\"chat\": true}}' 'choices.direction' \
   && _proto_freeze_refuses '{\"features\": {\"chat\": true}}' 'choices.features.chat: no such feature'"

# From the Lendlog end-to-end dry run: gaps a real spec hit that the fixture didn't.
check "prototype check catches: the only primary button behind a feature toggle" \
  "_proto_catches gated-primary \"primary button is behind feature 'reminders'\""
check "prototype check catches: an unknown list icon, and lists the valid names" \
  "_proto_catches bad-icon \"'rocket' is not in the icon set (arrow, bell\""

# Every icon maps to native iOS/Android symbols, and the skill lists every name, so an
# agent can't pick an icon the scaffold can't build.
_proto_icons() {
  python3 - "$KIT/scripts/proto/icons.json" "$KIT/skills/prototype/SKILL.md" <<'PYEOF'
import json, re, sys
d = json.load(open(sys.argv[1])); skill = open(sys.argv[2]).read()
assert len(d["icons"]) >= 40, len(d["icons"])
assert set(d["icons"]) == set(d["native"]), set(d["icons"]) ^ set(d["native"])
for n, pair in d["native"].items():
    assert len(pair) == 2 and all(re.fullmatch(r"[a-z0-9._]+", x) for x in pair), n
    assert re.search(rf"\b{re.escape(n)}\b", skill.split("Icons (")[1].split("\n\n")[0]), f"skill lacks {n}"
PYEOF
}
check "prototype: every icon has SF + Material names, and the skill lists them all" "_proto_icons"
check "prototype: SCREENS.md lists the frozen icons with their sf/md names" \
  "grep -qx '## Icons' '$FRZ/docs/product/SCREENS.md' && grep -qF '| home | \`house\` | \`home\` |' '$FRZ/docs/product/SCREENS.md'"

# A named font that is never loaded silently falls back to the system font, so the app
# stops matching the prototype. The template loads lib/fonts.ts and a test guards it.
_fonts_wired() {
  local m="$KIT/template/mobile"
  grep -q 'export const fontAssets' "$m/lib/fonts.ts" \
    && grep -q 'useFonts(fontAssets)' "$m/app/_layout.tsx" \
    && grep -q 'fontError !== null' "$m/app/_layout.tsx" \
    && grep -q '_${spec.weight}` in fontAssets' "$m/lib/__tests__/fonts.test.ts" \
    && grep -q 'fontFace(name, weight)' "$m/lib/theme.ts" \
    && grep -q 'lib/fonts.ts' "$KIT/skills/scaffold/SKILL.md" \
    && grep -q 'expo-font expo-asset' "$KIT/scripts/mobile-deps.sh" \
    && grep -qx 'npm pkg set jest.testTimeout=30000 --json.*' "$KIT/scripts/mobile-deps.sh"
}
check "template loads the tokens' custom fonts (and a test fails when one isn't registered)" "_fonts_wired"


# From the prototype review: spec text must never become page markup or spec structure.
_proto_render_refuses_mut() {  # <mutation> <expected message>: check AND render refuse, nothing written
  local out rc
  _proto_catches "$1" "$2" || return 1
  rm -f "$T/pm-$1.html"
  out=$(python3 "$PROTO_PY" render "$T/pm-$1.json" "$T/pm-$1.html" 2>&1); rc=$?
  [ "$rc" -eq 1 ] && [ ! -e "$T/pm-$1.html" ] && ! printf '%s' "$out" | grep -q Traceback
}
check "prototype refuses a token colour that could close <style> (no script injection)" \
  "_proto_render_refuses_mut style-inject 'color.light.evil: must be #RRGGBB'"
check "prototype refuses a non-numeric token value (space, type, motion...)" \
  "_proto_render_refuses_mut space-inject 'space.xs: must be a number'"
check "prototype refuses a palette missing a required colour, without a traceback" \
  "_proto_render_refuses_mut no-accent 'color.light.accent: required'"
check "prototype refuses a multi-line string (it would forge SCREENS.md headings)" \
  "_proto_catches newline-title 'spec.screens\\[0\\].title: must be one line'"
_proto_script_escaped() {
  python3 "$T/proto_mutate.py" "$PROTO_FIX" script-in-copy "$T/pm-sc.json" \
    && python3 "$PROTO_PY" render "$T/pm-sc.json" "$T/pm-sc.html" >/dev/null || return 1
  python3 - "$T/pm-sc.html" <<'PYEOF'
import re, sys
page = open(sys.argv[1]).read()
assert "Ends <\\/script><\\!-- here" in page, "copy not escaped inside the JSON script"
assert len(re.findall(r"<script\b", page)) == len(re.findall(r"</script>", page)), "a </script> leaked"
PYEOF
}
check "prototype escapes </script> and <!-- in spec copy" "_proto_script_escaped"
_proto_md_inert() {
  python3 "$T/proto_mutate.py" "$PROTO_FIX" md-chars "$T/pm-md.json" \
    && python3 "$PROTO_PY" freeze "$T/pm-md.json" "$T/proto-choices.json" --target "$T/pm-md" >/dev/null || return 1
  grep -qF '## Screen: Home \#\# \`x\` \| \*y\* (`home`)' "$T/pm-md/docs/product/SCREENS.md"
}
check "SCREENS.md escapes Markdown in spec text (headings, code, tables)" "_proto_md_inert"
_proto_freeze_target_file() {
  local out rc; : > "$T/not-a-dir"
  out=$(python3 "$PROTO_PY" freeze "$PROTO_FIX" "$T/proto-choices.json" --target "$T/not-a-dir" 2>&1); rc=$?
  [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q '^freeze: cannot write under' && ! printf '%s' "$out" | grep -q Traceback
}
check "freeze onto a file fails cleanly (no traceback, nothing half-written)" "_proto_freeze_target_file"
_proto_font_sets_agree() {
  python3 - "$PROTO_PY" "$KIT/template/mobile/lib/fonts.ts" <<'PYEOF'
import re, sys, importlib.util
spec = importlib.util.spec_from_file_location("proto", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ts = re.search(r"BUILT_IN_FONTS = new Set\(\[(.*?)\]\)", open(sys.argv[2]).read()).group(1)
assert set(re.findall(r'"([^"]+)"', ts)) == m.SYSTEM_FONTS | m.MONO_FONTS
PYEOF
}
check "prototype and the app agree on which fonts are built in" "_proto_font_sets_agree"
_proto_rev() {
  python3 - "$PROTO_PY" "$PROTO_FIX" <<'PYEOF'
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("proto", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
s = json.load(open(sys.argv[2])); a = m._rev(s)
s["defaults"]["direction"] = s["directions"][1]["id"]; assert m._rev(s) != a, "defaults change"
s["features"][0]["default"] = not s["features"][0]["default"]; assert len({a, m._rev(s)}) == 2
PYEOF
  grep -q 'saved.rev !== REV' "$KIT/scripts/proto/runtime.js" && grep -q '"rev"' "$PROTO_OUT/prototype.html"
}
check "saved prototype clicks are dropped when the team changes defaults or features" "_proto_rev"
check "skills: freeze reads choices.in.json; shape writes validate: pending; scaffold handles no SCREENS.md" \
  "grep -q 'freeze design/prototype.json design/choices.in.json' '$KIT/skills/prototype/SKILL.md' \
   && grep -q 'progress.validate: pending' '$KIT/skills/shape/SKILL.md' \
   && grep -q 'No SCREENS.md' '$KIT/skills/scaffold/SKILL.md'"

# The prototype -> native map: every component SCREENS.md names is a real export of the
# template's components/ui, and each frozen SCREENS.md says how chrome and motion go native.
_proto_components_real() {
  python3 - "$PROTO_PY" "$KIT/template/mobile/components/ui/index.ts" "$FRZ/docs/product/SCREENS.md" <<'PYEOF'
import re, sys, importlib.util
spec = importlib.util.spec_from_file_location("proto", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
exports = set(re.findall(r"\b([A-Za-z]\w*)\b", " ".join(re.findall(r"export \{([^}]*)\}", open(sys.argv[2]).read()))))
named = set()
for v in m.COMPONENTS.values():
    named |= set(re.findall(r"[A-Za-z]\w*", v))
screens = open(sys.argv[3]).read()
named |= set(re.findall(r"<([A-Z]\w*)", screens)) - {"NativeTabs"}
missing = sorted(n for n in named if n not in exports)
assert not missing, f"not exported from components/ui: {missing}"
assert "`<StatCard" in screens and "<Button variant=" in screens, "SCREENS.md lacks code-level calls"
PYEOF
}
check "every component the prototype maps to is a real components/ui export" "_proto_components_real"
check "SCREENS.md says how tabs, sheets and motion go native (with the frozen values)" \
  "grep -qx '## Platform (what the prototype imitates, built natively)' '$FRZ/docs/product/SCREENS.md' \
   && grep -qx '## Motion (frozen from the prototype.s feel)' '$FRZ/docs/product/SCREENS.md' \
   && grep -q 'NativeTabs' '$FRZ/docs/product/SCREENS.md' && grep -q 'entrance(i)' '$FRZ/docs/product/SCREENS.md'"
_proto_lively_springs() {
  python3 - "$PROTO_PY" "$PROTO_FIX" <<'PYEOF'
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("proto", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
s = json.load(open(sys.argv[2]))
base = dict(s["defaults"], variants={}, features={})
def damping(temp):
    ch, errs = m.resolve_choices(s, dict(base, temperature=temp)); assert not errs, errs
    return m.frozen_tokens(s, ch)["motion"]["spring"]["snappy"]["damping"]
assert damping("lively") < damping("calm"), "lively springs must overshoot more than calm"
PYEOF
}
check "the prototype's temperature reaches the springs (lively overshoots, calm settles)" "_proto_lively_springs"
check "native UI wired: @expo/ui segmented control + expo-image installed, no radio role" \
  "grep -q '@expo/ui expo-image' '$KIT/scripts/mobile-deps.sh' \
   && grep -q '@expo/ui/community/segmented-control' '$KIT/template/mobile/components/ui/Choice.tsx' \
   && grep -q 'from \"expo-image\"' '$KIT/template/mobile/components/ui/Media.tsx' \
   && ! grep -rq 'accessibilityRole=\"radio' '$KIT/template/mobile/components' '$KIT/template/mobile/app'"

