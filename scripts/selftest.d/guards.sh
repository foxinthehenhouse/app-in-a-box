# Guard negative controls (teardown, 2026-10-01): sourced by selftest.sh with $KIT, $APP (rendered
# app, a git repo on feat/selftest, cwd), $T and check/refuses/skip.
#
# Each case is phrased the way a future editor would actually write the violation, not
# in the guard's own vocabulary: a control built from the regex's own prefixes proves
# the regex matches itself and nothing else. Benign lookalikes must PASS, or the guard
# gets switched off.

_G="git -c user.email=t@example.com -c user.name=selftest"

# pre-commit: the shapes provisioning writes (capitals), a real PEM (header + body), and
# lookalikes that must pass (a header alone in a scanner's test file; prose about keys).
_precommit_case() {  # <expect: refuse|allow> <name> <content...>
  local expect="$1" name="$2"; shift 2
  printf '%s\n' "$@" > "$APP/_plant.txt"; git add -f "$APP/_plant.txt"
  local err
  if err="$($_G commit -qm plant 2>&1 >/dev/null)"; then
    git reset -q --soft HEAD~1; git restore --staged "$APP/_plant.txt"; rm -f "$APP/_plant.txt"
    [ "$expect" = allow ] && ok "pre-commit allows: $name" || bad "pre-commit LET THROUGH: $name"
  else
    git restore --staged "$APP/_plant.txt"; rm -f "$APP/_plant.txt"
    # Refused for the right reason: the hook's own message, not a crash in the hook.
    if [ "$expect" = refuse ]; then
      grep -q '^pre-commit:' <<<"$err" && ok "pre-commit refuses: $name" || bad "pre-commit failed, but not with its own message: $name"
    else bad "pre-commit blocked a benign commit: $name"; fi
  fi
}
# Each planted value is assembled from two halves at run time. A literal that looks like a
# real token trips GitHub push protection and every scanner (that IS the plant's point),
# but it must never sit in this repo's own history.
_j() { printf '%s%s' "$1" "$2"; }
_precommit_case refuse "SUPABASE_SERVICE_ROLE_KEY=eyJ... (what provisioning writes)" \
  "SUPABASE_SERVICE_ROLE_KEY=$(_j eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 .eyJyb2xlIjoic2VydmljZV9yb2xlIn0)"
_precommit_case refuse "SENTRY_AUTH_TOKEN=sntrys_..." \
  "SENTRY_AUTH_TOKEN=$(_j sntrys_ eyJpYXQiOjE3MjM0NTY3ODkuMTIzNDU2LCJ1cmwiOiJodHRwczovL3NlbnRyeS5pbyJ9_abcdefghijklmnop)"
_precommit_case refuse "OpenAI project key" "OPENAI_API_KEY=$(_j sk-proj- abcdefghijklmnopqrstuvwxyz0123456789)"
_precommit_case refuse "Stripe live key" "STRIPE_SECRET_KEY=$(_j sk_live_ abcdefghijklmnopqrstuv)"
_precommit_case refuse "Slack bot token" "SLACK_TOKEN=$(_j xoxb- 123456789012-abcdefghijklmnopqrstuvwx)"
_precommit_case refuse "GitHub app installation token" "GH_TOKEN=$(_j ghs_ abcdefghijklmnopqrstuvwxyz0123456789)"
_precommit_case refuse "a service_role JWT under a renamed variable (payload says service_role)" \
  "BACKEND_SUPABASE_KEY=$(_j eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9. eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFiY2RlZmdoaWprbG1ub3BxcnN0Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MX0)"
_precommit_case allow "the anon JWT under any variable name (payload says anon)" \
  "SUPABASE_ANON_KEY=$(_j eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9. eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJhbm9uIn0)"
