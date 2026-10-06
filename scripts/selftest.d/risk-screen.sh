# The risk screen (docs/specs/trust-by-default): sourced by selftest.sh with $KIT, $APP,
# $T and the check/refuses helpers. Shape screens the idea against sensitive categories
# before anything is built; a keyword backstop is the floor under the agent's judgment,
# check_intake.py validates the brief's `risk` block, and RISK.md is generated from it.
# Each guard passes on the kit and fails on a planted violation, naming the rule.
RS_PY="$KIT/scripts/risk_screen.py"
RS_DATA="$KIT/scripts/risk/categories.json"
RS_FIX="$KIT/../../scripts/fixtures/risk-brief.json"
RS_SPEC="$KIT/../../docs/specs/trust-by-default/REQUIREMENTS.md"

# categories.json: the contract's ids and keys, 1-3 questions each, official regime links.
check "risk data: categories.json passes its own lint (contract ids, packs, questions, official links)" \
  "python3 '$RS_PY' lint"
_rs_data() {  # <python edit of d (the data dict)> -> lint the planted copy
  python3 -c "import json;d=json.load(open('$RS_DATA'));$1;json.dump(d,open('$T/rs-data.json','w'))" || return 1
  python3 "$RS_PY" lint "$T/rs-data.json"
}
refuses "risk data catches: a regime linked to an unofficial source" \
  "_rs_data \"d['categories'][0]['regimes'][0]['link']='https://example.com/coppa'\"" \
  "not an official source in official_domains"
refuses "risk data catches: a category with no must-answer questions" \
  "_rs_data \"d['categories'][1]['questions']=[]\"" "location: 0 questions"
refuses "risk data catches: a guardrail pack the contract doesn't have" \
  "_rs_data \"d['categories'][7]['guardrails']=['spyware']\"" "guardrail pack 'spyware' is not one of"
refuses "risk data catches: a dropped contract category" \
  "_rs_data \"d['categories'].pop()\"" "are not the contract's"

# The ids in categories.json are the spec's (one vocabulary for four workstreams).
_rs_spec_ids() {  # <spec file>
  python3 - "$1" "$RS_DATA" <<'PY'
import json, re, sys
spec, data = open(sys.argv[1]).read(), json.load(open(sys.argv[2]))
cats = re.search(r"## Categories \(ids are the contract\)\n\n(.*?)\n\nTiers:", spec, re.S).group(1)
packs = re.search(r"Pack ids \(match `guardrails` in categories.json\): (.*?)\. Enabled", spec, re.S).group(1)
want = re.findall(r"`([a-z_]+)`", cats)
assert want == [c["id"] for c in data["categories"]], f"spec categories {want}"
assert re.findall(r"`([a-z_]+)`", packs) == list(data["packs"]), f"spec packs {packs}"
PY
}
check "risk data: the category and pack ids are the spec's, in order" "_rs_spec_ids '$RS_SPEC'"
sed 's/`ai_decisions` (automated/`automated_decisions` (automated/' "$RS_SPEC" > "$T/rs-spec.md"
refuses "risk data catches: the spec and categories.json naming a category differently" \
  "_rs_spec_ids '$T/rs-spec.md'" "spec categories"

# The screen on the three acceptance ideas, and two that must stay calm.
_rs_screen() {  # <idea> <python assertion on r (the screen result)>
  python3 "$RS_PY" screen --idea "$1" > "$T/rs-screen.json" || return 1
  python3 -c "import json;r=json.load(open('$T/rs-screen.json'));ids=[c['id'] for c in r['categories']];covers=[q for g in r['ask_now'] for q in g['covers']];assert $2, (r['tier'], ids, covers, r['packs'])"
}
check "risk screen: a kid-location tracker is high, minors + location, with the consent and visibility questions and both packs" \
  "_rs_screen 'a map so parents can see where their kids are after school' \
   \"r['tier']=='high' and ids==['minors','location'] and {'minors.consent','location.consent','location.visibility'}<=set(covers) and {'minors','location'}<=set(r['packs']) and sorted(r['needs_ack'])==['location','minors'] and any('non-custodial' in a['text'] for a in r['abuse_prompts'])\""
check "risk screen: a to-do app is standard with zero extra questions" \
  "_rs_screen 'a to-do app for people juggling work and home; today I use sticky notes' \"r['tier']=='standard' and not ids and not covers and not r['later'] and r['packs']==['baseline']\""
