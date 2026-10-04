# Design tells (docs/specs/high-end-design, PR 2): sourced by selftest.sh with $KIT,
# $APP, $T and the check/skip helpers. The same rules run in three places, and each is
# proven here to pass on the pristine kit and FAIL on a planted tell:
#   check_design.py         design/tokens.json (the app's gates; prototype.py check)
#   check-design-tells.js   the app's code (gates)
#   prototype.py check      the spec's layout + copy tells, and each direction's tokens
# Impeccable's own detector runs on the rendered prototype in kit CI (scripts/design-gate.sh).
CD_PY="$KIT/scripts/check_design.py"
TOK="$KIT/template/design/tokens.json"
PROTO_PY="$KIT/scripts/prototype.py"
PROTO_FIX="$KIT/../../scripts/fixtures/prototype.json"

_dc_refuses() {  # <python edit of d (the tokens dict)> <expected message>
  local out rc
  python3 -c "import json,sys;d=json.load(open('$TOK'));$1;json.dump(d,open('$T/dc.json','w'))" || return 1
  out=$(python3 "$CD_PY" "$T/dc.json"); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q -- "$2"
}
check "design tokens: the template's tokens pass check_design.py" "python3 '$CD_PY' '$TOK'"
check "design tokens: the app's copy of the check is the kit's (one implementation)" \
  "cmp -s '$KIT/template/scripts/check_design.py' '$APP/scripts/check_design.py' && grep -q 'template/scripts/check_design.py' '$CD_PY'"
check "design tokens catch: an overused display font" "_dc_refuses \"d['font']['display']='Inter'\" \"overused-font: font.display is 'Inter'\""
check "design tokens catch: an overused face in any role, case-insensitively" "_dc_refuses \"d['font']['body']='space grotesk'\" 'overused-font: font.body'"
check "design tokens allow: the phone's own system font (Roboto built in, not loaded)" \
  "python3 -c \"import json;d=json.load(open('$TOK'));d['font']['body']='Roboto';json.dump(d,open('$T/dc-sys.json','w'))\" && python3 '$CD_PY' '$T/dc-sys.json'"
check "design tokens catch: pure-grey neutrals" \
  "_dc_refuses \"d['color']['dark'].update(bg='#0D0D0D',surface='#161616',surfaceRaised='#1E1E1E',border='#2E2E2E')\" 'untinted-greys: color.dark'"
check "design tokens catch: the stock AI violet accent (and a near miss of it)" \
  "_dc_refuses \"d['color']['light']['accent']='#6366F1'\" 'reflex-accent: color.light.accent #6366F1' \
   && _dc_refuses \"d['color']['dark']['accent']='#8E62F2'\" 'reflex-accent: color.dark.accent'"
check "design tokens catch: an easing curve that overshoots" \
  "_dc_refuses \"d['motion']['easing']['enter']=[0.34,1.56,0.64,1]\" 'overshoot-easing: motion.easing.enter'"
