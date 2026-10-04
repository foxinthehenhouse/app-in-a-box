#!/usr/bin/env bash
# Design gate: run Impeccable's anti-pattern detector against the rendered prototype.
# Kit CI only (job `design` in .github/workflows/kit.yml). Generated apps never install
# or download it; they carry our own ported checks instead (check_design.py and
# check-design-tells.js). See THIRD_PARTY_NOTICES.md.
#
#   IMPECCABLE=/path/to/impeccable scripts/design-gate.sh
#
# Scans, each of which must report no findings (exit 0):
#   - the HTML source of two renders: the fixture's default (calm, light, solid) and a
#     dark, glass, live-field render
#   - both renders in a real browser at phone (390x844) and desktop (1440x960) widths
# The browser scans run with reduced motion forced. That is the settled page: with
# full motion the detector samples text mid-entrance, still blurred, and reports low
# contrast that no reader ever sees (the composited contrast is checked exactly by the
# selftest instead).
# A negative control proves the detector is live: a planted page with nested cards,
# bounce easing and an overused font must FAIL (exit 2) and name those rules.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
KIT="$HERE/../plugins/app-in-a-box"
IMP="${IMPECCABLE:-impeccable}"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export DO_NOT_TRACK=1 IMPECCABLE_NO_TELEMETRY=1 IMPECCABLE_NO_UPDATE_CHECK=1 IMPECCABLE_NO_STALENESS_CHECK=1
export APPBOX_OFFLINE=1 APPBOX_FONT_CACHE="$T/fonts"  # deterministic: fonts as <link>s

command -v "$IMP" >/dev/null 2>&1 || [ -x "$IMP" ] || { echo "design-gate: no impeccable binary ($IMP)"; exit 2; }
"$IMP" --version

# The browser the detector drives, with reduced motion forced (and no sandbox as root).
CHROME="${IMPECCABLE_BROWSER:-}"
if [ -z "$CHROME" ]; then
  for c in google-chrome google-chrome-stable chromium chromium-browser /opt/pw-browsers/chromium-*/chrome-linux/chrome; do
    if command -v "$c" >/dev/null 2>&1; then CHROME="$(command -v "$c")"; break; fi
  done
fi
[ -n "$CHROME" ] || { echo "design-gate: no Chrome/Chromium for the browser scans"; exit 2; }
SANDBOX=""; [ "$(id -u)" = 0 ] && SANDBOX="--no-sandbox"
printf '#!/bin/sh\nexec "%s" %s --force-prefers-reduced-motion "$@"\n' "$CHROME" "$SANDBOX" > "$T/chrome"
chmod +x "$T/chrome"
export IMPECCABLE_BROWSER="$T/chrome"

# Two renders: the fixture's default, and dark + glass + live field.
python3 "$KIT/scripts/prototype.py" render "$HERE/fixtures/prototype.json" "$T/light.html" >/dev/null || exit 1
python3 - "$HERE/fixtures/prototype.json" "$T/dark.json" <<'PYEOF'
import json, sys
s = json.load(open(sys.argv[1]))
s["defaults"].update(direction="athletic", mode="dark", temperature="lively")
next(d for d in s["directions"] if d["id"] == "athletic")["tokens"]["atmosphere"] = {"mode": "field", "surface": "glass", "intensity": "high"}
json.dump(s, open(sys.argv[2], "w"))
PYEOF
python3 "$KIT/scripts/prototype.py" render "$T/dark.json" "$T/dark.html" >/dev/null || exit 1

fail=0
scan() {  # <label> <target> [detector args...]
  local label="$1" target="$2"; shift 2
  local out rc
  out=$("$IMP" detect --no-config "$@" "$target" 2>&1); rc=$?
  if [ "$rc" -eq 0 ]; then echo "  PASS  $label"
  else echo "  FAIL  $label (exit $rc)"; printf '%s\n' "$out" | sed 's/^/        | /'; fail=1; fi
}
for page in light dark; do
  scan "$page: source" "$T/$page.html"
  scan "$page: browser 390x844" "file://$T/$page.html" --viewport 390x844
  scan "$page: browser 1440x960" "file://$T/$page.html" --viewport 1440x960
done

# Negative control: the detector must still catch the tells it's here for.
cat > "$T/planted.html" <<'EOF'
<!doctype html><html><head><meta charset="utf-8"><title>Planted</title>
<style>
body { font-family: "Inter", sans-serif; background: #fff; color: #111; }
.card { border-radius: 16px; background: #f4f4f5; box-shadow: 0 4px 12px rgba(0,0,0,.12); padding: 24px; }
.pop { animation: pop .5s cubic-bezier(0.34, 1.56, 0.64, 1) both; }
@keyframes pop { from { transform: scale(.8); } }
</style></head><body>
<div class="card"><h2>Weekly summary for your account</h2>
  <div class="card pop"><p>Nested card with enough text to count as content.</p></div>
</div></body></html>
EOF
out=$("$IMP" detect --no-config "$T/planted.html" 2>&1); rc=$?
if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -q 'bounce-easing' && printf '%s' "$out" | grep -q 'overused-font'; then
  echo "  PASS  negative control: a planted page fails (bounce-easing, overused-font)"
else
  echo "  FAIL  negative control: the detector passed a planted page (exit $rc)"; printf '%s\n' "$out" | sed 's/^/        | /'; fail=1
fi
out=$("$IMP" detect --no-config --viewport 1440x960 "file://$T/planted.html" 2>&1); rc=$?
if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -q 'nested-cards'; then
  echo "  PASS  negative control: the browser scan catches the nested card"
else
  echo "  FAIL  negative control: the browser scan missed the nested card (exit $rc)"; printf '%s\n' "$out" | sed 's/^/        | /'; fail=1
fi

[ "$fail" -eq 0 ] && echo "design-gate: clean" || echo "design-gate: FAILED"
exit "$fail"