check "risk screen: a covert partner tracker is stop, and the consented version is offered" \
  "_rs_screen 'an app to secretly see where my girlfriend is, without her knowing' \
   \"r['tier']=='stop' and r['stop'][0]['id']=='covert_monitoring' and 'both people' in r['stop'][0]['reframe'] and 'surveillance' in ids\""
check "risk screen: consented location sharing between partners is high, never stop (combinations cap at high)" \
  "_rs_screen 'share my location with my wife so we know when the other gets home' \"r['tier']=='high' and not r['stop'] and 'surveillance' in ids\""
check "risk screen: ordinary words stay standard (a group chat mention, a habit check-in, a kids-free packing list)" \
  "_rs_screen 'a shared grocery list for housemates; things get lost in the group chat' \"r['tier']=='standard'\" \
   && _rs_screen 'a habit tracker with daily check-ins and streaks' \"r['tier']=='standard'\" \
   && _rs_screen 'a packing list app for weekend campers' \"r['tier']=='standard'\""

# The brief's risk block: a complete high-tier brief passes check_intake.py; each plant
# fails on its rule. _rs_brief edits b (the fixture brief) and runs check_intake.
_rs_brief() {  # <python edit of b>
  python3 -c "import json;b=json.load(open('$RS_FIX'));$1;json.dump(b,open('$T/rs-brief.json','w'))" || return 1
  python3 "$KIT/scripts/check_intake.py" brief "$T/rs-brief.json"
}
check "risk brief: a complete high-tier brief (kid tracker fixture) passes check_intake.py" "_rs_brief 'pass'"
refuses "risk brief: the backstop catches an under-classified idea (kid tracker recorded as standard)" \
  "_rs_brief \"b['risk'].update(tier='standard', categories=[], questions=[], abuse_cases=[], accepted=[])\"" \
  "risk: tier standard is lower than the backstop's high (minors, location)"
refuses "risk brief: dropping a category the backstop found fails" \
  "_rs_brief \"b['risk']['categories'].pop()\"" "the backstop finds \`location\`"
refuses "risk brief: a missing owner acknowledgment for a high-tier category fails" \
  "_rs_brief \"b['risk']['accepted'] = b['risk']['accepted'][1:]\"" "no owner acknowledgment for \`minors\`"
refuses "risk brief: an acknowledgment by someone other than the owner doesn't count" \
  "_rs_brief \"b['risk']['accepted'][1]['by'] = 'agent'\"" "no owner acknowledgment for \`location\`"
refuses "risk brief: an elevated or high idea with no abuse case fails" \
  "_rs_brief \"b['risk']['abuse_cases'] = []\"" "tier high needs at least one abuse case"
refuses "risk brief: an architectural question deferred past shape fails" \
  "_rs_brief \"b['risk']['questions'][3]['status'] = 'deferred'\"" \
  "risk.questions \`location.visibility\`: it changes the architecture"
refuses "risk brief: a must-answer question left out fails" \
  "_rs_brief \"b['risk']['questions'].pop(0)\"" "\`minors.age\` (minors) is not in risk.questions"
refuses "risk brief: a risk question missing from the decisions ledger fails" \
  "_rs_brief \"b['decisions'] = [d for d in b['decisions'] if d['id'] != 'location.retention']\"" \
  "risk.questions \`location.retention\`: no \`decisions\` entry"
refuses "risk brief: tier stop never passes (the kit doesn't build the covert core)" \
  "_rs_brief \"b['risk']['tier'] = 'stop'\"" "risk: tier stop: the kit doesn't build"
refuses "risk brief: a stop pattern in the idea with nothing declined fails" \
  "_rs_brief \"b['app']['one_liner'] += ', secretly'\"" "the backstop finds a stop pattern"
check "risk brief: the same idea passes once the covert part is declined and the reframe recorded" \
  "_rs_brief \"b['app']['one_liner'] += ', secretly'; b['risk']['declined'] = [dict(item='hidden tracking', why='covert core', reframe='the child sees who can see them')]\""
refuses "risk brief: a brief with no risk block fails" "_rs_brief \"del b['risk']\"" "brief: no \`risk\` block"
check "risk brief: risk questions count toward the 7 (one decision covers several via \`decision\`)" \
  "python3 -c \"import json;b=json.load(open('$RS_FIX'));assert sum(1 for q in b['risk']['questions'] if q.get('decision')=='risk.consent')==2\" \
   && grep -q 'count toward the 7-question budget' '$KIT/skills/shape/SKILL.md'"

