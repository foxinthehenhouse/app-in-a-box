# Type library + the prototype's Type knob: sourced by selftest.sh with $KIT, $APP, $T
# and the check/skip helpers. Python only; renders are offline (fonts fall back to
# Google Fonts <link>s from an empty cache), so nothing here needs the network.
#   prototype.py fonts     scripts/proto/fonts.json: OFL-1.1, no Reserved Font Name, not
#                          overused, pairings of listed families, and the
#                          design-directions archetype table naming only listed faces
#   render / freeze        the knob offers same-personality pairings, and a pick reaches
#                          design/tokens.json -> font (older choices still freeze)
# Each guard is proven to pass on the pristine kit and to FAIL, by name, on a plant.
FL_PY="$KIT/scripts/prototype.py"
FL_LIB="$KIT/scripts/proto/fonts.json"
FL_SKILL="$KIT/skills/design-directions/SKILL.md"
FL_FIX="$KIT/../../scripts/fixtures/prototype.json"
export APPBOX_OFFLINE=1 APPBOX_FONT_CACHE="$T/fl-fonts-empty"

check "type library: prototype.py fonts passes on the shipped library and archetype table" \
  "python3 '$FL_PY' fonts | grep -q 'type library check passed'"

# Independent of the guard: every family recorded OFL-1.1, rfn false, ~45 of them, and
# none on the app's own overused list (read from the template's check_design.py).
_fl_data() {
  python3 - "$FL_LIB" "$KIT/template/scripts/check_design.py" <<'PYEOF'
import json, sys, importlib.util
lib = json.load(open(sys.argv[1]))
spec = importlib.util.spec_from_file_location("cd", sys.argv[2]); cd = importlib.util.module_from_spec(spec); spec.loader.exec_module(cd)
fams = {f["family"]: f for f in lib["families"]}
assert 40 <= len(fams) <= 60, len(fams)
for n, f in fams.items():
    assert f["license"] == "OFL-1.1" and f["rfn"] is False, n
    assert n.lower() not in cd.OVERUSED_FONTS and n.lower() not in cd.BUILT_IN, n
for p in lib["pairings"]:
    assert all(p[r] in fams for r in ("display", "body", "mono") if r in p), p
# the families whose OFL.txt reserves a name stay out
assert not {"IBM Plex Mono", "Varela Round", "Readex Pro", "Quicksand", "Merriweather"} & set(fams)
PYEOF
}
check "type library: every family OFL-1.1 with no RFN, none overused, pairings use listed families" "_fl_data"

# _fl_refuses <python edit of lib> <expected message> [skill text edit]: the guard exits 1
# AND names the problem.
_fl_refuses() {
  local out rc
  python3 - "$FL_LIB" "$FL_SKILL" "$T/fl-lib.json" "$T/fl-skill.md" "$1" "${3:-}" <<'PYEOF' || return 1
import json, sys
lib = json.load(open(sys.argv[1])); skill = open(sys.argv[2]).read()
exec(sys.argv[5])
if sys.argv[6]:
    exec(sys.argv[6])
json.dump(lib, open(sys.argv[3], "w")); open(sys.argv[4], "w").write(skill)
PYEOF
  out=$(python3 "$FL_PY" fonts --library "$T/fl-lib.json" --skill "$T/fl-skill.md"); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q -- "$2"
}
check "type library catches: an overused family (Inter)" \
  "_fl_refuses \"lib['families'][0]['family']='Inter'\" \"families\\[Inter\\]: is on check_design.py's OVERUSED_FONTS\""
check "type library catches: a family that declares a Reserved Font Name" \
  "_fl_refuses \"lib['families'][1]['rfn']=True\" 'declares a Reserved Font Name (rfn must be false)'"
check "type library catches: a family that isn't OFL-1.1" \
  "_fl_refuses \"lib['families'][2]['license']='Apache-2.0'\" \"license must be OFL-1.1, got 'Apache-2.0'\""
check "type library catches: a pairing naming a family the library doesn't list" \
  "_fl_refuses \"lib['pairings'][0]['body']='Baloo 2'\" \"pairings\\[red-hat\\].body: 'Baloo 2' is not a listed family\""
