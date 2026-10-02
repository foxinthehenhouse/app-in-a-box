# Kit consistency: things the kit's docs promise must exist in the template.
# Sourced by selftest.sh (cwd = rendered app, with $KIT, $APP, check/refuses).

_required_checks_exist() {
  python3 - "$KIT/skills/harness/SKILL.md" "$APP/.github/workflows" <<'PY'
import re, sys, pathlib, yaml
skill = pathlib.Path(sys.argv[1]).read_text()
m = re.search(r"<!-- required-checks: ([^>]+) -->", skill)
assert m, "harness skill lost its required-checks marker"
required = m.group(1).split()
jobs = {}
for wf in pathlib.Path(sys.argv[2]).glob("*.yml"):
    d = yaml.safe_load(wf.read_text())
    for jid, job in (d.get("jobs") or {}).items():
        jobs[jid] = job
missing = [r for r in required if r not in jobs]
conditional = [r for r in required if r in jobs and jobs[r].get("if")]
in_cmd = re.findall(r"contexts\]\[\]=([\w-]+)", skill)
assert not missing, f"required checks with no such job: {missing}"
assert not conditional, f"required checks that can be skipped by `if:`: {conditional}"
assert sorted(in_cmd) == sorted(required), f"gh api command {in_cmd} != marker {required}"
PY
}
check "harness skill's required checks are real, unconditional job ids" "_required_checks_exist"

# pre-commit must catch a key even when the staged diff is large (the SIGPIPE bypass:
# `git diff | grep -q` under pipefail silently passed on a 240 KB file).
_big_diff_secret_refused() {
  local r; r="$(mktemp -d)"
  cp -R "$APP/.githooks" "$r/" && cd "$r" && git init -q -b feat/x && git config core.hooksPath .githooks
  { printf 'KEY=sb_secret_abcdefghijklmnopqrstuv\n'; head -c 250000 /dev/zero | tr '\0' 'a' | fold -w 100; } > big.txt
  git add big.txt
  if git -c user.email=t@example.com -c user.name=t commit -qm big >/dev/null 2>&1; then cd "$APP"; rm -rf "$r"; return 1; fi
  cd "$APP"; rm -rf "$r"; return 0
}
check "pre-commit refuses a key on line 1 of a 250 KB staged file" "_big_diff_secret_refused"

# bash-safety's .env guard: every fixture line is WANT|command (ALLOW or BLOCK).
_env_guard_cases() {
  local bad=0 want c rc got
  while IFS='|' read -r want c; do
    [ -n "$want" ] || continue
    printf '{"tool_input":{"command":%s}}' "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$c")" \
      | bash "$APP/.claude/hooks/bash-safety.sh" >/dev/null 2>&1; rc=$?
    got=$([ "$rc" = 2 ] && echo BLOCK || echo ALLOW)
    [ "$got" = "$want" ] || { echo "env guard: want $want got $got: $c" >&2; bad=1; }
  done < "$(dirname "${BASH_SOURCE[0]}")/fixtures/env-guard-cases.txt"
  return "$bad"
}
check "bash-safety .env guard: 17 allow/block cases" "_env_guard_cases"

# env_set.py: the .env ends 0600, an upsert replaces rather than duplicates (also an
# `export KEY=` line, keeping its prefix), no value is printed, and the write is atomic:
# a 0600 temp file renamed over the target, so no temp file is left behind and an
# unrelated line survives byte-for-byte.
_env_set_safe() {
  local d; d="$(mktemp -d)"
  (umask 022; printf 'A_KEY=sekrit1\nB_KEY=x\n' | python3 "$KIT/scripts/env_set.py" "$d/.env") > "$d/out" || return 1
  printf 'A_KEY=sekrit2\n' | python3 "$KIT/scripts/env_set.py" "$d/.env" >> "$d/out" || return 1
  [ "$(stat -c %a "$d/.env" 2>/dev/null || stat -f %Lp "$d/.env")" = 600 ] || return 1
  [ "$(grep -c '^A_KEY=' "$d/.env")" = 1 ] && grep -qx 'A_KEY=sekrit2' "$d/.env" || return 1
  ! grep -q sekrit "$d/out" || return 1
  # export-prefixed lines are the same key: replaced in place, prefix kept, not duplicated.
  printf '# comment\nexport C_KEY=old\nD_KEY=keep\n' > "$d/.env"
  printf 'C_KEY=new\n' | python3 "$KIT/scripts/env_set.py" "$d/.env" >> "$d/out" || return 1
  [ "$(grep -c 'C_KEY=' "$d/.env")" = 1 ] && grep -qx 'export C_KEY=new' "$d/.env" || return 1
  grep -qx '# comment' "$d/.env" && grep -qx 'D_KEY=keep' "$d/.env" || return 1
  [ "$(stat -c %a "$d/.env" 2>/dev/null || stat -f %Lp "$d/.env")" = 600 ] || return 1
  # atomic write: nothing but .env and our own capture file in the directory afterwards
  [ "$(ls -A "$d" | sort | tr '\n' ' ')" = ".env out " ]
}
check "env_set.py leaves .env 0600, upserts in place (incl. export KEY=), never prints a value, writes atomically" "_env_set_safe"