_dc_builtins_agree() {
  python3 - "$KIT/template/scripts/check_design.py" "$KIT/template/mobile/lib/fonts.ts" <<'PYEOF'
import re, sys, importlib.util
spec = importlib.util.spec_from_file_location("cd", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
ts = re.search(r"BUILT_IN_FONTS = new Set\(\[(.*?)\]\)", open(sys.argv[2]).read()).group(1)
assert {f.lower() for f in re.findall(r'"([^"]+)"', ts)} == m.BUILT_IN, (m.BUILT_IN, ts)
PYEOF
}
check "design tokens: the built-in font list matches the app's lib/fonts.ts" "_dc_builtins_agree"

# The app's code-level guard: its own node:test suite (positive + planted negatives).
if command -v node >/dev/null 2>&1; then
  check "design code: check-design-tells.js passes on the template and its self-tests pass" \
    "cd '$KIT/template/mobile' && node scripts/check-design-tells.js && node --test scripts/__tests__/check-design-tells.test.js"
  _dct_plant() {  # the guard must fail on a real-looking plant in a rendered app
    local c="$T/dct"; rm -rf "$c"; mkdir -p "$c"
    (cd "$APP/mobile" && tar --exclude=node_modules -cf - app components lib locales scripts) | (cd "$c" && tar -xf -) || return 1
    printf '\nexport const pop = Easing.bezier(0.34, 1.56, 0.64, 1);\n' >> "$c/lib/motion.ts"
    local out; out=$(cd "$c" && node scripts/check-design-tells.js 2>&1) && return 1
    printf '%s' "$out" | grep -q 'lib/motion.ts:[0-9]*: bounce-easing'
  }
  check "design code: the guard fails a rendered app with a bounce curve added (negative control)" "_dct_plant"
else
  skip "design code: check-design-tells.js self-tests" "node"
fi
check "design: both checks are in the app's npm run gates" \
  "grep -q 'node scripts/check-design-tells.js' '$KIT/scripts/mobile-deps.sh' && grep -q 'python3 ../scripts/check_design.py ../design/tokens.json' '$KIT/scripts/mobile-deps.sh'"

# prototype.py check: tokens per direction, plus the spec's own layout + copy tells.
cat > "$T/design_mutate.py" <<'PYEOF'
import json, sys
src, name, out = sys.argv[1:4]
s = json.load(open(src))
home = next(x for x in s["screens"] if x["id"] == "home")
blocks = home["variants"][0]["blocks"]
if name == "font":
    s["directions"][0]["tokens"]["font"]["display"] = "Geist"
elif name == "eyebrows":
    next(b for b in blocks if b["type"] == "card")["eyebrow"] = "Reminder"
elif name == "card-wall":
    card = next(b for b in blocks if b["type"] == "card")
    blocks[1:1] = [dict(card, title=f"Card {n}") for n in "abc"]
elif name == "emoji-label":
    next(b for b in blocks if b["type"] == "button")["label"] = "🚀 Add entry"
elif name == "emoji-bullet":
    blocks.append({"type": "text", "body": "✅ Drink a glass of water first"})
json.dump(s, open(out, "w"))
PYEOF
_dp_catches() {  # <mutation> <expected message>
  local out rc
  python3 "$T/design_mutate.py" "$PROTO_FIX" "$1" "$T/dp-$1.json" || return 1
  out=$(python3 "$PROTO_PY" check "$T/dp-$1.json"); rc=$?
  [ "$rc" -eq 1 ] && printf '%s\n' "$out" | grep -q -- "$2"
}
check "prototype check catches: an overused font in a direction" "_dp_catches font \"directions\\[calm\\]: design: overused-font: font.display is 'Geist'\""
check "prototype check catches: an eyebrow over every heading" "_dp_catches eyebrows 'screens\\[home\\].variants\\[list\\]: 2 eyebrows'"
check "prototype check catches: a wall of equal cards" "_dp_catches card-wall '4+ cards in a row'"
check "prototype check catches: emoji as a label, and as a bullet" \
  "_dp_catches emoji-label 'emoji as UI' && _dp_catches emoji-bullet 'emoji as UI'"

# The rendered prototype holds itself to the same motion rule the detector enforces.
_dp_motion() {
  APPBOX_OFFLINE=1 APPBOX_FONT_CACHE="$T/dp-fonts" python3 "$PROTO_PY" render "$PROTO_FIX" "$T/dp.html" >/dev/null || return 1
  python3 - "$T/dp.html" <<'PYEOF'
import re, sys
page = open(sys.argv[1]).read()
css = "\n".join(re.findall(r"<style>(.*?)</style>", page, re.S))
# 1. screen-scale motion settles: the --settle curve never passes 1
for curve in re.findall(r"--settle: linear\(0, (.*?), 1\);", css):
    assert max(float(x.split()[0]) for x in curve.split(", ")) <= 1.0005, "settle overshoots"
assert re.search(r"\.screen\.in-fade \{ animation: in-fade calc\(var\(--settle-dur\) \* var\(--mmult\)\) var\(--settle\)", css)
# 2. no animation shorthand names a spring/bounce (what the detector flags), and no
#    cubic-bezier anywhere overshoots
for m in re.finditer(r"animation(?:-name)?\s*:\s*([^;{}]*)", css):
    assert not re.search(r"bounce|elastic|wobble|jiggle|spring", m.group(1), re.I), m.group(0)
for m in re.finditer(r"cubic-bezier\(([^)]*)\)", css):
    _, y1, _, y2 = (float(v) for v in m.group(1).split(","))
    assert -0.1 <= y1 <= 1.1 and -0.1 <= y2 <= 1.1, m.group(0)
# 3. the phone itself isn't a card around the cards (the frame lives on .phone-slot)
phone = re.search(r"\n\.phone \{(.*?)\n\}", css, re.S).group(1)
assert "box-shadow" not in phone, "the .phone rule has a shadow again (it reads as a card)"
# 4. the header eyebrow is a plain line, not a tracked uppercase kicker
assert 'b.eyebrow ? el("p", { class: "t-secondary eyebrow"' in page
PYEOF
}
check "prototype: screen motion settles without overshoot, no bounce curves, phone isn't a card, no kicker" "_dp_motion"
_dp_motion_refuses() {  # put the old overshooting curve back: the check must fail
  python3 - "$PROTO_PY" "$PROTO_FIX" "$T/dp-bad.html" <<'PYEOF' || return 1
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("proto", sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.TEMPERATURE["lively"]["enter"] = [0.34, 1.56, 0.64, 1]
m.render(json.load(open(sys.argv[2])), sys.argv[3])
PYEOF
  ! python3 -c "
import re,sys
css=open('$T/dp-bad.html').read()
for m in re.finditer(r'cubic-bezier\(([^)]*)\)', css):
    y1,y2=(float(v) for v in m.group(1).split(',')[1::2])
    assert -0.1<=y1<=1.1 and -0.1<=y2<=1.1
"
}
check "prototype: that motion check fails an overshooting curve (negative control)" "_dp_motion_refuses"

check "design: the critique step screenshots the prototype and the critic reads the PNGs" \
  "grep -q 'proto_shots.mjs\" design/prototype.html design/shots' '$KIT/skills/prototype/SKILL.md' \
   && grep -q 'design/avoid.md' '$KIT/skills/prototype/SKILL.md' && grep -q 'design/shots/' '$KIT/agents/design-critic.md' \
   && grep -q 'exit(3)' '$KIT/scripts/proto_shots.mjs' && node --check '$KIT/scripts/proto_shots.mjs'"
check "design: TASTE.md credits Impeccable (Apache-2.0) and platform-design-skills (MIT); licences ship" \
  "grep -q 'Apache License 2.0' '$KIT/docs/TASTE.md' && grep -q 'platform-design-skills' '$KIT/docs/TASTE.md' \
   && grep -q 'Apache License' '$KIT/../../licenses/Apache-2.0-impeccable.txt' && grep -q 'MIT License' '$KIT/../../licenses/MIT-platform-design-skills.txt' \
   && grep -q 'never installed into, or downloaded by, a generated app' '$KIT/../../THIRD_PARTY_NOTICES.md'"
check "design: TASTE.md has the Motion and Platform sections, and the growing avoid-list rule" \
  "grep -qx '## Motion' '$KIT/docs/TASTE.md' && grep -qx '## Platform (iOS and Android)' '$KIT/docs/TASTE.md' && grep -q 'This list grows' '$KIT/docs/TASTE.md'"
check "design: generated apps never get the Impeccable detector" \
  "! grep -rqi 'impeccable-linux\|npx impeccable\|impeccable install' '$APP' --include=*.json --include=*.yml --include=*.sh --include=*.ts --include=*.js"
