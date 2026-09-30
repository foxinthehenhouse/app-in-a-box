#!/usr/bin/env bash
# PreToolUse(Bash) safety hook.
# Reads the bash command from stdin (JSON) and exits 2 to block if a danger pattern matches.
# Exit 2 → blocking; stderr is shown to Claude (auto-relayed back to the model).
# Exit 0 → allow; output ignored.
# Belt-and-braces with settings.json deny list — hook gives a message, deny list gives hard block.

set -u

# Read JSON input from stdin
INPUT=$(cat 2>/dev/null || echo "{}")

# Extract the command string. tool_input.command is the path for Bash.
# Use python3 for safe JSON parsing — falls open if python3 is unavailable.
CMD=$(printf '%s' "$INPUT" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' 2>/dev/null || echo "")

# Empty command — allow.
[ -z "$CMD" ] && exit 0

# Current git context (fail-open: empty strings if not a repo / git errors).
# CUR_BRANCH = symbolic branch name, or "HEAD" when detached.
CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
# DETACHED = "1" if HEAD is detached, else "0".
if [ "$CUR_BRANCH" = "HEAD" ]; then DETACHED="1"; else DETACHED="0"; fi
export CUR_BRANCH DETACHED

block() {
  echo "BLOCKED by .claude/hooks/bash-safety.sh: $1" >&2
  echo "Command: $CMD" >&2
  echo "If you genuinely need this, ask the project owner to allow it explicitly." >&2
  exit 2
}

# Hard-block patterns. Use Python regex for precision so we don't false-positive
# on benign cases like `rm -rf /tmp/foo` (only / itself, $HOME, ~, and system dirs).
# Fail open if python3 is unavailable (no regex engine → allow).
command -v python3 >/dev/null 2>&1 || exit 0

# NOTE: do NOT chain `|| exit 0` here — python exits 2 to signal a block, and `||`
# would swallow that into a fail-open allow. We capture RC explicitly below and
# only treat the well-defined exit code 2 (block) specially; any other failure
# (e.g. python internal error) falls through to the trailing `exit 0` (fail open).
python3 - "$CMD" <<'PY'
import os, re, sys
cmd = sys.argv[1]

cur_branch = os.environ.get("CUR_BRANCH", "")
detached = os.environ.get("DETACHED", "0") == "1"

def block(msg):
    sys.stderr.write(f"BLOCKED by .claude/hooks/bash-safety.sh: {msg}\n")
    sys.stderr.write(f"Command: {cmd}\n")
    sys.stderr.write("If you genuinely need this, ask the project owner to allow it explicitly.\n")
    sys.exit(2)

def warn(msg):
    sys.stderr.write(f"WARNING from .claude/hooks/bash-safety.sh: {msg}\n")

DANGER = [
    # rm -rf against root or system dirs or $HOME or ~
    (r'\brm\s+-[rRf]+\s+(/|/\*|~|~/|\$HOME|/etc|/var|/usr|/bin|/sbin|/lib|/boot|/System|/Library|/Applications|/Users\b)(\s|$|/\s|/$)',
     'rm -rf against root/system/$HOME/~'),
    (r'--no-verify\b',
     '--no-verify (skipping git hooks). Fix the hook failure instead.'),
    (r'--dangerously-skip-permissions\b',
     '--dangerously-skip-permissions is forbidden outside sandboxed worktrees.'),
    (r'git\s+push\s+(-f|--force(-with-lease)?)\s+\S+\s+(main|master)\b',
     'force-push to main/master.'),
    # ANY push whose explicit target ref is main/master (not just force).
    # Matches: `git push origin main`, `git push origin HEAD:main`,
    #          `git push origin feat/x:main`, `git push -u origin master`.
    # The remote token (origin/etc) sits between `push` and the refspec; flags
    # like -u/--set-upstream/-f may precede it.
    (r'git\s+push\b(?:\s+(?:-u|--set-upstream|-f|--force(?:-with-lease)?|--tags|-q|--quiet))*\s+\S+\s+(?:\S+:)?(?:main|master)\b',
     'pushing to main/master directly. Feature work ships via PR — never push to main.'),
    (r'\bchmod\s+(-R\s+)?777\b',
     'chmod 777 is almost never what you want.'),
    (r'(curl|wget)\s+[^|]*\|\s*(sh|bash|zsh)\b',
     'piping curl/wget directly to sh. Download, inspect, then run.'),
    (r':\(\)\s*\{\s*:\|:&\s*\}\s*;:',
     'fork bomb.'),
    (r'\bdd\s+if=[^ ]*\s+of=/dev/(sd|nvme|disk)\w*',
     'dd to a raw block device.'),
]

for pat, msg in DANGER:
    if re.search(pat, cmd):
        block(msg)

# --- .env guard ---------------------------------------------------------------
# A GUARDRAIL, NOT A BOUNDARY: it stops the obvious, accidental ways an agent would
# print secrets into its transcript. It matches command text, so a multi-step route
# (`cp .env /tmp/x; cat /tmp/x`, a script that reads it) gets through. The real
# protections are that secrets never enter git (pre-commit + gitleaks) and that
# nobody pastes them into chat.
# settings.json denies the Read tool on .env, but Bash can print it just as well
# (`head .env`, `python3 -c "print(open('.env').read())"`, `curl -d @.env`), and a
# printed secret lands in the transcript. Allowed: sourcing it into the shell
# (`set -a; . ./.env; set +a`), writing/appending to it, name-only checks
# (`grep -q`/`grep -c '^KEY='`), `git check-ignore`, `git restore --staged`, cp/touch.
ENV_REF = r"(?:^|[\s/'\"=@<(])\.env(?![\w.-]*example)(?:\.[\w-]+)?(?=$|[\s'\")/;|&])"
if re.search(ENV_REF, cmd):
    safe_segments = (
        r"^\s*(set\s+[+-]a|\.\s+\S*\.env|source\s+\S*\.env)",
        r"^\s*grep\s+(-[a-zA-Z]*[qc][a-zA-Z]*\s+)",
        r"^\s*git\s+(check-ignore|restore\s+--staged|rm\s+--cached|add\s+-f)",
        r"^\s*(cp|touch|chmod)\s",
        r"^\s*python3\s+[\"']?[^\s\"']*scripts/env_set\.py[\"']?\s",  # the kit's write-only dotenv helper
        r"^\s*(printf|echo)\s[^|]*>>?\s*\S+\s*$",
    )
    for seg in re.split(r"&&|\|\||;|\|", cmd):
        if not re.search(ENV_REF, seg):
            continue
        if any(re.search(s, seg) for s in safe_segments):
            continue
        block("this command reads a .env file, which would print secrets into the "
              "transcript. Source it instead (`set -a; . ./.env; set +a; <command using "
              "$VARS>`) or check a name with `grep -c '^KEY=' .env`.")

# --- Context-aware git push guard -------------------------------------------
# A `git push` that does NOT name an explicit branch refspec inherits its target
# from the current branch / push.default. That is exactly how commits leaked onto
# the wrong branch in past incidents. Block such "contextual" pushes whenever the
# current branch is main/master OR HEAD is detached.
#
# A push is "explicit" (and thus safe to allow here) if it names a refspec after
# the remote — e.g. `git push origin feat/x` or `git push origin HEAD:feat/x`.
# (Pushes to main were already blocked above.)
if re.search(r'\bgit\s+push\b', cmd):
    # Strip everything up to and including `push`, then inspect what follows.
    # `git push [flags] [remote] [refspec]`
    m = re.search(r'\bgit\s+push\b(.*)$', cmd)
    tail = m.group(1) if m else ""
    toks = [t for t in tail.split() if t]
    # Positional args (remote, refspec) are tokens that aren't flags / key=val.
    positionals = [t for t in toks
                   if not t.startswith('-') and '=' not in t]
    # positionals[0] = remote, positionals[1] = refspec (if present).
    has_explicit_refspec = len(positionals) >= 2
    if not has_explicit_refspec:
        if detached:
            block("bare/contextual `git push` while HEAD is DETACHED — this can "
                  "push to an unintended ref. Check out your feature branch and push "
                  "it explicitly: `git push origin <branch>`.")
        if cur_branch in ("main", "master"):
            block(f"bare/contextual `git push` while on `{cur_branch}` — feature work "
                  "ships via PR. Switch to your feature branch and push it explicitly: "
                  "`git push origin <branch>`.")
        # Otherwise (on a feature branch): allow, but nudge toward an explicit push
        # so a stale/unexpected current branch can't be inherited silently.
        if cur_branch and cur_branch not in ("main", "master"):
            warn(f"`git push` without an explicit branch will push the CURRENT branch "
                 f"(`{cur_branch}`). If that is not what you intend, push explicitly: "
                 f"`git push origin {cur_branch}`.")

# Committing on main is blocked by .githooks/pre-commit, which binds every agent.

sys.exit(0)
PY
RC=$?
# Propagate hook block (exit 2) if Python decided so.
[ $RC -eq 2 ] && exit 2
exit 0

exit 0
