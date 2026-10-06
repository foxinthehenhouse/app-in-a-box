# Code health + drift: sourced by selftest.sh with $KIT, $APP (rendered app, venv built
# by the Backend section), $T and the check/refuses helpers. Each guard passes on the
# pristine app and FAILS, naming its rule, on a planted violation:
#   check_generated.py   tokens.ts / Codex adapters rebuilt from source; a hand edit fails
#   check_pr_title.py    the squash-commit title shape (pr-title.yml)
#   CODEOWNERS           migrations, .github, .agents and auth keep an owner
#   ruff C90/SIM/RET/PT  complexity <= 10 and the simpler-code rules (pyproject.toml)
#   vulture              dead code in backend/ at 80% confidence (CI)
# knip and the ESLint complexity rules need node_modules: their plants run in the
# --mobile pass (selftest.d/mobile/code-health.sh).
CH_PY="$APP/.venv/bin"

_ch_copy() {  # a throwaway copy of the rendered app (no venv, no git) at $T/ch
  rm -rf "$T/ch"; mkdir -p "$T/ch"
  (cd "$APP" && tar --exclude=.venv --exclude=.git --exclude=node_modules -cf - .) | (cd "$T/ch" && tar -xf -)
}

# ---- generated files ---------------------------------------------------------------
check "generated: tokens.ts and the Codex adapters in a fresh render are current" \
  "cd '$APP' && python3 scripts/check_generated.py"
check "generated: the renderer writes them with the app's own generator (one implementation)" \
  "grep -q 'template\" / \"scripts\" / \"check_generated.py\"\\|TEMPLATE / \"scripts\" / \"check_generated.py\"' '$KIT/scripts/render.py' && ! grep -q '^def tokens_ts\\|^def codex_agent_toml' '$KIT/scripts/render.py'"
check "generated: CI runs the freshness check" \
  "grep -q 'run: python3 scripts/check_generated.py' '$APP/.github/workflows/ci.yml'"
_ch_tokens_edit() {
  _ch_copy && sed -i 's/"accent": "#[0-9A-Fa-f]*"/"accent": "#FF0000"/' "$T/ch/mobile/lib/tokens.ts" \
    && cd "$T/ch" && python3 scripts/check_generated.py
}
_ch_codex_edit() {
  _ch_copy && echo 'sandbox_mode = "danger-full-access"' >> "$T/ch/.codex/agents/chair.toml" \
    && cd "$T/ch" && python3 scripts/check_generated.py
}
_ch_source_edit() {  # the other direction: a source edited, the adapter not regenerated
  _ch_copy && printf '\nAlso check the changelog.\n' >> "$T/ch/.agents/agents/chair.md" \
    && cd "$T/ch" && python3 scripts/check_generated.py
}
refuses "generated: a hand edit to mobile/lib/tokens.ts fails" "_ch_tokens_edit" \
  "mobile/lib/tokens.ts: differs from what its source generates"
refuses "generated: a hand edit to a Codex role fails" "_ch_codex_edit" \
  ".codex/agents/chair.toml: differs from what its source generates"
refuses "generated: a role edited without regenerating its Codex adapter fails" "_ch_source_edit" \
  ".codex/agents/chair.toml: differs"
check "generated: --fix regenerates, and the check passes again" \
  "_ch_copy && echo x >> '$T/ch/.codex/hooks.json' && cd '$T/ch' && python3 scripts/check_generated.py --fix >/dev/null && python3 scripts/check_generated.py"

# ---- PR titles ---------------------------------------------------------------------
check "pr title: a backlog-shaped title passes" \
  "python3 '$APP/scripts/check_pr_title.py' 'feat: streak count on Home (#42)'"
refuses "pr title: a title with no type fails" \
  "python3 '$APP/scripts/check_pr_title.py' 'Update api.ts'" "must look like \`<type>: <summary>\`"
refuses "pr title: a WIP title fails (squash merge would put it on main)" \
  "PR_TITLE='feat: WIP streaks' python3 '$APP/scripts/check_pr_title.py'" "WIP/draft marker"
