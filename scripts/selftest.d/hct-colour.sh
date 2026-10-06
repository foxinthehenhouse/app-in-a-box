# Colour by construction: sourced by selftest.sh with $KIT, $APP, $T and the check/skip
# helpers. Python only, nothing here needs $APP or the network.
#   scripts/hct.py          HCT + tonal palettes, ported from material-color-utilities;
#                           scripts/tests/test_hct.py pins upstream's own test values
#   scripts/palette.py      both palettes from one accent + neutral hue;
#                           scripts/tests/test_palette.py runs 20 seeds through the real
#                           check_contrast.py and check_design.py
#   prototype.py            a direction's `palette` derives its colours (check/render/freeze)
# Each guard is proven to pass on the pristine kit and to FAIL, by name, on a plant.
HC_PY="$KIT/scripts/palette.py"
HC_PROTO="$KIT/scripts/prototype.py"
HC_FIX="$KIT/../../scripts/fixtures/prototype.json"
HC_TESTS="$KIT/../../scripts/tests"

check "colour: the HCT port reproduces upstream's test values, and the palette property test passes" \
  "python3 -m unittest discover -s '$HC_TESTS' -p 'test_*.py' 2>&1 | tail -1 | grep -qx OK"

# _hc_plant <file under scripts/> <python edit of s (its text)> <test module> <expected text>:
# copy the scripts and the tests into a mirror tree, plant one edit, and the named suite
# must FAIL saying why.
_hc_plant() {
  local m="$T/hc" out
  rm -rf "$m"; mkdir -p "$m/scripts" "$m/plugins/app-in-a-box/scripts" "$m/plugins/app-in-a-box/template/scripts" "$m/plugins/app-in-a-box/template/design"
  cp -R "$HC_TESTS" "$m/scripts/tests" || return 1
  cp "$KIT/scripts/hct.py" "$KIT/scripts/palette.py" "$KIT/scripts/check_contrast.py" "$KIT/scripts/check_design.py" "$m/plugins/app-in-a-box/scripts/" || return 1
  cp "$KIT/template/scripts/check_contrast.py" "$KIT/template/scripts/check_design.py" "$m/plugins/app-in-a-box/template/scripts/" || return 1
  cp "$KIT/template/design/tokens.json" "$m/plugins/app-in-a-box/template/design/" || return 1
  python3 - "$m/plugins/app-in-a-box/scripts/$1" "$2" <<'PYEOF' || return 1
import sys
p, edit = sys.argv[1:3]
s = open(p).read(); before = s
exec(edit)
assert s != before, "the plant changed nothing"
open(p, "w").write(s)
PYEOF
  out=$(cd "$m" && python3 -m unittest "scripts/tests/$3.py" 2>&1) && return 1
  printf '%s\n' "$out" | grep -q -- "$4"
}
check "colour catches: a wrong CAM16 constant in the port (upstream's red/green/blue values fail)" \
  "_hc_plant hct.py \"s=s.replace('r_c = 0.401288 * x', 'r_c = 0.4013 * x')\" test_hct 'FAIL: test_cam_from_int'"
check "colour catches: a wrong solver matrix entry (upstream's tonal palette for blue fails)" \
  "_hc_plant hct.py \"s=s.replace('(1373.2198709594231,', '(1393.2198709594231,')\" test_hct 'FAIL: test_blue'"
check "colour catches: a tone table that breaks contrast (the property test names the gate and the pair)" \
  "_hc_plant palette.py \"s=s.replace('\\\"inkFaint\\\": (\\\"nv\\\", 42, 68)', '\\\"inkFaint\\\": (\\\"nv\\\", 58, 68)')\" test_palette 'check_contrast.py failed' \
   && grep -q '\\[light\\] inkFaint' <<<\"\$(cd '$T/hc' && python3 -m unittest scripts/tests/test_palette.py 2>&1)\""
check "colour catches: neutrals at chroma 0 (untinted-greys fires through check_design.py)" \
  "_hc_plant palette.py \"s=s.replace('NEUTRAL_CHROMA = 6.0', 'NEUTRAL_CHROMA = 0.0').replace('NEUTRAL_CHROMA_RANGE = (4.0, 24.0)', 'NEUTRAL_CHROMA_RANGE = (0.0, 24.0)')\" test_palette 'untinted-greys: color'"
check "colour catches: no turn away from the stock violet (reflex-accent fires on an edge accent)" \
  "_hc_plant palette.py \"s=s.replace('def _reflex(hex_: str) -> bool:', 'def _reflex(hex_: str) -> bool:\\n    return False')\" test_palette 'reflex-accent: color'"

