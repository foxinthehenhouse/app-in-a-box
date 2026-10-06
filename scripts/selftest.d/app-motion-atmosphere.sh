# Motion, atmosphere and glass in the generated app (docs/specs/high-end-design, PR 3):
# sourced by selftest.sh with $KIT, $APP, $T and the check/refuses helpers. The app
# must paint what the founder froze in the prototype, so each check here compares the
# app's generated values with the prototype's own functions (one implementation), and
# the renderer's new refusal is proven to fire on a planted bad knob.
MA_PROTO="$KIT/scripts/prototype.py"
MA_FIX="$KIT/../../scripts/fixtures/prototype.json"
MA_MOB="$KIT/template/mobile"

# The pristine template ships an atmosphere, and its colours are the ones the prototype
# would derive for the template's own palette (so the default app is contrast-capped).
_ma_template_atmo() {
  python3 - "$KIT/scripts" "$KIT/template/design/tokens.json" <<'PYEOF'
import json, sys
sys.path.insert(0, sys.argv[1]); import prototype as p
t = json.load(open(sys.argv[2])); a = t["atmosphere"]
assert {k: a[k] for k in p.ATMO_DEFAULT} == p.ATMO_DEFAULT, a
assert a["lights"] == [list(x) for x in p.ATMO_LIGHTS], a["lights"]
for m in p.MODES:
    assert a["color"][m] == p.atmo_lights(t["color"][m], m, a["intensity"]), (m, a["color"][m])
PYEOF
}
check "atmosphere: the template's default block matches what the prototype derives for its palette" "_ma_template_atmo"
check "atmosphere: the template's light colours never leak into a direction (prototype check stays green)" \
  "python3 '$MA_PROTO' check '$MA_FIX' >/dev/null && python3 -c \"import sys;sys.path.insert(0,'$KIT/scripts');import prototype as p,json;s=json.load(open('$MA_FIX'));assert all(set(p.merged_tokens(d)['atmosphere'])<=set(p.ATMO_DEFAULT) for d in s['directions'])\""

# Parity: freeze (lively, glass, field) -> render's tokens.ts carries the frozen atmosphere
# unchanged, and `settle` is the prototype's settle_spring of the frozen gentle spring.
MA_FRZ="$T/ma-frozen"
printf '%s' '{"direction": "athletic", "mode": "dark", "temperature": "lively", "atmosphere": {"mode": "field", "intensity": "high", "surface": "glass", "grain": false}}' > "$T/ma-choices.json"
rm -rf "$MA_FRZ"
_ma_parity() {
  python3 "$MA_PROTO" freeze "$MA_FIX" "$T/ma-choices.json" --target "$MA_FRZ" >/dev/null || return 1
  python3 - "$KIT/scripts" "$MA_FRZ/design/tokens.json" <<'PYEOF'
import json, math, re, sys
sys.path.insert(0, sys.argv[1]); import prototype as p, render
t = json.load(open(sys.argv[2])); ts = render.tokens_ts(t)
def const(name):
    m = re.search(r"export const %s(?:: \w+)? = (\{.*?\n\})( as const)?;" % name, ts, re.S)
    assert m, name
    return json.loads(m.group(1))
assert const("atmosphere") == t["atmosphere"], (const("atmosphere"), t["atmosphere"])
g = t["motion"]["spring"]["gentle"]; s = const("settle")
assert g["damping"] < 2 * math.sqrt(g["stiffness"]), "lively gentle should be under-damped before settle"
assert s == p.settle_spring(g) and s["damping"] >= 2 * math.sqrt(s["stiffness"] * s["mass"]), s
PYEOF
}
check "atmosphere: freeze -> tokens.ts passes the frozen lights/alpha through; settle is damped to >= critical" "_ma_parity"
_ma_absent_or_partial() {
  python3 - "$KIT/scripts" "$KIT/template/design/tokens.json" <<'PYEOF'
import json, re, sys
sys.path.insert(0, sys.argv[1]); import prototype as p, render
t = json.load(open(sys.argv[2]))
def atmo(tok):
    return json.loads(re.search(r"export const atmosphere: Atmosphere = (\{.*?\n\});", render.tokens_ts(tok), re.S).group(1))
old = dict(t); old.pop("atmosphere")
a = atmo(old)  # a token file from before atmospheres: no light, no grain
assert a["mode"] == "none" and not a["grain"] and all(a["color"][m]["alpha"] == 0 for m in p.MODES), a
hand = dict(t, atmosphere={"mode": "glow", "intensity": "low"})  # hand-written: colours derived, capped
a = atmo(hand)
assert all(a["color"][m] == p.atmo_lights(t["color"][m], m, "low") for m in p.MODES), a
PYEOF
}
check "atmosphere: an older tokens.json renders no light; a hand-written block gets capped colours" "_ma_absent_or_partial"
_ma_render_refuses() {  # <python edit of d['atmosphere']> <expected message>
  local out rc a="$T/ma-render"; rm -rf "$a"
  python3 "$KIT/scripts/render.py" --target "$a" --name P --slug penny-jar --bundle-id com.a.b --owner o >/dev/null || return 1
  python3 -c "import json;f='$a/design/tokens.json';d=json.load(open(f));$1;json.dump(d,open(f,'w'))" || return 1
  out=$(python3 "$KIT/scripts/render.py" --target "$a" --name P --slug penny-jar --bundle-id com.a.b --owner o --force 2>&1); rc=$?
  [ "$rc" -eq 2 ] && printf '%s\n' "$out" | grep -q -- "$2"
}
check "atmosphere: render refuses a bad atmosphere knob in tokens.json (exit 2, named)" \
  "_ma_render_refuses \"d['atmosphere']['mode']='neon'\" \"ERROR: design/tokens.json can't be rendered: atmosphere.mode: 'neon' is not one of none, glow, field\" \
   && _ma_render_refuses \"d['atmosphere']['grain']='yes'\" 'atmosphere.grain: must be true or false'"