check "pr title: pr-title.yml runs it, and pr-title is a required check in the harness skill" \
  "grep -q 'python3 scripts/check_pr_title.py' '$APP/.github/workflows/pr-title.yml' && grep -q 'required-checks: .*pr-title' '$KIT/skills/harness/SKILL.md'"

# ---- CODEOWNERS --------------------------------------------------------------------
_ch_owners() {  # <CODEOWNERS file>: the app's own rule, applied to it
  "$CH_PY/python" - "$APP/tests/harness" "$1" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import test_code_health as t
problems = t.codeowners_problems(open(sys.argv[2]).read())
print(*problems, sep="\n")
sys.exit(1 if problems else 0)
PY
}
check "codeowners: the rendered app's CODEOWNERS owns migrations, .github, .agents and auth (@alex)" \
  "_ch_owners '$APP/.github/CODEOWNERS' && grep -q '^/supabase/migrations/ @alex$' '$APP/.github/CODEOWNERS'"
refuses "codeowners: dropping the migrations line fails" \
  "grep -v '^/supabase/migrations/' '$APP/.github/CODEOWNERS' > '$T/co-nomig' && _ch_owners '$T/co-nomig'" \
  "supabase/migrations/20250101000000_example.sql has no code owner"
refuses "codeowners: a later owner-less line that un-owns auth fails" \
  "{ cat '$APP/.github/CODEOWNERS'; echo '/mobile/lib/'; } > '$T/co-unown' && _ch_owners '$T/co-unown'" \
  "mobile/lib/auth.tsx has no code owner"

# ---- ruff complexity + vulture -----------------------------------------------------
check "ruff: C90 (max 10), ASYNC, SIM, RET and PT are on, and the app's backend, tests and scripts pass" \
  "grep -q '\"C90\", \"ASYNC\", \"SIM\", \"RET\", \"PT\"' '$APP/pyproject.toml' && grep -q '^max-complexity = 10$' '$APP/pyproject.toml' && cd '$APP' && '$CH_PY/ruff' check backend tests scripts"
_ch_complex() {  # a backend function with 11 branches
  _ch_copy && python3 - "$T/ch/backend/planted.py" <<'PY' && cd "$T/ch" && "$CH_PY/ruff" check backend
import sys
body = "".join(f"    if x == {i}:\n        return {i}\n" for i in range(11))
open(sys.argv[1], "w").write(f"def route(x: int) -> int:\n{body}    return -1\n")
PY
}
refuses "ruff: a backend function with complexity 11 fails" "_ch_complex" "C901 \`route\` is too complex (12 > 10)"
check "vulture: the app's backend is clean at 80% confidence, and CI runs it" \
  "cd '$APP' && '$CH_PY/vulture' && grep -q 'run: vulture' .github/workflows/ci.yml && grep -q '^vulture>=' requirements-dev.txt"
_ch_dead() {
  _ch_copy && printf 'import fractions\n' >> "$T/ch/backend/config.py" && cd "$T/ch" && "$CH_PY/vulture"
}
refuses "vulture: an unused import in the backend fails" "_ch_dead" "unused import 'fractions'"

# ---- the mobile gates are configured (the plants run under --mobile) ---------------
check "knip: in npm run gates, pinned in mobile-deps.sh, configured in mobile/knip.jsonc" \
  "grep -q 'eslint . && knip && ' '$KIT/scripts/mobile-deps.sh' && grep -q '\"knip@^6\"' '$KIT/scripts/mobile-deps.sh' && [ -f '$APP/mobile/knip.jsonc' ]"
check "eslint: complexity, max-depth, max-nested-callbacks and max-params are errors" \
  "grep -q 'complexity: \\[\"error\", 15\\]' '$APP/mobile/eslint.config.js' && grep -q '\"max-depth\": \\[\"error\"' '$APP/mobile/eslint.config.js'"
check "code health: the app's own guard tests (rules + negative controls) pass" \
  "cd '$APP' && '$CH_PY/python' -m pytest -q tests/harness/test_code_health.py"
