# Trust by default, the launch gate (docs/specs/trust-by-default): sourced by selftest.sh
# with $KIT, $APP, $T and the check/refuses helpers.
#
# The generated app's scripts/risk_gate.py is what `ship` runs first and `next` reads.
# Each guard is proven to pass on a clean screen and to FAIL, naming the item, on a
# planted one: an open question, an accepted risk with no owner or date, a high-tier
# category with nothing resolved, a screen that touches an unscreened category. A new
# location feature on a standard app re-screens it and raises the tier.
#
# The category data is a five-entry stand-in (selftest.d/fixtures/risk-categories.json)
# in the contract's format, so this area never depends on the real categories.json.

LG_PY="$APP/scripts/risk_gate.py"
LG_CATS="$HERE/selftest.d/fixtures/risk-categories.json"
# --categories always wins over the kit lookup; the kit's full screen stays out unless a
# check asks for it, so these test the gate itself.
LG="env -u CLAUDE_PLUGIN_ROOT -u APPBOX_RISK_CATEGORIES APPBOX_RISK_SCREEN=none python3 $LG_PY"

_lg_app() {  # <dir> <risk JSON, or "none"> : a minimal app with a brief
  rm -rf "$1" && mkdir -p "$1/design" "$1/docs/product"
  if [ "$2" = none ]; then echo '{"decisions": []}' > "$1/design/brief.json"
  else printf '{"decisions": [], "risk": %s}\n' "$2" > "$1/design/brief.json"; fi
}
# A screened, high-tier idea with every item answered or properly accepted.
LG_CLEAN='{"tier": "high", "categories": [{"id": "minors", "why": "a kids app", "source": "inferred"}],
  "questions": [{"id": "minors.consent", "category": "minors", "status": "asked", "answer": "verified parental consent"}],
  "abuse_cases": [{"actor": "a stranger", "harm": "contacts a child", "mitigation": "no messaging"}],
  "accepted": [{"item": "minors.analytics", "by": "owner", "on": "2026-10-06", "note": "first-party only"}],
  "screened_at": "shape", "declined": []}'
LG_STANDARD='{"tier": "standard", "categories": [], "questions": [], "abuse_cases": [], "accepted": [], "screened_at": "shape", "declined": []}'
_lg_risk() {  # <dir> <python edit of r (the risk dict)>
  python3 -c "import json;p='$1/design/brief.json';b=json.load(open(p));r=b['risk'];$2;json.dump(b,open(p,'w'))"
}
_lg_tier() { python3 -c "import json;print(json.load(open('$1/design/brief.json'))['risk']['tier'])"; }
_lg_check() { $LG check --app "$1" --categories "$LG_CATS"; }

check "launch gate: the app ships the kit's one gate (scripts/risk_gate.py)" \
  "cmp -s '$KIT/template/scripts/risk_gate.py' '$LG_PY'"

_lg_clean_passes() {
  local d="$T/lg-clean" out; _lg_app "$d" "$LG_CLEAN"
  out=$(_lg_check "$d") || { echo "$out"; return 1; }
  grep -q 'no open risk items (tier high)' <<<"$out" && grep -q 'not a compliance sign-off' <<<"$out" \
    && ! grep -qi 'is compliant\|you are compliant' <<<"$out"
}
check "launch gate: a screened idea with every item answered or accepted passes (and says it's no sign-off)" "_lg_clean_passes"

_lg_app "$T/lg-open" "$LG_CLEAN"
_lg_risk "$T/lg-open" "r['questions'][0].update(status='deferred', answer=None, ask_at='pre-launch')"
refuses "launch gate: an open risk question blocks ship, named with its text" \
  "_lg_check '$T/lg-open'" "open question \`minors.consent\` (minors, parked until pre-launch): How does a parent or guardian consent?"
_lg_app "$T/lg-high" "$LG_CLEAN"
_lg_risk "$T/lg-high" "r['questions']=[]; r['accepted']=[]"
refuses "launch gate: a high-tier category with nothing answered or accepted blocks ship" \
  "_lg_check '$T/lg-high'" "high-tier category \`minors\` has no resolved or accepted item"
