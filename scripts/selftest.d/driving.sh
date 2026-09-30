# v0.4 "self-driving" checks. Sourced by scripts/selftest.sh with $KIT, $APP (rendered
# app, a git repo on feat/selftest), $T and the check/refuses helpers; cwd is $APP.
# Fast and offline: frontmatter, eval-case shape, generated Codex mapping, the next
# signal script, the progress view and the workflow scripts' syntax.

_front() {  # _front <file> <key> -> value of a top-level frontmatter key
  awk -v k="$2" 'NR==1&&$0!="---"{exit} NR>1&&$0=="---"{exit} NR>1{ if (index($0, k": ")==1) { sub(k": *",""); print; exit } }' "$1"
}

agents_routed() {
  local f m e bad=0
  for f in "$APP"/.agents/agents/*.md; do
    m=$(_front "$f" model); e=$(_front "$f" effort)
    case "$m" in opus|sonnet|haiku|fable|inherit) ;; *) echo "bad model '$m' in $f"; bad=1 ;; esac
    case "$e" in low|medium|high|max) ;; *) echo "bad effort '$e' in $f"; bad=1 ;; esac
  done
  [ "$bad" = 0 ] && [ -f "$APP/.agents/agents/chair.md" ] && [ "$(_front "$APP/.agents/agents/chair.md" model)" = fable ]
}

skills_named() {
  local f bad=0
  for f in "$APP"/.agents/skills/*/SKILL.md "$KIT"/skills/*/SKILL.md; do
    [ -n "$(_front "$f" name)" ] && [ -n "$(_front "$f" description)" ] || { echo "missing name/description: $f"; bad=1; }
    [ "$(_front "$f" name)" = "$(basename "$(dirname "$f")")" ] || { echo "name != folder: $f"; bad=1; }
  done
  [ "$bad" = 0 ]
}

eval_cases_shaped() {
  local d g n bad=0 suites=0
  for suite in "$KIT/evals" "$APP/.agents/evals"; do
    [ -d "$suite" ] || { echo "no suite $suite"; return 1; }
    suites=$((suites+1))
    for d in "$suite"/*/; do
      [ "$(basename "$d")" = results ] && continue
      [ -f "$d/prompt.md" ] || { echo "no prompt.md in $d"; bad=1; continue; }
      n=0
      for g in "$d"/graders/*.md; do
        [ -f "$g" ] || continue
        grep -qE '^type: (regex|tool_order|tool_used|file_exists|llm|baseline)$' "$g" || { echo "grader without valid type: $g"; bad=1; }
        n=$((n+1))
      done
      [ "$n" -ge 1 ] || { echo "no graders in $d"; bad=1; }
    done
    # every suite keeps at least one should-NOT-fire case
    grep -rlq 'max: 0' "$suite" || { echo "no negative case in $suite"; bad=1; }
  done
  [ "$bad" = 0 ] && [ "$suites" = 2 ]
}

codex_routed() {
  python3 - "$APP" <<'PY'
import sys, glob, tomllib, os
app = sys.argv[1]
tomls = sorted(glob.glob(f"{app}/.codex/agents/*.toml"))
mds = sorted(glob.glob(f"{app}/.agents/agents/*.md"))
assert len(tomls) == len(mds), (len(tomls), len(mds))
for f in tomls:
    d = tomllib.load(open(f, "rb"))
    assert d["name"] and d["description"] and d["developer_instructions"], f
    assert d.get("model_reasoning_effort") in {"low", "medium", "high", "xhigh"}, f
    assert "model" not in d, f"{f}: pinned model without codex_model"
    assert "# Claude tier: model=" in open(f).read(), f
chair = tomllib.load(open(f"{app}/.codex/agents/chair.toml", "rb"))
assert chair["model_reasoning_effort"] == "high"
tri = tomllib.load(open(f"{app}/.codex/agents/triage.toml", "rb"))
assert tri["model_reasoning_effort"] == "low"
for s in ("ship", "routines"):
    y = open(f"{app}/.agents/skills/{s}/agents/openai.yaml").read()
    assert "allow_implicit_invocation: false" in y, s
assert not os.path.exists(f"{app}/.agents/skills/next/agents/openai.yaml")
PY
}

codex_model_pin() {  # an explicit codex_model: pin reaches the TOML
  python3 -c "import sys; sys.path.insert(0, '$KIT/scripts'); import render; t = render.codex_agent_toml('---\nname: x\ndescription: y\nmodel: haiku\ncodex_model: some-fast-model\neffort: max\n---\nbody'); assert 'model = \"some-fast-model\"' in t and 'model_reasoning_effort = \"xhigh\"' in t, t"
}

next_signals() {
  local out
  out=$(python3 "$APP/.agents/skills/next/signals.py") || return 1
  echo "$out" | python3 -c "import json,sys; d=json.load(sys.stdin); assert {'setup_pending','branch','overdue_rituals','tracker'} <= d.keys(), d"
  python3 "$APP/.agents/skills/next/signals.py" --line | grep -q '^- Next: '
}

next_sees_setup() {  # an unfinished appbox.yaml makes resuming setup the top line
  printf 'app:\n  name: "P"\nprogress:\n  preflight: done\n  interview: done\n' > "$APP/appbox.yaml"
  python3 "$APP/.agents/skills/next/signals.py" --line | grep -q 'setup phase `design`'
  local rc=$?; rm -f "$APP/appbox.yaml"; return $rc
}

session_start_line() {
  local out
  out=$(echo '{}' | CLAUDE_PROJECT_DIR="$APP" bash "$APP/.claude/hooks/session-start.sh") || return 1
  echo "$out" | grep -q '^- Next: '
}

progress_renders() {
  printf 'app:\n  name: "Penny Jar"   # comment\nprogress:\n  preflight: done\n  interview: done\n  design: skipped\n' > "$T/appbox-sample.yaml"
  local out; out=$(python3 "$KIT/scripts/progress.py" "$T/appbox-sample.yaml") || return 1
  echo "$out" | grep -q '^Penny Jar: setup progress' \
    && echo "$out" | grep -q '\[x\] 2. Design.*(skipped)' \
    && echo "$out" | grep -q '\[>\] 3. Accounts' \
    && echo "$out" | grep -q '3/9 phases done' \
    && python3 "$KIT/scripts/progress.py" "$T/nope.yaml" | grep -q 'Phase 0'
}

workflows_parse() {
  command -v node >/dev/null || { echo "node missing"; return 1; }
  local f
  for f in "$APP"/.claude/workflows/*.js; do
    head -1 "$f" | grep -q '^export const meta = {' || { echo "no meta header: $f"; return 1; }
    node -e '
      const fs = require("fs"); const src = fs.readFileSync(process.argv[1], "utf8");
      const m = src.match(/^export const meta = (\{[\s\S]*?\n\})\n/);
      if (!m) throw new Error("meta block not found");
      const meta = Function("return (" + m[1] + ")")();
      if (!meta.name || !meta.description) throw new Error("meta needs name + description");
      if (/Date\.now\(|Math\.random\(|new Date\(\)/.test(src)) throw new Error("non-resumable call");
      const body = src.replace(/^export const meta/, "const meta");
      const AsyncFn = Object.getPrototypeOf(async function () {}).constructor;
      new AsyncFn("args", "agent", "parallel", "pipeline", "phase", "log", "workflow", "budget", body);
    ' "$f" || return 1
  done
}

template_clean() {  # no Forge/owner leakage into the generated harness
  ! grep -rniE 'kyle|forge|PUL-' "$KIT/template/.agents" "$KIT/template/.claude" "$KIT/template/AGENTS.md"
}

check "every agent role has a valid model + effort (chair on fable)" agents_routed
check "every skill (kit + template) has name + description matching its folder" skills_named
check "every eval case has prompt.md + >=1 typed grader, each suite has a negative case" eval_cases_shaped
check "Codex TOML carries effort mapping + tier comment; explicit-only skills get openai.yaml" codex_routed
check "codex_model: pin and max->xhigh reach the TOML" codex_model_pin
check "next/signals.py emits JSON and a one-line nudge" next_signals
check "next line points at unfinished setup first" next_sees_setup
check "SessionStart hook prints the next-action line" session_start_line
check "progress.py renders a sample appbox.yaml checklist" progress_renders
check "workflow scripts: pure meta literal, resumable, parse as async bodies" workflows_parse
check "AGENTS.md stays lean (<= 150 lines)" "[ \$(wc -l < '$APP/AGENTS.md') -le 150 ]"
check "no owner/Forge references in the template harness" template_clean