# RISK.md: every section, prose outside the markers survives, --check catches a hand edit.
_rs_md() {
  local f="$T/rs-RISK.md" h
  rm -f "$f"
  python3 "$RS_PY" render "$RS_FIX" --out "$f" >/dev/null || return 1
  for h in 'Summary' 'Who could be harmed and how' 'Guardrails built in' 'Open questions' \
           'Accepted risks' 'Regimes that may apply' 'Not legal advice'; do
    grep -qx "## $h" "$f" || { echo "RISK.md lost: $h"; return 1; }
  done
  grep -q 'non-custodial parent' "$f" && grep -q '(`minors`)' "$f" && grep -q '(`location`)' "$f" \
    && grep -q '`location.retention` (location, ask at first-feature)' "$f" && grep -q 'not legal advice' "$f" \
    || { echo "RISK.md content"; return 1; }
  printf '\nOur own note: talk to a lawyer in March.\n' >> "$f"
  python3 "$RS_PY" render "$RS_FIX" --out "$f" >/dev/null && grep -q 'talk to a lawyer in March' "$f" \
    || { echo "prose outside the markers was lost"; return 1; }
  python3 "$RS_PY" render "$RS_FIX" --out "$f" --check
}
check "RISK.md: all seven sections, the abuse case, both packs and the open questions; prose kept; --check passes" "_rs_md"
_rs_md_drift() {
  local f="$T/rs-RISK-drift.md"
  python3 "$RS_PY" render "$RS_FIX" --out "$f" >/dev/null || return 1
  sed -i 's/^None open\.$/x/; s/^- `minors.contact`.*$/- nothing to see here/' "$f"
  python3 "$RS_PY" render "$RS_FIX" --out "$f" --check
}
refuses "RISK.md catches: a hand-edited generated block" "_rs_md_drift" "generated block 'open' differs"

# Shape runs the screen, asks only what changes the architecture, and owns the stop policy.
_rs_shape() {  # <shape SKILL.md>
  local f="$1"
  grep -q 'risk_screen.py" screen --brief design/brief.json' "$f" || { echo "shape: never runs the risk screen"; return 1; }
  grep -q 'risk_screen.py" render design/brief.json' "$f" || { echo "shape: never renders RISK.md"; return 1; }
  grep -q '`risk-reviewer`' "$f" && grep -q 'zero extra questions' "$f" && grep -q 'decline only the covert or non-consensual core' "$f" \
    && grep -q 'risk.accepted' "$f" && grep -q 'risk.declined' "$f" || { echo "shape: risk policy incomplete"; return 1; }
}
check "shape: runs the risk screen, stays light for standard ideas, records acknowledgments, declines only the covert core" \
  "_rs_shape '$KIT/skills/shape/SKILL.md'"
grep -v 'risk_screen.py" screen --brief' "$KIT/skills/shape/SKILL.md" > "$T/rs-shape.md"
refuses "shape: a skill that stops running the risk screen fails" "_rs_shape '$T/rs-shape.md'" "shape: never runs the risk screen"

# The risk-reviewer team agent: registered with the team, read-only, not legal advice.
check "risk-reviewer: on the team (advisor delegates to it), tools declared without Write, says 'may apply' and recommends a lawyer" \
  "grep -q '^tools: .*WebSearch' '$KIT/agents/risk-reviewer.md' && ! grep -q '^tools: .*Write' '$KIT/agents/risk-reviewer.md' \
   && grep -q 'may apply' '$KIT/agents/risk-reviewer.md' && grep -q 'lawyer' '$KIT/agents/risk-reviewer.md' \
   && grep -q 'risk_screen.py\" screen' '$KIT/agents/risk-reviewer.md' && grep -q '\`risk-reviewer\`' '$KIT/agents/product-advisor.md' \
   && grep -q 'risk-reviewer' '$KIT/docs/COST.md'"

# Evals: the three acceptance ideas each have a case.
check "evals: kid tracker (high), to-do (standard) and covert tracker (stop + reframe) have cases" \
  "grep -q 'non-custodial parent' '$KIT'/evals/*-kid-tracker-is-high/graders/*.md \
   && grep -q '\"standard\"' '$KIT'/evals/*-todo-stays-standard/graders/risk-tier-standard.md \
   && grep -q 'consented version' '$KIT'/evals/*-covert-tracker-stops-and-reframes/graders/*.md"