_lg_app "$T/lg-blank" "$LG_CLEAN"
_lg_risk "$T/lg-blank" "r['questions'][0].update(answer='  ')"
refuses "launch gate: an 'asked' question with a blank answer is still open" \
  "_lg_check '$T/lg-blank'" "open question \`minors.consent\`"

_lg_app "$T/lg-nobody" "$LG_CLEAN"
_lg_risk "$T/lg-nobody" "del r['accepted'][0]['by']"
refuses "launch gate: an accepted risk with no owner is rejected" \
  "_lg_check '$T/lg-nobody'" "accepted risk \`minors.analytics\` is rejected: no owner (\`by\`)"
_lg_app "$T/lg-nodate" "$LG_CLEAN"
_lg_risk "$T/lg-nodate" "r['accepted'][0]['on']='later'"
refuses "launch gate: an accepted risk with no real date is rejected" \
  "_lg_check '$T/lg-nodate'" "accepted risk \`minors.analytics\` is rejected: no date (\`on\`, YYYY-MM-DD)"
_lg_app "$T/lg-acc" "$LG_CLEAN"
_lg_risk "$T/lg-acc" "r['questions'][0].update(status='open', answer=None); r['accepted'].append({'item': 'minors.consent', 'on': '2026-10-06'})"
refuses "launch gate: an unsigned acceptance doesn't resolve the question it names" \
  "_lg_check '$T/lg-acc'" "open question \`minors.consent\`"
_lg_risk "$T/lg-acc" "r['accepted'][-1]['by']='owner'"
check "launch gate: the same acceptance with owner and date resolves it (control)" "_lg_check '$T/lg-acc'"

_lg_app "$T/lg-never" none
refuses "launch gate: an idea that was never risk-screened can't ship" \
  "_lg_check '$T/lg-never'" "the idea was never risk-screened"
_lg_app "$T/lg-stop" "$LG_CLEAN"
_lg_risk "$T/lg-stop" "r['tier']='stop'"
refuses "launch gate: a stop-tier design can't ship" "_lg_check '$T/lg-stop'" "tier is \`stop\`"

# Re-screen: a new location feature on a standard app.
_lg_rescreen_raises() {
  local d="$T/lg-rs" out; _lg_app "$d" "$LG_STANDARD"
  _lg_check "$d" >/dev/null || { echo "standard app should pass first"; return 1; }
  $LG rescreen --app "$d" --categories "$LG_CATS" --text "Show runners nearby on a live map" --check >/dev/null \
    && { echo "--check should exit 1 on a new category"; return 1; }
  [ "$(_lg_tier "$d")" = standard ] || { echo "--check wrote the brief"; return 1; }
  out=$($LG rescreen --app "$d" --categories "$LG_CATS" --text "Show runners nearby on a live map") || { echo "$out"; return 1; }
  grep -q "new category \`location\` ('map'); tier standard -> elevated" <<<"$out" || { echo "$out"; return 1; }
  [ "$(_lg_tier "$d")" = elevated ] || { echo "tier is $(_lg_tier "$d")"; return 1; }
  out=$(_lg_check "$d") && { echo "gate still passes after the re-screen"; return 1; }
  grep -q 'open question `location.consent` (location): Who agrees to share a location' <<<"$out"
}
check "re-screen: a new location feature on a standard app adds the category, raises the tier, and blocks ship until answered" \
  "_lg_rescreen_raises"
