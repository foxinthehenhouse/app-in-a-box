# Routines are real files, every name they use resolves, and the self-driving
# loop's moving parts are tested for behaviour, not just presence. Sourced by selftest.sh.

# Every ritual on the routines menu has a spec file, and every skill a spec names exists.
_routines_resolve() {
  python3 - "$APP/.agents" <<'PY'
import pathlib, re, sys
a = pathlib.Path(sys.argv[1])
menu = (a / "skills/routines/SKILL.md").read_text()
rows = re.findall(r"^\| `([a-z-]+)` \|", menu, re.M)
assert len(rows) >= 6, f"menu rows: {rows}"
for r in rows:
    assert (a / "routines" / f"{r}.md").is_file(), f"no .agents/routines/{r}.md for menu row {r}"
for f in (a / "routines").glob("*.md"):
    for skill in re.findall(r"\.agents/skills/([a-z-]+)/SKILL\.md", f.read_text()):
        assert (a / "skills" / skill / "SKILL.md").is_file(), f"{f.name} names missing skill {skill}"
for skill in re.findall(r"\.agents/skills/([a-z<>-]+)/SKILL\.md", menu):
    assert skill == "<ritual>" or (a / "skills" / skill / "SKILL.md").is_file(), skill
assert ".agents/routines/<ritual>.md" in menu, "the Routine prompt must point at the spec file"
PY
}
check "routines: every menu ritual has a spec file; every skill a spec names exists" "_routines_resolve"

# next/signals.py's setup list mirrors the kit's phase order, with progress.py's rules.
_signals_setup() {
  python3 - "$KIT/scripts/progress.py" "$APP/.agents/skills/next/signals.py" <<'PY'
import importlib.util, sys
def load(p, n):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
prog, sig = load(sys.argv[1], "progress"), load(sys.argv[2], "signals")
assert sig.SETUP == [k for k, *_ in prog.PHASES], (sig.SETUP, [k for k, *_ in prog.PHASES])
def pending(p):
    sig.appbox = lambda: {"progress": p, "stack": {}}
    sig.sh = lambda *a, **k: None; sig.rituals = lambda: []
    return sig.local()["setup_pending"]
assert pending({"preflight": "done", "interview": "done", "validate": "running"})[0] == "design"
assert pending({"preflight": "done", "interview": "done"})[0] == "design"      # legacy
assert pending({"preflight": "done", "interview": "done", "validate": "pending"})[0] == "validate"
PY
}
check "next: setup list matches progress.py phases (validate included; running/legacy not 'next')" "_signals_setup"

# next --remote against a fake gh: failing checks per PR, red main runs, issue labels.
_signals_remote() {
  local f="$T/fake-gh-next"; mkdir -p "$f"
  cat > "$f/gh" <<'GH'
#!/usr/bin/env bash
case "$1 $2" in
  "pr list") echo '[{"number":4,"title":"t","isDraft":false,"headRefName":"b","reviewDecision":"","statusCheckRollup":[{"name":"ci","conclusion":"FAILURE"},{"name":"lint","conclusion":"SUCCESS"},{"context":"deploy","state":"ERROR"}]}]' ;;
  "run list") echo '[{"workflowName":"CI","conclusion":"failure","url":"u"},{"workflowName":"DB","conclusion":"success","url":"v"}]' ;;
  "issue list") echo '[{"number":9,"title":"bug","labels":[{"name":"p1"}]}]' ;;
  *) exit 1 ;;
esac
GH
  chmod +x "$f/gh"
  (cd "$APP" && PATH="$f:$PATH" python3 .agents/skills/next/signals.py --remote) | python3 -c "
import json,sys; d=json.load(sys.stdin)
assert d['gh_available'] is True
assert d['open_prs'][0]['failing_checks'] == ['ci', 'deploy'], d['open_prs']
assert [r['workflowName'] for r in d['main_ci_failing']] == ['CI']
assert d['open_issues'][0]['labels'] == ['p1']"
}
check "next --remote: failing checks per PR, red main runs and issue labels from gh" "_signals_remote"

# Workflow scripts: every phase() call is declared in meta.phases, and vice versa.
_workflow_phase_parity() {
  python3 - "$APP/.claude/workflows" <<'PY'
import pathlib, re, sys
for f in pathlib.Path(sys.argv[1]).glob("*.js"):
    s = f.read_text()
    meta = s[s.index("export const meta"):]
    declared = re.findall(r"title:\s*'([^']+)'", meta[:meta.index("\n}\n") if "\n}\n" in meta else 4000])
    called = re.findall(r"^\s*phase\('([^']+)'\)", s, re.M)
    assert called, f"{f.name}: no phase() calls"
    assert set(called) <= set(declared), f"{f.name}: phase() not in meta.phases: {set(called) - set(declared)}"
    assert set(declared) <= set(called), f"{f.name}: declared but never run: {set(declared) - set(called)}"
PY
}
check "workflow scripts: phase() calls and meta.phases match exactly" "_workflow_phase_parity"

# gitleaks with the generated repo's own config: the pristine app scans clean, and a
# planted Supabase secret key is caught by the custom rule. The fake key is assembled at
# run time so no key-shaped literal ever sits in this repo.
_gitleaks_catches() {
  local out rc
  (cd "$APP" && gitleaks dir . --config .gitleaks.toml --no-banner --exit-code 1 >/dev/null 2>&1) || { echo "pristine app not clean"; return 1; }
  printf 'SUPABASE_SECRET_KEY=%s%s\n' "sb_secret_" "Zq7XkP2mLw9RtY4vB8nC" > "$APP/backend/planted_config.py"
  out=$(cd "$APP" && gitleaks dir backend/planted_config.py --config .gitleaks.toml --no-banner --exit-code 1 --report-format json --report-path - 2>/dev/null); rc=$?
  rm -f "$APP/backend/planted_config.py"
  [ "$rc" = 1 ] && printf '%s' "$out" | grep -q '"RuleID": "supabase-secret-key"'
}
if command -v gitleaks >/dev/null 2>&1; then
  check "gitleaks: the generated app scans clean, and a planted Supabase secret key is caught" "_gitleaks_catches"
else
  skip "gitleaks: the generated app scans clean, and a planted Supabase secret key is caught" "gitleaks"
fi
