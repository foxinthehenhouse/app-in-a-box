#!/usr/bin/env bash
# PostToolUse(all) + UserPromptSubmit: CAPTURE, the raw layer of the self-learning loop.
# Appends a one-line breadcrumb per meaningful tool call to the day's activity log
# and stamps per-skill last-use times. pattern-extractor.py, skill-lifecycle.py,
# the healthcheck and the reflect / harness-optimize skills all read this.
#
# Append-only. Fails open: never blocks a tool call, exits 0 on any input shape
# (Codex payloads may differ from Claude's; unknown shapes are simply skipped).
#
# Storage is machine-local and outside the repo, resolved ONLY through
# harness_paths.captures_dir() so every worktree writes to the same log:
#   <state_base>/captures/{YYYY-MM-DD}-activity.md
#   <state_base>/captures/skill-tracker.json
# Prompt text is never logged, only a leading /skill or $skill name.

set -u

INPUT=$(cat 2>/dev/null || echo "{}")
command -v python3 >/dev/null 2>&1 || exit 0

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || exit 0

HOOK_INPUT="$INPUT" PROJECT_ROOT="$PROJECT_ROOT" HOOK_DIR="$HOOK_DIR" \
  python3 - <<'PY' >/dev/null 2>&1 || true
import os, sys, json, datetime, re

# The heredoc owns stdin (it's the script source), so the payload comes via env.
try:
    d = json.loads(os.environ.get("HOOK_INPUT") or "{}")
except Exception:
    sys.exit(0)
if not isinstance(d, dict):
    sys.exit(0)

tool = str(d.get("tool_name") or d.get("tool") or "")
event = str(d.get("hook_event_name") or "PostToolUse")
ti = d.get("tool_input") or {}
if not isinstance(ti, dict):
    ti = {"command": ti} if isinstance(ti, (str, list)) else {}

root = os.environ.get("PROJECT_ROOT") or os.getcwd()
sys.path.insert(0, os.environ.get("HOOK_DIR", ""))
try:
    from harness_paths import captures_dir
    base = captures_dir(root)
    os.makedirs(base, exist_ok=True)
except Exception:
    sys.exit(0)


def short(s, n=120):
    return " ".join(str(s).split())[:n]


def stamp_skill(name):
    """Cadence clock, for the Skill tool AND typed /slash or $skill prompts."""
    tracker = os.path.join(base, "skill-tracker.json")
    try:
        data = json.load(open(tracker)) if os.path.exists(tracker) else {}
    except Exception:
        data = {}
    data[str(name)] = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        json.dump(data, open(tracker, "w"), indent=2)
    except Exception:
        pass


def command_of(ti):
    c = ti.get("command") or ti.get("cmd") or ""
    return " ".join(map(str, c)) if isinstance(c, list) else str(c)


# Secrets must never reach the activity log: redact values passed on the command line
# (`--value X`, `--body X`, `-p X`, `Bearer X`, `Basic X`, `KEY=value` for secret-looking
# keys, `?token=X` style URL params) and anything shaped like a known token, before a
# command, Grep pattern or fetched URL is summarised.
SECRET_ARG = re.compile(
    r"(--(?:value|body|token|password|db-password|secret|api-key)[= ]|-p\s+|Bearer\s+|Basic\s+|"
    r"[?&](?:access_token|token|api_?key|key|secret|password|signature|sig)=|"
    r"\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|DSN)[A-Z0-9_]*=)"
    r"(\"[^\"]*\"|'[^']*'|\S+)"
)
SECRET_SHAPE = re.compile(
    r"(sb_secret_\w+|sb_publishable_\w+|sk-ant-[\w-]+|ghp_\w+|github_pat_\w+|phx_\w+|"
    r"eyJ[\w-]{10,}\.[\w-]+\.[\w-]+|AKIA[0-9A-Z]{16})"
)


def redact(s):
    s = SECRET_ARG.sub(lambda m: m.group(1) + "[redacted]", s)
    return SECRET_SHAPE.sub("[redacted]", s)


