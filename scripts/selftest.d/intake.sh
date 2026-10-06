# Intake and the decision ledger: sourced by selftest.sh with $KIT, $APP, $T and the
# check/refuses helpers. Day 0 asks only what's expensive to change (at most 7
# questions), states the rest as defaults or defers it to a named phase, and records
# every call in design/brief.json -> decisions. Each guard here passes on the kit and
# fails on a planted violation, naming the rule that fired.
IN_PY="$KIT/scripts/check_intake.py"
IN_SHAPE="$KIT/skills/shape/SKILL.md"

# Shape caps day 0, lists the day-0 set and defers the rest to named phases.
_in_shape() {  # <shape SKILL.md>
  local f="$1" k
  grep -q 'at most 7 questions in total' "$f" || { echo "shape: no question cap"; return 1; }
  grep -q "I'm assuming" "$f" || { echo "shape: no stated defaults"; return 1; }
  for k in '**Who, the moment, how often**' "**The problem and today's alternative**" '**The payoff**' \
           '**Social shape**' '**Distribution**' '**Money model**' '**Sensitive data**'; do
    grep -qF -- "$k" "$f" || { echo "shape: day-0 set lost $k"; return 1; }
  done
  for k in prototype scaffold first-feature pre-launch post-launch; do
    grep -q "^- \`$k\`: " "$f" || { echo "shape: defers nothing to $k"; return 1; }
  done
  grep -q 'check_intake.py" brief design/brief.json' "$f" || { echo "shape: never validates the brief"; return 1; }
}
check "shape: caps day 0 at 7 questions, lists the day-0 set, defers the rest to named phases" "_in_shape '$IN_SHAPE'"
sed '/at most 7 questions in total/d' "$IN_SHAPE" > "$T/in-shape-nocap.md"
refuses "shape: a skill that drops the question cap fails" "_in_shape '$T/in-shape-nocap.md'" "shape: no question cap"
grep -v '^- `pre-launch`: ' "$IN_SHAPE" > "$T/in-shape-nodefer.md"
refuses "shape: a skill that stops deferring to pre-launch fails" "_in_shape '$T/in-shape-nodefer.md'" "shape: defers nothing to pre-launch"

