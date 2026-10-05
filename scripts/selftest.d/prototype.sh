# Prototype renderer: sourced by selftest.sh with $KIT, $APP, $T and the
# check/refuses helpers. Python + (optionally) node only; no browser, no network.
# Every negative control asserts BOTH a non-zero exit AND the specific message, so a
# lint that silently stops firing (or a mutant that fails to write) fails the check.
PROTO_PY="$KIT/scripts/prototype.py"
PROTO_FIX="$KIT/../../scripts/fixtures/prototype.json"   # test-only spec, not an example
PROTO_OUT="$T/proto-out"
# Renders are offline and deterministic: fonts come only from this (empty) cache, so
# each family falls back to a Google Fonts <link>. The inlining path has its own check.
export APPBOX_OFFLINE=1 APPBOX_FONT_CACHE="$T/proto-fonts-empty"

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
elif name == "bad-atmo":
    s["directions"][0]["tokens"]["atmosphere"] = {"mode": "neon", "grain": "yes"}
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
_proto_reduced_motion() {  # every motion has a reduced path: CSS, JS waits, each effect, the field
  python3 - "$PROTO_OUT/prototype.html" <<'PYEOF'
import re, sys
page = open(sys.argv[1]).read()
assert re.search(r"\.phone\.rm \*, \.phone\.rm \*::before, \.phone\.rm \*::after \{ animation: none !important;", page), "no .rm kill rule"
assert re.search(r"\.phone\.rm \.screen\.in-fade[^{]*\{ animation: rm-in", page), "screens don't crossfade under .rm"
assert re.search(r"@media \(prefers-reduced-motion: reduce\) \{\s*\.atmo::before \{ animation: none", page), "atmosphere drifts under reduce"
assert 'matchMedia("(prefers-reduced-motion: reduce)")' in page
assert 'phone.classList.toggle("rm", !!isReduced())' in page, "the OS setting never reaches .rm"
assert "function wait(ms) { return isReduced() ? 0 : ms; }" in page
fx = page[page.index("Proto.fx = (function"):page.index("Proto.panel = (function")]
for fn in ("function bloom(e)", "function commit(btn)", "function countUp(root)"):
    body = fx[fx.index(fn):][:200]
    assert "if (isReduced()" in body, f"{fn} ignores reduced motion"
assert "var still = isReduced() || document.hidden;" in fx, "the field animates under reduced motion"
PYEOF
}
check "prototype: every motion has a reduced-motion path (CSS crossfades, JS waits, each effect, the field)" "_proto_reduced_motion"
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
  "python3 -c \"import json;d=json.load(open('$FRZ/design/tokens.json'));assert d['name']=='athletic' and d['mode']=='dark' and d['space']['md']==12 and d['motion']['duration']['fast']==102 and d['motion']['pressScale']<0.96 and d['motion']['easing']['enter']==[0.16,1,0.3,1]\""
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


# ---- High-end by default: atmosphere, springs, fonts, size (docs/specs/high-end-design) ----

# The lit ground is a colour no token file holds, so it gets its own contrast check:
# re-derive the field from the RENDERED page (the light geometry in .atmo::before, its
# drift, and each direction x mode x intensity's light colours + alpha), composite it
# over the palette, and require every ink at AA on the lit ground and on glass over it.
cat > "$T/proto_atmo_guard.py" <<'PYEOF'
import json, re, sys
sys.path.insert(0, sys.argv[3])
import check_contrast as cc
page, spec = open(sys.argv[1]).read(), json.load(open(sys.argv[2]))
geo = re.search(r"\.atmo::before \{ background: (.*?); \}", page).group(1)
lights = [tuple(float(v) / 100 for v in m) for m in re.findall(r"radial-gradient\(([\d.-]+)% ([\d.-]+)% at ([\d.-]+)% ([\d.-]+)%", geo)]
assert len(lights) == 2, lights
drift = re.search(r"@keyframes atmo-drift \{ to \{ transform: translate\(([\d.-]+)%, ([\d.-]+)%\) scale\(([\d.]+)\)", page)
dx, dy, sc = float(drift.group(1)) / 100, float(drift.group(2)) / 100, float(drift.group(3))
fills = {m: float(v) / 100 for m, v in re.findall(r'\.phone\[data-mode="(\w+)"\] \{ --glass-fill: ([\d.]+)%; \}', page)}
assert set(fills) == {"light", "dark"}, fills
def rgb(h): return [int(h[i:i + 2], 16) for i in (1, 3, 5)]
def over(f, b, a): return "#" + "".join("%02X" % round(fc * a + bc * (1 - a)) for fc, bc in zip(rgb(f), rgb(b)))
spots = set()
for tx, ty, k in ((0, 0, 1), (dx, dy, sc)):
    for yi in range(43):
        for xi in range(21):
            x, y = (xi / 20 - 0.5 - tx) / k + 0.5, (yi / 42 - 0.5 - ty) / k + 0.5
            spots.add(tuple(round(max(0.0, 1 - (((x - lx) / rx) ** 2 + ((y - ly) / ry) ** 2) ** 0.5), 3) for rx, ry, lx, ly in lights))