_precommit_case refuse "a legacy encrypted PEM (Proc-Type line before the body)" \
  "$(_j '-----BEGIN RSA ' 'PRIVATE KEY-----')" 'Proc-Type: 4,ENCRYPTED' 'DEK-Info: AES-256-CBC,ABCDEF0123456789ABCDEF0123456789' 'MIIEpAIBAAKCAQEA7x9kZ2b8ZxQ2v1kJ8nYq3F0pL5sT2rW9cH4dG6eA1bC3dE5f'
_precommit_case refuse "a PEM private key (header + body)" \
  "$(_j '-----BEGIN RSA ' 'PRIVATE KEY-----')" 'MIIEpAIBAAKCAQEA7x9kZ2b8ZxQ2v1kJ8nYq3F0pL5sT2rW9cH4dG6eA1bC3dE5f'
_precommit_case allow "a PEM header alone (a secret scanner's own test fixture)" \
  'PATTERNS = ["-----BEGIN RSA PRIVATE KEY-----"]'
_precommit_case allow "prose that mentions the service_role key" \
  'The service_role key lives in .env and is never committed; see docs/runbooks/secrets-rotation.md.'

# pre-push: the main-branch block fires with gates skipped; a branch passes.
_prepush() {  # <remote ref>
  printf 'refs/heads/feat/selftest %s %s %s\n' "$(printf 0%.0s {1..40})" "$1" "$(printf 0%.0s {1..40})" \
    | SKIP_GATES=1 bash "$APP/.githooks/pre-push" origin x 2>&1
}
MAINREF="refs/heads/ma""in"
refuses "pre-push refuses a push to $MAINREF (gates skipped, block still fires)" "_prepush $MAINREF" "pre-push:"
check "pre-push allows a branch" "_prepush refs/heads/feat/selftest"

# ticket guard: run the workflow's real script. Lookalikes that used to pass must fail.
_ticket() {  # <TITLE> <BODY> <BRANCH>
  local script; script=$(python3 -c "import yaml,sys;print(yaml.safe_load(open(sys.argv[1]))['jobs']['ticket']['steps'][0]['run'])" "$APP/.github/workflows/ticket.yml") || return 2
  TITLE="$1" BODY="$2" BRANCH="$3" AUTHOR=dev GITHUB_EVENT_NAME=pull_request bash -c "$script" 2>&1
}
check "ticket guard: Linear id in title, GitHub #id in body, id in branch all pass" \
  "_ticket 'feat: streaks (APP-12)' '' x && _ticket 'feat: streaks' 'Closes #42' x && _ticket 'fix: y' '' fix/APP-17-otp && _ticket 'feat: x' '' feat/42-streak"
refuses "ticket guard: SHA-256 / ISO-8601 / UTF-8 in the title are not tickets" \
  "_ticket 'docs: hash with SHA-256, dates as ISO-8601, text as UTF-8' '' feat/hashing" "No ticket id"
refuses "ticket guard: a date in the branch is not a ticket (chore/2026-09-30-cleanup)" \
  "_ticket 'chore: cleanup' '' chore/2026-09-30-cleanup" "No ticket id"
refuses "ticket guard: a version in the branch is not a ticket (release/1-0)" \
  "_ticket 'release 1.0' '' release/1-0" "No ticket id"

# No build artefacts in the kit's own tree: a tracked .pyc embeds the contributor's absolute
# path and ships to every founder who installs the plugin (four did, once; no guard saw it).
_tracked_artefacts() { (cd "$KIT/../.." && git ls-files | grep -E '(^|/)(__pycache__/|node_modules/|\.pytest_cache/|\.ruff_cache/)|\.pyc$'); }
check "kit: no tracked build artefacts (__pycache__, .pyc, node_modules, tool caches)" "! _tracked_artefacts"
_artefact_plant() {
  local f="$KIT/scripts/zz_plant.pyc"; : > "$f"; (cd "$KIT/../.." && git add -N "$f")
  _tracked_artefacts >/dev/null; local rc=$?
  (cd "$KIT/../.." && git rm -q --cached "$f"); rm -f "$f"; [ "$rc" = 0 ]
}
check "kit: the artefact check catches a planted tracked .pyc" _artefact_plant