_lg_rescreen_quiet() {
  local d="$T/lg-rsq" out; _lg_app "$d" "$LG_STANDARD"
  out=$($LG rescreen --app "$d" --categories "$LG_CATS" --text "A roadmap screen and a dark mode toggle") || return 1
  grep -q 'no new category' <<<"$out" && [ "$(_lg_tier "$d")" = standard ]
}
check "re-screen: a feature with no trigger word ('roadmap' is not 'map') leaves the tier alone (control)" "_lg_rescreen_quiet"
_lg_rescreen_combo() {  # health and ai_decisions are each elevated; together they're high
  local d="$T/lg-rsc"; _lg_app "$d" "$LG_STANDARD"
  $LG rescreen --app "$d" --categories "$LG_CATS" --text "Log a symptom" >/dev/null || return 1
  [ "$(_lg_tier "$d")" = elevated ] || { echo "one category: $(_lg_tier "$d")"; return 1; }
  $LG rescreen --app "$d" --categories "$LG_CATS" --text "AI triage of your symptoms" >/dev/null || return 1
  [ "$(_lg_tier "$d")" = high ] || { echo "combination: $(_lg_tier "$d")"; return 1; }
}
check "re-screen: a risky combination (health + automated decisions) raises one more tier" "_lg_rescreen_combo"
_lg_rescreen_delegates() {  # a kit screen that is present but doesn't do the job: the backstop still holds
  local d="$T/lg-rsd" fake="$T/lg-fake-screen.py"; _lg_app "$d" "$LG_STANDARD"
  printf 'import sys\nprint("fake screen ran with", sys.argv[1])\nsys.exit(2)\n' > "$fake"
  local out; out=$(env -u CLAUDE_PLUGIN_ROOT APPBOX_RISK_SCREEN="$fake" python3 "$LG_PY" rescreen --app "$d" \
    --categories "$LG_CATS" --text "a GPS run tracker") || return 1
  grep -q 'fake screen ran with rescreen' <<<"$out" && [ "$(_lg_tier "$d")" = elevated ]
}
check "re-screen: calls the kit's risk_screen.py when present, and backstops whatever it leaves uncovered" "_lg_rescreen_delegates"
_lg_app "$T/lg-nocat" "$LG_STANDARD"
refuses "re-screen: with no category data it says so and tells the agent to run the shape risk step" \
  "cd '$T/lg-nocat' && env -u CLAUDE_PLUGIN_ROOT -u APPBOX_RISK_CATEGORIES APPBOX_RISK_SCREEN=none python3 '$LG_PY' rescreen --text 'a map'" \
  "Run the risk step of the App in a Box shape skill"

# SCREENS.md changes: the gate scans them, so an unscreened category can't reach launch.
_lg_app "$T/lg-screens" "$LG_CLEAN"
printf '## Screen: Chat\nKids message each other.\n' > "$T/lg-screens/docs/product/SCREENS.md"
refuses "launch gate: SCREENS.md naming a category the screen never covered blocks ship" \
  "_lg_check '$T/lg-screens'" "docs/product/SCREENS.md mentions \`ugc\` ('chat') but the risk screen never covered it"
_lg_risk "$T/lg-screens" "r['accepted'].append({'item': 'ugc', 'by': 'owner', 'on': '2026-10-06', 'note': 'parent-approved contacts only'})"
check "launch gate: the owner's signed call on that category clears it (control)" "_lg_check '$T/lg-screens'"

# The owner's checklist.
_lg_checklist() {
  local d="$T/lg-cl" f; _lg_app "$d" "$LG_CLEAN"; f="$d/docs/product/COMPLIANCE.md"
  $LG checklist --app "$d" --categories "$LG_CATS" >/dev/null || return 1
  grep -q 'Talk to counsel before launch' "$f" && grep -q 'not a statement that the app complies' "$f" \
    && grep -q 'Apple 1.3 (Kids Category)' "$f" && grep -q 'COPPA: children under 13 in the US (https://' "$f" \
    && grep -q 'Age rating' "$f" && grep -q 'Privacy labels' "$f" && grep -q '`minors.analytics`, by owner on 2026-10-06' "$f" \
    && ! grep -qiE '(is|are) (fully )?compliant' "$f" || { echo "content"; return 1; }
  sed -i.bak 's/^- \[ \] A privacy policy URL/- [x] A privacy policy URL/' "$f" && rm -f "$f.bak"
  printf 'My own note.\n' >> "$f"
  $LG checklist --app "$d" --categories "$LG_CATS" --check || { echo "ticks/notes counted as drift"; return 1; }
  _lg_risk "$d" "r['tier']='elevated'"
  $LG checklist --app "$d" --categories "$LG_CATS" --check >/dev/null && { echo "drift missed"; return 1; }
  $LG checklist --app "$d" --categories "$LG_CATS" >/dev/null
  grep -q '^- \[x\] A privacy policy URL' "$f" && grep -q 'My own note.' "$f" && ! grep -q 'Talk to counsel' "$f"
}
check "checklist: per category (store, age rating, privacy labels, regimes with links), counsel at high only, ticks and notes kept, drift caught" \
  "_lg_checklist"