check "atmosphere: the rendered app's tokens.ts carries atmosphere, settle and a real PNG grain tile" \
  "grep -q '^export const atmosphere: Atmosphere = {' '$APP/mobile/lib/tokens.ts' && grep -q '^export const settle = {' '$APP/mobile/lib/tokens.ts' \
   && python3 -c \"import base64,re;s=open('$APP/mobile/lib/tokens.ts').read();b=base64.b64decode(re.search(r'grainTile = \\\"data:image/png;base64,([^\\\"]+)\\\"',s).group(1));assert b[:8]==b'\\x89PNG\\r\\n\\x1a\\n' and len(b)<4096\""

# The app side: who uses what. The behaviour (reduce motion, reduce transparency, glass
# fallback, parity of the painted gradient) is proven by the app's jest suite under --mobile.
check "motion: entrance() and the screen entrance move on settle, not a timing curve" \
  "python3 -c \"import re;s=open('$MA_MOB/lib/motion.ts').read();[re.search(r'export function %s\\(.*?\\n\\}' % f, s, re.S).group(0).index('.damping(settle.damping)') for f in ('entrance','screenEntrance')];assert 'motion.duration.deliberate' not in s\" \
   && grep -q 'entering={screenEntrance(reduced)}' '$MA_MOB/components/ui/Screen.tsx'"
check "atmosphere: Screen mounts ScreenAtmosphere (not on sheets), and it is a components/ui export" \
  "grep -q '{sheet ? null : <ScreenAtmosphere' '$MA_MOB/components/ui/Screen.tsx' && grep -q 'export { ScreenAtmosphere }' '$MA_MOB/components/ui/index.ts'"
check "glass: chrome only (tab bar, SheetHeader), via expo-glass-effect, honouring Reduce Transparency" \
  "grep -q 'useGlassChrome()' '$MA_MOB/app/(app)/_layout.tsx' && grep -q 'useGlassChrome()' '$MA_MOB/components/ui/Sheet.tsx' \
   && grep -q 'isReduceTransparencyEnabled' '$MA_MOB/lib/atmosphere.ts' && grep -q '^  expo-glass-effect$' '$KIT/scripts/mobile-deps.sh' \
   && ! grep -rq 'GlassView' '$MA_MOB/components/ui/Screen.tsx'"
check "motion: the haptic token map exists and the jest suite covers settle, atmosphere and glass" \
  "grep -q 'export const hapticFor' '$MA_MOB/lib/motion.ts' && grep -q 'dampingRatio(settle)' '$MA_MOB/lib/__tests__/motion.test.ts' \
   && grep -q 'useReducedTransparency' '$MA_MOB/lib/__tests__/atmosphere.test.tsx' && grep -q 'SheetHeader glass' '$MA_MOB/components/__tests__/atmosphere.test.tsx'"
check "atmosphere: SCREENS.md names ScreenAtmosphere and the settle spring with its frozen values" \
  "grep -q '\`ScreenAtmosphere\` (mounted by \`Screen\`) paints it' '$MA_FRZ/docs/product/SCREENS.md' \
   && grep -q 'spring \`settle\` (stiffness 180, damping 26.8: critically damped' '$MA_FRZ/docs/product/SCREENS.md'"
