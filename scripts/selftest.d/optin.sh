# Opt-in services + ticket capture: sourced by selftest.sh with $KIT, $APP,
# $T and the check/refuses helpers.

# A declined service loses its MCP server in BOTH agents' configs; a bare render
# (no appbox.yaml) keeps every server.
_mcp_pruned() {
  local d="$T/optin-app"
  rm -rf "$d" && mkdir -p "$d"
  printf 'stack:\n  tracker: github   # github|linear\n  analytics: none\n  errors: sentry\n' > "$d/appbox.yaml"
  python3 "$KIT/scripts/render.py" --target "$d" --name "Opt In" --slug opt-in \
    --bundle-id com.t.optin --owner t >/dev/null || return 1
  python3 - "$d" <<'PY' || return 1
import json, sys, pathlib
d = pathlib.Path(sys.argv[1])
servers = set(json.loads((d / ".mcp.json").read_text())["mcpServers"])
codex = (d / ".codex" / "config.toml").read_text()
assert "posthog" not in servers and "linear" not in servers, servers
assert "sentry" in servers and "github" in servers, servers
assert "posthog" not in codex and "linear" not in codex
PY
  # Switching a service back on restores its server (the no-op calls were there all along).
  sed -i.bak 's/  analytics: none/  analytics: posthog/' "$d/appbox.yaml" && rm -f "$d/appbox.yaml.bak"
  python3 "$KIT/scripts/render.py" --target "$d" --adapters-only >/dev/null || return 1
  grep -q '"posthog"' "$d/.mcp.json" && grep -q 'posthog' "$d/.codex/config.toml" || return 1
  sed -i.bak 's/  analytics: posthog/  analytics: none/' "$d/appbox.yaml" && rm -f "$d/appbox.yaml.bak"  # declined again for the doctor check
  python3 - "$APP" <<'PY'
import json, sys, pathlib
servers = set(json.loads((pathlib.Path(sys.argv[1]) / ".mcp.json").read_text())["mcpServers"])
assert {"posthog", "sentry", "linear"} <= servers, servers
PY
}
check "declined services lose their MCP server (Claude + Codex), re-enabling restores it; bare render keeps all" "_mcp_pruned"

# doctor exits non-zero when logins are missing (they are, here): capture, then grep.
_doctor_skips() {
  (cd "$T/optin-app" && bash "$KIT/scripts/doctor.sh" accounts > "$T/doctor.out" 2>&1) || true
  grep -q 'posthog.*not in the stack' "$T/doctor.out" && ! grep -q 'POSTHOG_PERSONAL_API_KEY' "$T/doctor.out"
}
check "doctor skips declined services" "_doctor_skips"

check "interview asks tracker (Linear recommended), analytics and error monitoring" \
  "grep -q 'Ticket management:\*\* Linear + its MCP (Recommended' '$KIT/skills/interview/SKILL.md' \
   && grep -q 'Product analytics:\*\*' '$KIT/skills/interview/SKILL.md' \
   && grep -q 'Error monitoring:\*\*' '$KIT/skills/interview/SKILL.md' \
   && grep -q 'analytics: posthog          # posthog|none' '$KIT/skills/interview/SKILL.md'"

# The ticket guard: run its real script against sample PRs.
_ticket_guard() {
  local script; script=$(python3 -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1]))['jobs']['ticket']['steps'][0]['run'])" "$APP/.github/workflows/ticket.yml") || return 1
  pr() { TITLE="$1" BODY="$2" BRANCH="$3" AUTHOR="${4:-dev}" GITHUB_EVENT_NAME="${5:-pull_request}" bash -c "$script" >/dev/null 2>&1; }
  pr "feat: streaks (APP-12)" "" "x" && pr "feat: streaks" "Closes #42" "x" \
    && pr "feat: x" "" "feat/42-streak" && pr "fix: y" "" "fix/APP-17-otp" \
    && pr "typo [no-ticket]" "" "x" && pr "bump" "" "dependabot/npm" "dependabot[bot]" \
    && pr "bump" "" "renovate/x" "renovate[bot]" && pr "" "" "" "" merge_group \
    && ! pr "feat: stuff" "no id here" "feat/stuff" && ! pr "feat: v2" "" "feat/v2-redesign"
}
check "ticket guard passes ticketed PRs and fails untracked ones" "_ticket_guard"

check "backlog skill captures sub-issues; AGENTS.md says file them immediately" \
  "grep -q '^### Sub-tasks: capture them as you go' '$APP/.agents/skills/backlog/SKILL.md' \
   && grep -q 'parentId' '$APP/.agents/skills/backlog/SKILL.md' \
   && grep -q 'File sub-tasks and follow-ups the' '$APP/AGENTS.md'"

# Owner asks: strip one listed skill's ask step in a copy of the app; the harness lint
# must fail on exactly that.
_owner_ask_lint_fails() {
  local c="$T/owner-neg"
  rm -rf "$c" && mkdir -p "$c/.claude"
  cp -R "$APP/.agents" "$APP/tests" "$APP/AGENTS.md" "$c/" && cp -R "$APP/.claude/harness" "$c/.claude/"
  python3 - "$c/.agents/skills/ship/SKILL.md" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()
p.write_text(s.split("\n## Ask the owner", 1)[0] + "\n")
PY
  (cd "$c" && "$APP/.venv/bin/python" -m pytest -q -p no:cacheprovider tests/harness/test_owner_asks.py > "$T/owner.out" 2>&1) && return 1
  grep -q "ship: no '## Ask the owner' section" "$T/owner.out"
}
check "owner-asks lint fails when a product skill stops asking" "_owner_ask_lint_fails"

# Living AGENTS.md: add a router with no map row in a copy of the app; the lint fails.
# Then mark scaffold done with a marker still in place; the lint fails again.
_agents_md_lint_fails() {
  local c="$T/agents-neg"
  rm -rf "$c" && mkdir -p "$c/.claude"
  cp -R "$APP/.agents" "$APP/tests" "$APP/AGENTS.md" "$APP/backend" "$APP/mobile" "$APP/supabase" "$c/" 2>/dev/null
  cp -R "$APP/.claude/harness" "$c/.claude/"
  touch "$c/backend/routers/widgets.py"
  (cd "$c" && "$APP/.venv/bin/python" -m pytest -q -p no:cacheprovider tests/harness/test_agents_md_current.py > "$T/amd.out" 2>&1) && return 1
  grep -q "API router routers/widgets.py" "$T/amd.out" || return 1
  rm "$c/backend/routers/widgets.py" && printf 'progress:\n  scaffold: done\n' > "$c/appbox.yaml"
  (cd "$c" && "$APP/.venv/bin/python" -m pytest -q -p no:cacheprovider tests/harness/test_agents_md_current.py > "$T/amd.out" 2>&1) && return 1
  grep -q "appbox:product" "$T/amd.out"
}
check "AGENTS.md lint fails on an unmapped router and on markers left after scaffold" "_agents_md_lint_fails"

check "scaffold drafts AGENTS.md from the brief and asks the owner to review it" \
  "grep -q 'Draft AGENTS.md from the interview' '$KIT/skills/scaffold/SKILL.md' \
   && grep -q 'Does this describe your app?' '$KIT/skills/scaffold/SKILL.md'"