check "type library catches: a pairing using a display-only face as body" \
  "_fl_refuses \"lib['pairings'][0]['body']='Gloock'\" \"pairings\\[red-hat\\].body: 'Gloock' isn't suited to body\""
check "type library catches: the archetype table suggesting an unlisted family" \
  "_fl_refuses 'pass' \"the archetype table suggests 'Baloo 2', which is not in fonts.json\" \
   \"skill = skill.replace('(Fredoka / Nunito)', '(Nunito / Baloo 2)')\""
check "type library catches: the archetype table gone missing (never passes on nothing)" \
  "_fl_refuses 'pass' 'no archetype table with a Type pairing column' \"skill = skill.replace('Type pairing', 'Type')\""

# The knob offers pairings with the direction's personality, at most three, and
# nothing for a direction on the system font or a face outside the library.
FL_OUT="$T/fl-out"
rm -rf "$FL_OUT" && mkdir -p "$FL_OUT"
_fl_render() {
  python3 "$FL_PY" render "$FL_FIX" "$FL_OUT/prototype.html" >/dev/null || return 1
  python3 - "$FL_OUT/prototype.html" <<'PYEOF'
import json, re, sys
page = open(sys.argv[1]).read()
cfg = json.loads(re.search(r'<script type="application/json" id="proto-config">(.*?)</script>', page, re.S).group(1))
opts = cfg["typeOptions"]
assert [o["id"] for o in opts["calm"]] == ["red-hat", "wix-madefor", "golos-martian"], opts["calm"]
assert opts["athletic"] == [], opts["athletic"]          # Inter Tight + System: not in the library
assert all(len(v) <= 3 for v in opts.values())
rh = opts["calm"][0]
assert rh["label"] == "Red Hat Display + Red Hat Text" and rh["stacks"]["display"].startswith('"Red Hat Display", ')
# every offered family is loadable: inlined or a <link>, asking only for weights it has
for fam in ("Red Hat Display", "Red Hat Text", "Red Hat Mono", "Petrona", "Besley"):
    assert ("family=" + fam.replace(" ", "+")) in page or f'font-family: "{fam}"' in page, fam
assert "family=Red+Hat+Text:wght@400;500;600;700&amp;" in page
for needle in ('api.setFont(v === "default" ? null : v)', '"Direction default"', 'phone.style.setProperty("--font-" + r, p.stacks[r])',
               "c.font = { pairing: p.id, display: p.display, body: p.body };", 'if (k === "direction" && !pairing(v, state.font)) state.font = null;'):
    assert needle in page, needle
PYEOF
}
check "prototype Type knob: same-personality pairings offered, their fonts loadable, wired to choices" "_fl_render"
check "prototype Type knob: a single-weight family is requested at the weights it has (no 400 from Google)" \
  "python3 -c \"import sys;sys.path.insert(0,'$KIT/scripts');import prototype as p;assert ':wght@400&' in p._css2_url('Young Serif') and ':wght@400;500;600;700&' in p._css2_url('Figtree')\""

# freeze: the knob's pick reaches tokens.font; older choices (no font) still freeze.
_fl_freeze() {  # <choices json> <target dir> [spec]
  printf '%s' "$1" > "$T/fl-choices.json"
  rm -rf "$2"
  python3 "$FL_PY" freeze "${3:-$FL_FIX}" "$T/fl-choices.json" --target "$2" >/dev/null
}
check "prototype Type knob: freeze writes the pairing into tokens.font, choices.json and SCREENS.md" \
  "_fl_freeze '{\"font\": {\"pairing\": \"red-hat\", \"display\": \"Red Hat Display\", \"body\": \"Red Hat Text\", \"mono\": \"Red Hat Mono\"}}' '$T/fl-frz' \
   && python3 -c \"import json;t=json.load(open('$T/fl-frz/design/tokens.json'));c=json.load(open('$T/fl-frz/design/choices.json'));assert t['font']=={'display':'Red Hat Display','body':'Red Hat Text','mono':'Red Hat Mono'},t['font'];assert c['font']=={'pairing':'red-hat','display':'Red Hat Display','body':'Red Hat Text','mono':'Red Hat Mono'},c['font']\" \
   && grep -qF '| Type | display Red Hat Display, body Red Hat Text, mono Red Hat Mono (pairing \`red-hat\`' '$T/fl-frz/docs/product/SCREENS.md' \
   && python3 '$KIT/scripts/check_design.py' '$T/fl-frz/design/tokens.json' >/dev/null"