summary = None
if event == "UserPromptSubmit":
    p = str(d.get("prompt") or "")
    m = re.match(r"\s*/([A-Za-z0-9_:.-]+)", p)
    if m:
        summary = f"Slash /{m.group(1)}"
        stamp_skill(m.group(1))
    else:
        # Codex invokes skills as `$name`. Only count it when that skill exists,
        # so "$HOME is wrong" is not mistaken for a skill run.
        m = re.match(r"\s*\$([A-Za-z0-9_-]+)", p)
        if m and os.path.isdir(os.path.join(root, ".agents", "skills", m.group(1))):
            summary = f"Skill /{m.group(1)}"
            stamp_skill(m.group(1))
elif tool == "Read":
    fp = str(ti.get("file_path") or "")
    if fp and not re.search(r"\.claude/(hooks|settings|harness)", fp) and "captures/" not in fp:
        summary = f"Read {fp}"
elif tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "apply_patch"):
    fp = ti.get("file_path") or ti.get("notebook_path") or ""
    summary = f"{tool} {fp}" if fp else (f"{tool}" if tool == "apply_patch" else None)
elif tool == "Grep":
    summary = f"Grep '{short(redact(ti.get('pattern', '')), 60)}'" + (f" in {ti.get('path')}" if ti.get("path") else "")
elif tool == "Glob":
    summary = f"Glob '{short(ti.get('pattern', ''), 60)}'"
elif tool in ("Bash", "shell", "local_shell", "exec_command"):
    cmd = short(redact(command_of(ti)), 140)
    if re.search(r"\b(git|rg|pytest|npm|npx|maestro|supabase|curl|python3?|gh|eas|railway|tsc|jest|ruff)\b", cmd):
        summary = f"Bash: {cmd}"
elif tool == "Skill":
    name = ti.get("skill") or ti.get("command") or ti.get("name") or ""
    if name:
        summary = f"Skill /{name}"
        stamp_skill(name)
elif tool in ("Agent", "Task"):
    at = ti.get("subagent_type") or ti.get("agentType") or "agent"
    summary = f"Agent[{at}] {short(ti.get('description') or ti.get('prompt', ''), 80)}"
elif tool.startswith("mcp__"):
    # Name the tool, never its arguments beyond one identifier: connector
    # arguments (mail, docs, notes) are private.
    parts = tool.split("__")
    server, op = (parts[1] if len(parts) > 2 else "?"), parts[-1]
    if re.fullmatch(r"[0-9a-f-]{36}", server):
        server = "connector"
    key = next((ti[k] for k in ("id", "identifier", "issueId")
                if isinstance(ti.get(k), str) and ti.get(k)), "")
    summary = f"MCP {server}:{op}" + (f" {short(key, 60)}" if key else "")
elif tool in ("WebSearch", "WebFetch"):
    summary = f"{tool} {short(redact(ti.get('query') or ti.get('url', '')), 80)}"
# Everything else (todo lists, tool-search plumbing) is noise.

if not summary:
    sys.exit(0)

# Mark explicit failures so a tool that always errors is visible in the raw layer.
resp = d.get("tool_response")
failed = False
if isinstance(resp, dict):
    failed = bool(resp.get("is_error") or resp.get("isError") or
                  (isinstance(resp.get("error"), str) and resp.get("error")))
elif isinstance(resp, str):
    failed = bool(re.match(r"\s*(Error|MCP error|<error>)", resp))
if failed:
    summary = "FAIL " + summary

now = datetime.datetime.now()
logf = os.path.join(base, now.strftime("%Y-%m-%d") + "-activity.md")
try:
    new = not os.path.exists(logf)
    with open(logf, "a") as f:
        if new:
            f.write(f"# Activity: {now.strftime('%Y-%m-%d')}\n\n")
        f.write(f"- {now.strftime('%H:%M')} {summary}\n")
except Exception:
    pass
PY

exit 0