# The CLI: derive prints a palette the real gates pass; --into writes it; a violet is
# turned and said; a bad accent is refused.
_hc_cli() {
  python3 "$HC_PY" derive --accent '#2F7D6B' --neutral-hue 150 > "$T/hc-pal.json" || return 1
  python3 -c "import json;d=json.load(open('$KIT/template/design/tokens.json'));d['color']=json.load(open('$T/hc-pal.json'));json.dump(d,open('$T/hc-tok.json','w'))" || return 1
  python3 "$KIT/scripts/check_contrast.py" "$T/hc-tok.json" >/dev/null && python3 "$KIT/scripts/check_design.py" "$T/hc-tok.json" >/dev/null || return 1
  cp "$KIT/template/design/tokens.json" "$T/hc-into.json"
  python3 "$HC_PY" derive --accent '#E0522B' --into "$T/hc-into.json" >/dev/null || return 1
  python3 -c "import json;a=json.load(open('$T/hc-into.json'));b=json.load(open('$KIT/template/design/tokens.json'));assert a['color']!=b['color'] and {k:v for k,v in a.items() if k!='color'}=={k:v for k,v in b.items() if k!='color'}" || return 1
  python3 "$HC_PY" derive --accent '#6366F1' 2>&1 >/dev/null | grep -q 'sits on the stock AI violet; used hue' || return 1
  local out rc; out=$(python3 "$HC_PY" derive --accent orange 2>&1); rc=$?
  [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'accent must be #RRGGBB'
}
check "colour: palette.py derive passes the gates, --into keeps every other key, violet is said, bad input refused" "_hc_cli"

# prototype.py: a direction's palette stands in for its colours, end to end.
cat > "$T/hc_mutate.py" <<'PYEOF'
import json, sys
src, name, out = sys.argv[1:4]
s = json.load(open(src))
d = s["directions"][0]
if name == "palette":  # colours derived, with one hand-set key kept
    del d["tokens"]["color"]
    d["palette"] = {"accent": "#2F7D6B", "neutralHue": 150, "neutralChroma": 8}
    d["tokens"]["color"] = {"dark": {"success": "#3DDC97"}}
elif name == "bad-accent":
    del d["tokens"]["color"]
    d["palette"] = {"accent": "teal"}
elif name == "grey":
    del d["tokens"]["color"]
    d["palette"] = {"accent": "#2F7D6B", "neutralChroma": 0}
elif name == "no-colour":
    del d["tokens"]["color"]
json.dump(s, open(out, "w"))
PYEOF
_hc_proto() {
  python3 "$T/hc_mutate.py" "$HC_FIX" palette "$T/hc-spec.json" || return 1
  python3 "$HC_PROTO" check "$T/hc-spec.json" | grep -q 'prototype check passed' || return 1
  APPBOX_OFFLINE=1 APPBOX_FONT_CACHE="$T/hc-fonts" python3 "$HC_PROTO" render "$T/hc-spec.json" "$T/hc.html" >/dev/null || return 1
  echo '{"direction": "calm", "mode": "dark"}' > "$T/hc-choices.json"
  rm -rf "$T/hc-frozen"; mkdir -p "$T/hc-frozen"
  python3 "$HC_PROTO" freeze "$T/hc-spec.json" "$T/hc-choices.json" --target "$T/hc-frozen" >/dev/null || return 1
  python3 "$KIT/scripts/check_contrast.py" "$T/hc-frozen/design/tokens.json" >/dev/null || return 1
  python3 "$KIT/scripts/check_design.py" "$T/hc-frozen/design/tokens.json" >/dev/null || return 1
  python3 - "$T/hc-frozen/design/tokens.json" "$T/hc.html" "$HC_PY" <<'PYEOF'
import json, sys, importlib.util
tok = json.load(open(sys.argv[1]))["color"]
spec = importlib.util.spec_from_file_location("pl", sys.argv[3]); pl = importlib.util.module_from_spec(spec); spec.loader.exec_module(pl)
want = pl.derive_palette("#2F7D6B", 150, 8)
page = open(sys.argv[2]).read()
assert tok["dark"]["success"] == "#3DDC97", "the hand-set key was lost in freeze"
assert '"success": "#3DDC97"' in page, "the hand-set key was lost in render"
for m, k in (("light", "accent"), ("dark", "bg"), ("light", "inkFaint")):
    assert f'"{k}": "{want[m][k]}"' in page, f"the page doesn't carry the derived {m} {k}"
PYEOF
}
check "colour: a prototype direction with a palette checks, renders and freezes to tokens the gates pass" "_hc_proto"
_hc_proto_refuses() {  # <mutation> <expected message>
  local out rc
  python3 "$T/hc_mutate.py" "$HC_FIX" "$1" "$T/hc-$1.json" || return 1
  out=$(python3 "$HC_PROTO" check "$T/hc-$1.json"); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q -- "$2"
}
check "prototype check catches: a palette accent that isn't a hex" \
  "_hc_proto_refuses bad-accent 'directions\\[0\\].palette: accent: must be #RRGGBB'"
check "prototype check catches: a palette with grey neutrals (chroma 0)" \
  "_hc_proto_refuses grey 'directions\\[0\\].palette: neutralChroma: must be a number in 4..24'"
check "prototype check catches: a direction with neither colours nor a palette" \
  "_hc_proto_refuses no-colour 'directions\\[0\\].tokens.color: needs both color.light and color.dark (tokens v2), or a palette'"

check "colour: design-directions and visual-designer use the helper; the port is credited and its licence ships" \
  "grep -q 'palette.py\" derive --accent' '$KIT/skills/design-directions/SKILL.md' \
   && grep -q 'give a direction \`\"palette\":' '$KIT/agents/visual-designer.md' \
   && grep -q '## material-color-utilities' '$KIT/../../THIRD_PARTY_NOTICES.md' \
   && grep -q 'Apache License' '$KIT/../../licenses/Apache-2.0-material-color-utilities.txt' \
   && grep -q 'material-color-utilities (TypeScript, commit 5b3618b)' '$KIT/scripts/hct.py'"