check "prototype Type knob: older choices (no font) still freeze, on the direction's own faces" \
  "_fl_freeze '{\"direction\": \"editorial\"}' '$T/fl-frz-old' \
   && python3 -c \"import json;t=json.load(open('$T/fl-frz-old/design/tokens.json'));c=json.load(open('$T/fl-frz-old/design/choices.json'));assert t['font']=={'display':'Newsreader','body':'System','mono':'Menlo'},t['font'];assert c['font']['pairing']=='default'\""
# A face with fewer weights: each role takes the family's nearest real weight, so the
# app's lib/fonts.ts can register every one (its test fails on a missing weight).
_fl_weights() {
  python3 -c "import json;s=json.load(open('$FL_FIX'));d=next(x for x in s['directions'] if x['id']=='editorial');d['tokens']['font']['display']='Bodoni Moda';json.dump(s,open('$T/fl-bodoni.json','w'))" || return 1
  _fl_freeze '{"direction": "editorial", "font": {"display": "Young Serif", "body": "Albert Sans"}}' "$T/fl-frz-ys" "$T/fl-bodoni.json" || return 1
  python3 - "$T/fl-frz-ys/design/tokens.json" "$FL_LIB" <<'PYEOF'
import json, sys
t, lib = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
have = {f["family"]: f["weights"] for f in lib["families"]}
assert t["font"]["display"] == "Young Serif" and t["font"]["body"] == "Albert Sans", t["font"]
assert t["type"]["title"]["weight"] == "400" and t["type"]["display"]["weight"] == "400", t["type"]
for role, spec in t["type"].items():
    fam = t["font"][spec.get("font", "body")]
    assert fam not in have or int(spec["weight"]) in have[fam], (role, fam, spec["weight"])
PYEOF
}
check "prototype Type knob: freeze clamps each role to a weight the new family has" "_fl_weights"

_fl_freeze_refuses() {  # <choices json> <expected message>: exit 1, the message, nothing written
  local out rc
  printf '%s' "$1" > "$T/fl-bad.json"
  rm -rf "$T/fl-frz-bad"
  out=$(python3 "$FL_PY" freeze "$FL_FIX" "$T/fl-bad.json" --target "$T/fl-frz-bad"); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q -- "$2" && [ ! -e "$T/fl-frz-bad/design/tokens.json" ]
}
check "prototype Type knob: freeze refuses a pairing the knob never offered that direction" \
  "_fl_freeze_refuses '{\"font\": {\"display\": \"Young Serif\", \"body\": \"Albert Sans\"}}' \
   \"choices.font: 'Young Serif' + 'Albert Sans' is not a pairing the Type knob offers for direction 'calm'\""
check "prototype Type knob: freeze refuses a malformed font choice (unknown key, wrong mono)" \
  "_fl_freeze_refuses '{\"font\": {\"display\": \"Red Hat Display\", \"body\": \"Red Hat Text\", \"size\": 3}}' 'choices.font.size: unknown key' \
   && _fl_freeze_refuses '{\"font\": {\"display\": \"Red Hat Display\", \"body\": \"Red Hat Text\", \"mono\": \"Menlo\"}}' \"choices.font.mono: 'Menlo' doesn't match\""

check "type library: the prototype and design-directions skills document the Type knob and the library" \
  "grep -q 'scripts/proto/fonts.json' '$FL_SKILL' && grep -q 'prototype.py fonts' '$FL_SKILL' \
   && grep -q 'The Type knob' '$KIT/skills/prototype/SKILL.md' && grep -q 'font: {display, body}' '$KIT/skills/prototype/SKILL.md'"
