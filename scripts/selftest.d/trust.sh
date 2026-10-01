# v0.3 "trust" area checks, sourced by scripts/selftest.sh with $KIT, $APP (the rendered
# app, a git repo on a feature branch, cwd), $T and the check/refuses helpers.
#
# Proves the generated repo's CI guards pass on a pristine render AND that each one
# fails on a planted violation, for code and for non-code artifacts (skills, agent
# roles, memory, AGENTS.md, workflows, migrations). Every plant is reverted.
#
# Optional, when available: actionlint / zizmor on PATH; and a throwaway Postgres with
# pgTAP at $APPBOX_SELFTEST_DATABASE_URL, which runs the full DB gate (kit CI sets it).

PY="$APP/.venv/bin/python"
PT="$PY -m pytest -q -p no:cacheprovider -p no:warnings"

# fails_with NAME CMD NEEDLE: CMD must fail AND its output must name the rule. A plant
# that fails for some unrelated reason (an import error) would otherwise read as a pass.
fails_with() {
  local out
  if out="$(eval "$2" 2>&1)"; then bad "$1 (still green)"; return; fi
  if grep -qF -- "$3" <<<"$out"; then ok "$1"; else bad "$1 (failed, but not on: $3)"; fi
}
plant() { cp "$1" "$T/plant.bak"; }
unplant() { cp "$T/plant.bak" "$1"; }

check "harness lint green on a pristine render" "$PT tests/harness"
check "wire contract, scoping guard, migration guards green" \
  "$PT tests/test_wire_contract.py tests/test_scoping_static.py tests/test_migrations_static.py"
check "coverage floor met (pytest --cov)" "$PT --cov"
check "pyright clean (basic)" "PATH='$APP/.venv/bin':\$PATH pyright"
check "ruff clean on tests + scripts too" "'$APP/.venv/bin/ruff' check backend tests scripts"

mkdir -p .agents/skills/planted
printf -- '---\nname: planted\n---\nDo things.\n' > .agents/skills/planted/SKILL.md
fails_with "skill lint catches a skill with no description" \
  "$PT tests/harness/test_skills_lint.py" "description\` missing"
rm -rf .agents/skills/planted

WF=.github/workflows/claude-review.yml
plant "$WF"
sed -i.x 's/claude_args: "--max-turns 120"/claude_args: "--max-turns 120 --allowedTools Bash,Read"/' "$WF" && rm -f "$WF.x"
fails_with "workflow lint catches a planted --allowedTools" \
  "$PT tests/harness/test_workflow_lint.py" "sets --allowedTools"
unplant "$WF"

plant .github/workflows/ci.yml
printf '      - run: pytest || true\n' >> .github/workflows/ci.yml
fails_with "guard-wiring lint catches a guard made advisory with || true" \
  "$PT tests/harness/test_guards_wired.py" "cannot fail the build"
unplant .github/workflows/ci.yml

ROLE=.agents/agents/growth.md
plant "$ROLE"
printf '\nNew instruction nobody regenerated.\n' >> "$ROLE"
fails_with "agent-role lint catches a stale Codex adapter" \
  "$PT tests/harness/test_agent_roles_lint.py" "is stale"
unplant "$ROLE"

printf -- '---\ntype: project\n---\nA note nobody indexed.\n' > .agents/memory/orphan_note.md
fails_with "memory lint catches a note missing from MEMORY.md" \
  "$PT tests/harness/test_memory_vault.py" "orphan_note.md"
rm -f .agents/memory/orphan_note.md

plant AGENTS.md
python3 -c "open('AGENTS.md','a').write('\n' + 'x' * 33000 + '\n')"
fails_with "context lint catches AGENTS.md past Codex's 32 KiB" \
  "$PT tests/harness/test_context_docs.py" "over Codex's"
unplant AGENTS.md

plant mobile/lib/api.ts
sed -i.x 's/^  onboarded: boolean;$/  isOnboarded: boolean;/' mobile/lib/api.ts && rm -f mobile/lib/api.ts.x
fails_with "wire contract catches a renamed *Wire field" \
  "$PT tests/test_wire_contract.py" "never sent by the API"
unplant mobile/lib/api.ts

plant backend/routers/me.py
printf '\n\ndef leak(db):\n    return db.table("profiles").select("*").execute()\n' >> backend/routers/me.py
fails_with "static scoping guard catches an unscoped query" \
  "$PT tests/test_scoping_static.py" "me.py:leak"
unplant backend/routers/me.py

printf -- '-- Rollback: drop table public.planted;\ncreate table public.planted (id int);\n' \
  > supabase/migrations/20990101000000_planted.sql
fails_with "migration guard catches a table without RLS" \
  "$PT tests/test_migrations_static.py" "planted"
rm -f supabase/migrations/20990101000000_planted.sql

if command -v actionlint >/dev/null 2>&1; then
  check "actionlint clean on the generated workflows" "actionlint"
else
  skip "actionlint clean on the generated workflows" "actionlint"
fi
if command -v zizmor >/dev/null 2>&1; then
  check "zizmor clean on the generated workflows" "zizmor --offline .github/workflows"
  plant .github/workflows/ci.yml
  printf '      - run: echo "${{ github.event.pull_request.title }}"\n' >> .github/workflows/ci.yml
  fails_with "zizmor catches a planted template injection" \
    "zizmor --offline .github/workflows/ci.yml" "template-injection"
  unplant .github/workflows/ci.yml
else
  skip "zizmor clean on the generated workflows, and catches a planted injection" "zizmor"
fi
if [ -n "${APPBOX_SELFTEST_DATABASE_URL:-}" ]; then
  check "DB gate: migrations + advisors + pgTAP RLS + negative control" \
    "DATABASE_URL='$APPBOX_SELFTEST_DATABASE_URL' ./scripts/db-test.sh"
else
  skip "DB gate: migrations + advisors + pgTAP RLS + negative control" "APPBOX_SELFTEST_DATABASE_URL (Postgres + pgTAP)"
fi

check "every plant was reverted" "[ -z \"\$(git status --porcelain -- .agents .github AGENTS.md mobile backend supabase)\" ]"
