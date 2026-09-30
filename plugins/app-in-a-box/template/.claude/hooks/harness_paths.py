#!/usr/bin/env python3
"""The single source of truth for WHERE self-learning state lives.

Every harness script (capture, extractor, lifecycle, spend, healthcheck, the
reflect / harness-optimize skills) imports this instead of deriving a path. A
second derivation is how the first one drifts: a reader that looks in a
slightly different directory finds nothing and reports "0 corrections", which
is also what a healthy loop reports. Silence you can't distinguish from health.

Two rules, because writers and readers need opposite behaviour:

  - State CONVERGES. Captures, state.json and the pending-reflection seed belong
    to the *project*, not to a checkout, so every worktree writes to one place:
    `$APPBOX_STATE_DIR` or `${XDG_STATE_HOME:-~/.local/state}/appbox/<slug>/`.
    Outside the repo on purpose: it is activity, not source, and never dirties
    a branch. (Memory is different: it is git-tracked in `.agents/memory/`.)
  - Transcripts FAN IN. The agent owns where transcripts are written. Claude
    Code writes one dir per session cwd under `~/.claude/projects/`; Codex
    writes date-sharded rollouts under `~/.codex/sessions/`. Readers union them.

Both transcript locations are configurable in `.claude/harness/manifest.json`
(`transcripts`) and by env (`APPBOX_CLAUDE_PROJECTS_DIR`,
`APPBOX_CODEX_SESSIONS_GLOB`).

Must work with CLAUDE_PROJECT_DIR unset (Codex): falls back to
`git rev-parse --show-toplevel`, then the cwd.

    python3 .claude/hooks/harness_paths.py              # print the resolution
    python3 .claude/hooks/harness_paths.py stamp reflect  # record a ritual run
"""

import datetime
import glob
import json
import os
import re
import subprocess
import sys

WORKTREE_MARKER = "/.claude/worktrees/"  # the new-worktree skill's layout


def project_root(path=None):
    """The checkout this session is working in (a worktree, or the primary)."""
    p = path or os.environ.get("CLAUDE_PROJECT_DIR")
    if not p:
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=3
            )
            p = r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            p = ""
    return os.path.abspath(p or os.getcwd())


def canonical_root(path=None):
    """The PRIMARY checkout, from any worktree of it. No git subprocess when a
    path is given: capture calls this on every tool call."""
    p = project_root(path)
    i = p.find(WORKTREE_MARKER)
    if i != -1:
        return p[:i]
    # A worktree anywhere else (e.g. an agent's own worktree dir) has a `.git`
    # FILE pointing at `<primary>/.git/worktrees/<id>`. Plain file IO, no git.
    try:
        with open(os.path.join(p, ".git")) as f:
            m = re.match(r"gitdir:\s*(.+?)/\.git/worktrees/[^/]+/?\s*$", f.read())
        if m:
            return os.path.abspath(m.group(1))
    except Exception:
        pass
    return p


def slug(path):
    """Filesystem-safe project key: both `/` and `.` become `-` (Claude Code's own
    rule, so the Claude transcript dir and our state dir share one spelling)."""
    return re.sub(r"[/.]", "-", os.path.abspath(path))


def _state_parent():
    env = os.environ.get("APPBOX_STATE_DIR")
    if env:
        return os.path.expanduser(env)
    xdg = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(xdg, "appbox")


def state_base(path=None):
    return os.path.join(_state_parent(), slug(canonical_root(path)))


def captures_dir(path=None):
    return os.path.join(state_base(path), "captures")


def state_file(path=None):
    return os.path.join(state_base(path), "state.json")


def pending_reflection_file(path=None):
    return os.path.join(state_base(path), "pending_reflection.md")


def memory_dir(path=None):
    """Git-tracked memory of the CURRENT checkout (it travels with the branch)."""
    return os.path.join(project_root(path), ".agents", "memory")


def manifest(path=None):
    try:
        with open(os.path.join(project_root(path), ".claude", "harness", "manifest.json")) as f:
            return json.load(f)
    except Exception:
        return {}


def _transcript_cfg(path=None):
    return manifest(path).get("transcripts") or {}


def claude_projects_dir(path=None):
    d = (
        os.environ.get("APPBOX_CLAUDE_PROJECTS_DIR")
        or _transcript_cfg(path).get("claude_projects_dir")
        or "~/.claude/projects"
    )
    return os.path.expanduser(d)