bad, n = [], 0
for d in spec["directions"]:
    for mode in ("light", "dark"):
        pal = d["tokens"]["color"][mode]
        for inten in ("low", "medium", "high"):
            m = re.search(r'\.phone\[data-direction="%s"\]\[data-mode="%s"\]\[data-intensity="%s"\] \{ --atmo-1: (#\w{6}); --atmo-2: (#\w{6}); --atmo-a: ([\d.]+); \}' % (d["id"], mode, inten), page)
            assert m, (d["id"], mode, inten)
            c1, c2, a = m.group(1), m.group(2), float(m.group(3))
            worst = 99.0
            for f1, f2 in spots:
                g = over(c2, over(c1, pal["bg"], a * f1), a * f2)
                for ground in (g, over(pal["surfaceRaised"], g, fills[mode])):
                    worst = min(worst, min(cc.ratio(pal[i], ground) for i in cc.INKS))
            n += 1
            if worst < 4.5:
                bad.append(f"{d['id']}/{mode}/{inten}: {worst:.2f}")
assert n == len(spec["directions"]) * 6, n
assert not bad, "inks below AA on the lit ground: " + ", ".join(bad)
PYEOF
_proto_atmo_contrast() {  # [page]: the rendered page's atmosphere keeps every ink at AA
  python3 "$T/proto_atmo_guard.py" "${1:-$PROTO_OUT/prototype.html}" "$PROTO_FIX" "$KIT/scripts"
}
_proto_atmo_contrast_refuses() {  # a renderer that lights the raw accent at full strength must fail it
  python3 - "$PROTO_PY" "$PROTO_FIX" "$T/pm-atmo.html" <<'PYEOF' || return 1
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("proto", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.atmo_lights = lambda pal, mode, inten: {"light1": pal["accent"], "light2": pal["accent"], "alpha": 0.85}
m.render(json.load(open(sys.argv[2])), sys.argv[3])
PYEOF
  local out
  out=$(_proto_atmo_contrast "$T/pm-atmo.html" 2>&1) && return 1
  printf '%s' "$out" | grep -q 'inks below AA on the lit ground: calm/light/low'
}
check "prototype: atmosphere keeps every ink at AA on the lit ground and on glass (re-derived from the page)" "_proto_atmo_contrast"
check "prototype: that guard fails a renderer that lights the raw accent (negative control)" "_proto_atmo_contrast_refuses"

_proto_springs() {  # motion runs on the spring tokens: a valid linear() per spring x temperature
  python3 - "$PROTO_OUT/prototype.html" "$PROTO_FIX" <<'PYEOF'
import json, re, sys
page, spec = open(sys.argv[1]).read(), json.load(open(sys.argv[2]))
for d in spec["directions"]:
    peak = {}
    for temp in ("calm", "lively"):
        rule = re.search(r'\.phone\[data-direction="%s"\]\[data-temperature="%s"\] \{ (.*?) \}' % (d["id"], temp), page).group(1)
        for name in ("snappy", "gentle", "bouncy"):
            curve = re.search(r"--spring-%s: linear\(0, (.*?), 1\);" % name, rule).group(1)
            assert re.search(r"--spring-%s-dur: \d+ms;" % name, rule), (d["id"], temp, name)
            stops = [(float(v), float(p.rstrip("%"))) for v, p in (x.split() for x in curve.split(", "))]
            at = [p for _, p in stops]
            assert all(0 < a < b < 100 for a, b in zip(at, at[1:])), f"{d['id']}/{temp}/{name}: stops not increasing"
            peak[(temp, name)] = max(v for v, _ in stops)
    assert peak[("lively", "gentle")] > peak[("calm", "gentle")] + 0.05, "lively must overshoot more than calm"
for cls in ("in-fade", "in-push", "in-pop"):
    assert re.search(r"\.screen\.%s \{ animation: %s calc\(var\(--settle-dur\) \* var\(--mmult\)\) var\(--settle\)" % (cls, cls), page), cls
assert re.search(r"\.enter > \.blk, \.enter > \.stat-grid \{ animation: rise calc\(var\(--settle-dur\) \* var\(--mmult\)\) var\(--settle\)", page)
PYEOF
}
check "prototype: springs become CSS linear() per temperature, and screens + blocks move on the settle curve" "_proto_springs"
_proto_spring_math() {  # the generated curve really is the spring: settles at 1, overshoot matches damping
  python3 - "$PROTO_PY" <<'PYEOF'
import math, importlib.util, sys
spec = importlib.util.spec_from_file_location("proto", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for k, c in ((180, 23), (320, 16.5), (220, 12)):
    curve, ms = m.spring_curve({"stiffness": k, "damping": c, "mass": 1})
    vals = [float(x.split()[0]) for x in curve[len("linear(0, "):-len(", 1)")].split(", ")]
    zeta = c / (2 * math.sqrt(k))
    want = math.exp(-zeta * math.pi / math.sqrt(1 - zeta ** 2))
    assert abs((max(vals) - 1) - want) < 0.01, (k, c, max(vals) - 1, want)
    assert 150 < ms < 3000 and abs(vals[-1] - 1) < 0.02, (ms, vals[-1])
PYEOF
}
check "prototype: a generated spring curve overshoots exactly as its damping ratio predicts" "_proto_spring_math"

check "prototype check catches: a bad atmosphere on a direction" \
  "_proto_catches bad-atmo \"atmosphere.mode: 'neon' is not one of none, glow, field\" && _proto_catches bad-atmo 'atmosphere.grain: must be true or false'"
FRA="$T/proto-frozen-atmo"
printf '%s' '{"direction": "athletic", "mode": "dark", "atmosphere": {"mode": "field", "intensity": "high", "surface": "glass", "grain": false}}' > "$T/proto-choices-atmo.json"
rm -rf "$FRA"
check "prototype: freeze writes the atmosphere knobs + capped light colours into tokens.json and SCREENS.md" \
  "python3 '$PROTO_PY' freeze '$PROTO_FIX' '$T/proto-choices-atmo.json' --target '$FRA' >/dev/null \
   && python3 -c \"import json;t=json.load(open('$FRA/design/tokens.json'))['atmosphere'];c=json.load(open('$FRA/design/choices.json'))['atmosphere'];assert c=={'mode':'field','intensity':'high','grain':False,'surface':'glass'},c;assert {k:t[k] for k in c}==c and len(t['lights'])==2;assert all(0<t['color'][m]['alpha']<=0.85 and t['color'][m]['light1'].startswith('#') for m in ('light','dark'))\" \
   && grep -q '^Atmosphere \*\*field\*\*, intensity high, grain off, glass surfaces' '$FRA/docs/product/SCREENS.md' \
   && python3 '$KIT/scripts/check_contrast.py' '$FRA/design/tokens.json' >/dev/null"
check "prototype: freeze without atmosphere takes the direction's default (older choices still freeze)" \
  "python3 -c \"import json;c=json.load(open('$FRZ/design/choices.json'))['atmosphere'];assert c=={'mode':'glow','intensity':'medium','grain':True,'surface':'solid'},c\""
check "prototype: freeze refuses a bad atmosphere knob (writes nothing)" \
  "_proto_freeze_refuses '{\"atmosphere\": {\"mode\": \"neon\"}}' \"choices.atmosphere.mode: 'neon' is not one of none, glow, field\" \
   && _proto_freeze_refuses '{\"atmosphere\": {\"sparkle\": true}}' 'choices.atmosphere.sparkle: unknown key'"
check "prototype: panel has the atmosphere knobs, the motion preview, and Copy my choices carries atmosphere" \
  "grep -q 'id: \"ph-atmo\", text: \"Atmosphere\"' '$PROTO_OUT/prototype.html' && grep -q 'api.setAtmo(\"intensity\", v)' '$PROTO_OUT/prototype.html' \
   && grep -q 'api.setAtmo(\"surface\", v)' '$PROTO_OUT/prototype.html' && grep -q 'api.setAtmo(\"grain\", on)' '$PROTO_OUT/prototype.html' \
   && grep -q 'Preview reduced motion' '$PROTO_OUT/prototype.html' && grep -q 'variants: v, features: f, atmosphere: a' '$PROTO_OUT/prototype.html'"

# Fonts: inlined from the cache (no network here), or a Google Fonts <link> when they can't be.
_proto_fonts_inline() {
  local c="$T/proto-fonts-fake"; rm -rf "$c"; mkdir -p "$c"
  python3 - "$c" <<'PYEOF'
import hashlib, sys, pathlib
c = pathlib.Path(sys.argv[1]); url = "https://fonts.gstatic.com/s/figtree/v9/fake.woff2"
css = "".join("/* latin */\n@font-face {\n  font-family: 'Figtree';\n  font-style: normal;\n  font-weight: %d;\n  src: url(%s) format('woff2');\n}\n" % (w, url) for w in (400, 500, 600, 700))
(c / "figtree.google.css").write_text("/* latin-ext */\n@font-face { font-style: normal; font-weight: 400; src: url(https://fonts.gstatic.com/x.woff2); }\n" + css)
(c / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".woff2")).write_bytes(b"wOF2" + b"\0" * 60)
PYEOF
  APPBOX_FONT_CACHE="$c" python3 "$PROTO_PY" render "$PROTO_FIX" "$T/pf.html" >/dev/null || return 1
  grep -q '@font-face { font-family: "Figtree"; font-style: normal; font-weight: 400 700; font-display: block; src: url(data:font/woff2;base64,d09GMg' "$T/pf.html" \
    && ! grep -q 'family=Figtree' "$T/pf.html" && grep -q 'family=Newsreader' "$T/pf.html" \
    && [ "$(grep -o '@font-face' "$T/pf.html" | wc -l)" -eq 1 ]
}
check "prototype: fonts inline from the cache as one @font-face per file (latin only), others fall back to a <link>" "_proto_fonts_inline"
_proto_fonts_offline() {
  local out
  out=$(python3 "$PROTO_PY" render "$PROTO_FIX" "$T/pf2.html") || return 1
  printf '%s\n' "$out" | grep -q "note: font 'Figtree' is loaded from Google Fonts" \
    && [ "$(grep -c 'fonts.googleapis.com/css2' "$T/pf2.html")" -eq "$(_proto_font_count)" ] && ! grep -q '@font-face' "$T/pf2.html"
}
_proto_font_count() {  # the directions' 4 families + the Type knob's alternates (font-library.sh)
  python3 -c "import json,sys;sys.path.insert(0,'$KIT/scripts');import prototype as p;s=json.load(open('$PROTO_FIX'));o=p._font_families(s);print(len(o)+len([f for f in p._alt_families(s) if f not in o]))"
}
check "prototype: offline with no cache, every font is a Google Fonts <link> and render says so" "_proto_fonts_offline"

_proto_size_budget() {  # one file, and the page itself (fonts aside) stays small
  python3 - "$PROTO_OUT/prototype.html" <<'PYEOF'
import re, sys
page = open(sys.argv[1]).read()
code = re.sub(r"data:font/woff2;base64,[A-Za-z0-9+/=]+", "", page)
kb = len(code.encode()) / 1024
assert kb < 200, f"prototype is {kb:.0f} KB without fonts (budget 200 KB)"
PYEOF
}
check "prototype: size budget (under 200 KB before inlined fonts)" "_proto_size_budget"