# COST.md's brief schema carries the ledger and the day-0 sections, and its phase list is
# the one check_intake.py and the app's next/signals.py use (one vocabulary, three readers).
_in_schema() {  # <COST.md>
  local k
  for k in '"decisions"' '"ask_at"' '"status"' '"payoff"' '"social"' '"distribution"' '"context"' '"money"'; do
    grep -q "$k" "$1" || { echo "brief schema lost $k"; return 1; }
  done
  python3 - "$1" "$IN_PY" "$APP/.agents/skills/next/signals.py" <<'PY'
import importlib.util, re, sys
def load(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
doc = open(sys.argv[1]).read()
line = re.search(r"`ask_at`: when it gets settled: (.*?`)\.", doc, re.S).group(1)
phases = re.findall(r"`([a-z-]+)`", line)
ci, sig = load(sys.argv[2], "ci"), load(sys.argv[3], "sig")
assert phases == list(ci.PHASES) == sig.DECISION_PHASES, (phases, ci.PHASES, sig.DECISION_PHASES)
assert re.search(r"`asked`.*`default`.*`deferred`", doc, re.S) and list(ci.STATUSES) == ["asked", "default", "deferred"]
# money.model and social.shape use appbox.yaml's words (the interview's Output 1), not a second set.
iv = open(sys.argv[1].replace("docs/COST.md", "skills/interview/SKILL.md")).read()
assert re.search(r"monetisation: ([a-z0-9_|]+)", iv).group(1).split("|") == list(ci.MONEY), ci.MONEY
assert re.search(r"  social: ([a-z_|]+)", iv).group(1).split("|") == list(ci.SOCIAL), ci.SOCIAL
PY
}
check "COST.md: the brief schema has decisions + the day-0 keys; one phase list across COST.md, check_intake.py and signals.py" "_in_schema '$KIT/docs/COST.md'"
sed 's/"payoff"/"pay_off"/' "$KIT/docs/COST.md" > "$T/in-cost.md"
refuses "COST.md: a schema without payoff fails" "_in_schema '$T/in-cost.md'" 'brief schema lost "payoff"'

# The brief validator: a good brief passes; each planted violation fails on its rule.
_in_brief() {  # <python edit of b (the brief dict)> -> writes $T/in-brief.json
  python3 - "$T/in-brief.json" "$1" <<'PY'
import json, sys
b = {
  "app": {"name": "Sample List", "one_liner": "Housemates share one grocery list"},
  "users": [{"who": "people who live together", "moment": "noticing we're out of oat milk", "pain": "things get lost in the group chat"}],
  "context": {"frequency": "a few times a week", "where": "in the kitchen, at the shop"},
  "core_loop": {"trigger": "out of something", "action": "add it", "feedback": "housemates see it", "return": "the list gets done"},
  "payoff": {"first_session": "relief: it's on the list and everyone can see it", "moment": "the list ticking to done"},
  "social": {"shape": "shared", "cold_start": "useful as a personal list until a housemate joins"},
  "distribution": {"first_100": "invite links in house group chats", "channels": ["invite", "share"]},
  "money": {"model": "free"},
  "decisions": [
    {"id": "social", "question": "Who else is in it?", "answer": "shared with housemates", "status": "asked", "ask_at": "shape", "why": "data model and invites"},
    {"id": "platforms", "question": "Which phones?", "answer": "iPhone and Android", "status": "default", "ask_at": "shape", "why": "build profiles"},
    {"id": "name", "question": "Final name and bundle ID?", "answer": None, "status": "deferred", "ask_at": "scaffold", "why": "the bundle ID is permanent"},
    {"id": "pricing", "question": "Price and paywall?", "answer": None, "status": "deferred", "ask_at": "pre-launch", "why": "cheap to change, best set with usage"}
  ],
  "risk": {"tier": "standard", "categories": [], "questions": [], "abuse_cases": [], "accepted": [], "screened_at": "shape", "declined": []},
  "open_questions": []
}
exec(sys.argv[2])
json.dump(b, open(sys.argv[1], "w"))
PY
  python3 "$IN_PY" brief "$T/in-brief.json"
}
check "brief: a brief with the ledger and the day-0 sections passes check_intake.py" "_in_brief 'pass'"
refuses "brief: a planted brief with no decisions ledger fails" "_in_brief \"del b['decisions']\"" 'no `decisions` ledger'
refuses "brief: a brief missing a day-0 section (payoff) fails" "_in_brief \"del b['payoff']\"" 'no `payoff` section'
refuses "brief: a decision deferred to shape (which is now) fails" "_in_brief \"b['decisions'][2]['ask_at'] = 'shape'\"" 'name: deferred to shape, which is now'
refuses "brief: an unknown phase or status fails" "_in_brief \"b['decisions'][3]['ask_at'] = 'someday'\"" "pricing: ask_at 'someday' is not one of"
refuses "brief: a default with no stated answer fails" "_in_brief \"b['decisions'][1]['answer'] = None\"" 'platforms: status default needs an answer'
refuses "brief: an unknown social shape fails" "_in_brief \"b['social']['shape'] = 'marketplace'\"" "social.shape 'marketplace' is not one of"
refuses "brief: 8 questions asked at shape breaks the 7 cap" \
  "_in_brief \"b['decisions'] += [dict(id=f'q{i}', question='?', answer='a', status='asked', ask_at='shape', why='w') for i in range(7)]\"" \
  'decisions: 8 asked at shape, the cap is 7'

# The ledger travels: shape writes design/brief.json in the project folder that becomes
# the repo, and the renderer never overwrites it (--force or not).
_in_travels() {
  local d="$T/in-travel"
  rm -rf "$d" && mkdir -p "$d/design" && echo '{"decisions": ["mine"]}' > "$d/design/brief.json"
  [ ! -e "$KIT/template/design/brief.json" ] || { echo "the template ships a brief.json"; return 1; }
  python3 "$KIT/scripts/render.py" --target "$d" --name T --slug in-travel --bundle-id com.t.travel --owner t --force >/dev/null || return 1
  grep -q '"mine"' "$d/design/brief.json" && grep -q '"design/brief.json"' "$KIT/scripts/render.py"
}
check "brief: design/brief.json travels into the app and render --force never overwrites it" "_in_travels"

# next/signals.py surfaces a deferred decision once its phase has arrived, and only then.
_in_signals() {  # <progress lines> <expected due ids, comma-separated> [expected --line text]
  local d="$T/in-sig" got
  rm -rf "$d" && mkdir -p "$d/.agents/skills/next" "$d/design"
  cp "$APP/.agents/skills/next/signals.py" "$d/.agents/skills/next/"
  printf 'app:\n  name: "S"\nprogress:\n%b' "$1" > "$d/appbox.yaml"
  cat > "$d/design/brief.json" <<'JSON'
{"decisions": [
  {"id": "pricing", "question": "Price and paywall?", "answer": null, "status": "deferred", "ask_at": "pre-launch", "why": "w"},
  {"id": "nudges", "question": "Nudge policy?", "answer": null, "status": "deferred", "ask_at": "first-feature", "why": "w"},
  {"id": "tone", "question": "Copy tone?", "answer": "calm", "status": "asked", "ask_at": "prototype", "why": "w"},
  {"id": "reviews", "question": "Keep the review prompt?", "answer": null, "status": "deferred", "ask_at": "post-launch", "why": "w"}
]}
JSON
  got=$(cd "$d" && CLAUDE_PROJECT_DIR="$d" python3 .agents/skills/next/signals.py \
    | python3 -c "import json,sys; print(','.join(x['id'] for x in json.load(sys.stdin)['decisions_due']))") || return 1
  [ "$got" = "$2" ] || { echo "decisions_due: got '$got', expected '$2'"; return 1; }
  [ -z "${3:-}" ] || (cd "$d" && CLAUDE_PROJECT_DIR="$d" python3 .agents/skills/next/signals.py --line) | grep -qF -- "$3"
}
_IN_SETUP='  preflight: done\n  interview: done\n  validate: done\n  design: done\n  accounts: done\n  scaffold: done\n  provision: done\n  harness: done\n  verify: done\n'
check "next: an overdue first-feature decision is surfaced; pre-launch waits; answered ones never show" \
  "_in_signals '$_IN_SETUP' 'nudges'"
check "next: once setup is complete, pre-launch decisions are due too, and the session line says so" \
  "_in_signals '${_IN_SETUP}  first_feature: done\n' 'nudges,pricing' '2 product decision(s) are due, starting with \`nudges\`'"
refuses "next: before the phase arrives nothing is due (negative control for the fixture)" \
  "_in_signals '  preflight: done\n  interview: done\n' 'nudges'" "decisions_due: got '', expected 'nudges'"

# The phases that own deferred decisions actually ask them.
_in_phases_ask() {
  grep -q 'ask_at: prototype' "$KIT/skills/prototype/SKILL.md" || { echo prototype; return 1; }
  grep -q 'ask_at: scaffold' "$KIT/skills/scaffold/SKILL.md" && grep -q '^## 0. Decisions due now' "$KIT/skills/scaffold/SKILL.md" || { echo scaffold; return 1; }
  grep -q 'ask_at: first-feature' "$KIT/skills/first-feature/SKILL.md" || { echo first-feature; return 1; }
  grep -q 'first-feature' "$APP/.agents/skills/feature-discovery/SKILL.md" && grep -q 'docs/DEFAULTS.md' "$APP/.agents/skills/feature-discovery/SKILL.md" || { echo feature-discovery; return 1; }
  grep -q 'ask_at: pre-launch' "$APP/.agents/skills/ship/SKILL.md" && grep -q 'Price and paywall placement' "$APP/.agents/skills/ship/SKILL.md" \
    && grep -q 'Support channel' "$APP/.agents/skills/ship/SKILL.md" || { echo ship; return 1; }
  grep -q 'decisions_due' "$APP/.agents/skills/next/SKILL.md" || { echo next; return 1; }
  grep -q 'docs/DEFAULTS.md' "$APP/.agents/skills/build-feature/SKILL.md" || { echo build-feature; return 1; }
}
check "phases ask their deferred decisions: prototype, scaffold, first feature, ship (pre-launch), next" "_in_phases_ask"

# The interview's count matches its numbered questions (shape draws from them).
_in_interview_count() {
  local f="$KIT/skills/interview/SKILL.md" n claimed
  n=$(sed -n '/^## Round 1/,/^## When each question/p' "$f" | grep -cE '^[0-9]+\. \*\*')
  claimed=$(grep -oE 'about [0-9]+ questions' "$f" | grep -oE '[0-9]+')
  [ "$n" = "$claimed" ] || { echo "interview says about $claimed questions, numbers $n"; return 1; }
  grep -q '^## When each question is asked (the decision ledger)' "$f" && grep -q '^## Payoff' "$f" \
    && grep -q '^## Distribution' "$f" && grep -q '^## Decisions still to make' "$f" && grep -q '  payoff: ' "$f"
}
check "interview: its question count is true, it says when each is asked, and Output 1/2 carry payoff, social, distribution" "_in_interview_count"

# DEFAULTS.md: every row names real files (or says it's on the roadmap), in the kit
# against the template and in a rendered app against itself.
check "defaults: every DEFAULTS.md row names files that exist in the template" \
  "python3 '$IN_PY' defaults '$KIT/docs/DEFAULTS.md' --root '$KIT/template'"
check "defaults: DEFAULTS.md travels to the app's docs/ and its paths resolve there" \
  "cmp -s '$KIT/docs/DEFAULTS.md' '$APP/docs/DEFAULTS.md' && python3 '$IN_PY' defaults '$APP/docs/DEFAULTS.md' --root '$APP'"
{ cat "$KIT/docs/DEFAULTS.md"; echo '| Planted | A claim | `mobile/lib/not-a-real-file.ts` |'; } > "$T/in-defaults-path.md"
refuses "defaults: a row naming a file that doesn't exist fails" \
  "python3 '$IN_PY' defaults '$T/in-defaults-path.md' --root '$KIT/template'" 'Planted: `mobile/lib/not-a-real-file.ts` doesn'"'"'t exist'
{ cat "$KIT/docs/DEFAULTS.md"; echo '| Planted | Claims to exist, names nothing | Built in. |'; } > "$T/in-defaults-vague.md"
refuses "defaults: a row that names no file and isn't on the roadmap fails" \
  "python3 '$IN_PY' defaults '$T/in-defaults-vague.md' --root '$KIT/template'" "Planted: names no file and doesn't say it's on the roadmap"