# next surfaces open risk items through the same gate.
_lg_next() {  # <expected count> <risk JSON or none> <python edit of r, or empty>
  local d="$T/lg-next" n
  _lg_app "$d" "$2" && mkdir -p "$d/.agents/skills/next" "$d/scripts"
  cp "$APP/.agents/skills/next/signals.py" "$d/.agents/skills/next/" && cp "$LG_PY" "$d/scripts/"
  printf 'progress:\n  preflight: done\n  interview: done\n  validate: done\n  design: done\n  accounts: done\n  scaffold: done\n  provision: done\n  harness: done\n  verify: done\n  first_feature: done\n' > "$d/appbox.yaml"
  [ -n "$3" ] && _lg_risk "$d" "$3"
  n=$(cd "$d" && CLAUDE_PROJECT_DIR="$d" python3 .agents/skills/next/signals.py | python3 -c "import json,sys;print(len(json.load(sys.stdin)['risk_open']))")
  [ "$n" = "$1" ] || { echo "risk_open: $n, expected $1"; return 1; }
  [ "$1" = 0 ] || (cd "$d" && CLAUDE_PROJECT_DIR="$d" python3 .agents/skills/next/signals.py --line) | grep -q "risk item(s) are open and \`ship\` will refuse"
}
check "next: signals.py surfaces open risk items, and the session line says ship will refuse" \
  "_lg_next 1 '$LG_CLEAN' \"del r['accepted'][0]['on']\""
check "next: a clean screen and an unscreened app surface nothing (controls)" \
  "_lg_next 0 '$LG_CLEAN' '' && _lg_next 0 none ''"

# The skills run the gate; the eval keeps ship from claiming compliance.
_lg_wired() {
  local s="$APP/.agents/skills"
  grep -q 'python3 scripts/risk_gate.py check' "$s/ship/SKILL.md" && grep -q 'Never tell the owner the app is compliant' "$s/ship/SKILL.md" \
    && grep -q 'python3 scripts/risk_gate.py checklist' "$s/ship/SKILL.md" || { echo ship; return 1; }
  grep -q 'risk_open' "$s/next/SKILL.md" || { echo next; return 1; }
  grep -q 'python3 scripts/risk_gate.py rescreen --file <spec path>' "$s/build-feature/SKILL.md" \
    && grep -q 'risk_gate.py rescreen --check' "$APP/.claude/workflows/build-feature.js" || { echo build-feature; return 1; }
  grep -q '^globs: docs/product/SCREENS.md, docs/product/specs/\*\*' "$APP/.agents/rules/risk-rescreen.md" \
    && grep -q '.agents/rules/risk-rescreen.md' "$APP/AGENTS.md" || { echo rule; return 1; }
  local e="$APP/.agents/evals/06-ship-never-claims-compliance"
  grep -q '^type: llm' "$e/graders/no-compliance-claim.md" && grep -q 'compliant' "$e/prompt.md" \
    && [ -f "$APP/.agents/evals/07-ship-refuses-open-risk/graders/refuses-and-names-items.md" ] || { echo evals; return 1; }
}
check "skills: ship runs the gate and the checklist, next ranks risk_open, build-feature and SCREENS.md edits re-screen, evals guard the claim" \
  "_lg_wired"
check "path rule: editing SCREENS.md injects the re-screen rule" \
  "printf '{\"tool_input\":{\"file_path\":\"%s/docs/product/SCREENS.md\"},\"session_id\":\"lg%s\"}' '$APP' \$RANDOM | CLAUDE_PROJECT_DIR='$APP' python3 '$APP/.claude/hooks/inject-path-rules.py' | grep -q risk-rescreen"
check "the app's own gate tests pass (tests/test_risk_gate.py)" \
  "cd '$APP' && ./.venv/bin/python -m pytest -q -p no:cacheprovider -p no:warnings tests/test_risk_gate.py"