# The worktree marker must follow the base slug IMMEDIATELY: a `*` filler would let
# a sibling repo (`<root>-marketing`) leak its transcripts into this project's signal.
_WORKTREE_SLUG_SUFFIX = "--claude-worktrees-"


def claude_transcript_dirs(path=None):
    """Claude Code transcript dirs: the primary checkout + each worktree's."""
    projects = claude_projects_dir(path)
    base = slug(canonical_root(path))
    out = [os.path.join(projects, base)]
    out += sorted(
        d
        for d in glob.glob(os.path.join(projects, base + _WORKTREE_SLUG_SUFFIX + "*"))
        if os.path.isdir(d)
    )
    return out


# Back-compat name used by every reader.
transcript_dirs = claude_transcript_dirs


def _codex_session_cwd(fp):
    """cwd recorded in a Codex rollout's `session_meta` line, or None.

    Codex rollouts are JSONL whose first record is
    `{"type": "session_meta", "payload": {"cwd": ...}}`. If that shape is absent
    (format changed, other tool), we return None and the file is SKIPPED: better
    no Codex signal than another project's signal."""
    try:
        with open(fp, errors="replace") as f:
            for _ in range(5):
                line = f.readline()
                if not line:
                    break
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if isinstance(d, dict) and d.get("type") == "session_meta":
                    cwd = (d.get("payload") or {}).get("cwd")
                    return cwd if isinstance(cwd, str) else None
    except Exception:
        pass
    return None


def codex_transcripts(path=None, since_ts=0.0):
    """Codex rollout files for THIS project modified since `since_ts`.

    Off when manifest `transcripts.codex` is false. Location defaults to
    `~/.codex/sessions/**/*.jsonl` (override: manifest `codex_sessions_glob` or
    APPBOX_CODEX_SESSIONS_GLOB)."""
    cfg = _transcript_cfg(path)
    if cfg.get("codex") is False:
        return []
    pattern = os.path.expanduser(
        os.environ.get("APPBOX_CODEX_SESSIONS_GLOB")
        or cfg.get("codex_sessions_glob")
        or "~/.codex/sessions/**/*.jsonl"
    )
    root = canonical_root(path)
    out = []
    try:
        files = glob.glob(pattern, recursive=True)
    except Exception:
        return []
    for fp in files:
        try:
            if os.path.getmtime(fp) < since_ts:
                continue
        except OSError:
            continue
        cwd = _codex_session_cwd(fp)
        if cwd and canonical_root(cwd) == root:
            out.append(fp)
    return sorted(out)


def orphan_capture_silos(path=None):
    """State dirs keyed on a WORKTREE path that hold capture logs, i.e. some
    writer resolved its own path instead of canonical_root(). Should be empty."""
    parent = _state_parent()
    base = slug(canonical_root(path))
    out = []
    for d in glob.glob(os.path.join(parent, base + _WORKTREE_SLUG_SUFFIX + "*")):
        c = os.path.join(d, "captures")
        if glob.glob(os.path.join(c, "*-activity.md")):
            out.append(c)
    return sorted(out)


def load_state(path=None):
    try:
        with open(state_file(path)) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(data, path=None):
    p = state_file(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, p)


def stamp(ritual, path=None):
    """Record that a ritual (reflect, harness-optimize) just completed."""
    d = load_state(path)
    d.setdefault("last_run", {})[ritual] = datetime.datetime.now().isoformat(timespec="seconds")
    save_state(d, path)
    return d


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "stamp":
        stamp(sys.argv[2])
        print(f"stamped {sys.argv[2]} in {state_file()}")
        sys.exit(0)
    print(
        json.dumps(
            {
                "project_root": project_root(),
                "canonical_root": canonical_root(),
                "state_base": state_base(),
                "captures_dir": captures_dir(),
                "pending_reflection": pending_reflection_file(),
                "memory_dir": memory_dir(),
                "claude_transcript_dirs": claude_transcript_dirs(),
                "codex_transcripts_14d": len(
                    codex_transcripts(since_ts=datetime.datetime.now().timestamp() - 14 * 86400)
                ),
                "orphan_capture_silos": orphan_capture_silos(),
            },
            indent=2,
        )
    )
