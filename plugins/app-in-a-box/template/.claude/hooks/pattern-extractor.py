#!/usr/bin/env python3
"""EXTRACT: turn session transcripts + capture logs into signal.

Produces the structured signal that `reflect` and `harness-optimize` act on:

  corrections        user push-backs / redirects (high-precision heuristics)
  challenges         push-backs phrased as QUESTIONS ("are you sure", "did you
                     actually"). Separate so widening recall here never costs
                     precision on `corrections`.
  tool_failures      calls the agent itself flagged as errors. Authoritative.
  tool_failures_suspected
                     calls that SUCCEEDED but whose result text looked
                     failure-ish. Low precision; corroborate before acting.
  hook_failures      hooks that crashed (non-blocking, so otherwise silent)
  correction_themes  recurring keywords across corrections + challenges
  skill_usage / tool_usage

Precision over recall: downstream automation acts on corrections, so a noisy
signal is worse than a sparse one.

Sources (all via harness_paths, never re-derived here):
  - Claude Code transcripts: every dir from claude_transcript_dirs() (primary
    checkout + each worktree).
  - Codex rollouts: codex_transcripts(). BEST-EFFORT: only user messages
    (`response_item` / `message` / role `user`, `input_text` blocks) and tool
    names (`function_call`) are read. Codex tool failures, hook failures and
    skill calls are NOT parsed, because their record shapes aren't stable
    enough to trust; any record we don't recognise is skipped, never guessed.

`transcripts_scanned` is a connectivity assertion: 0 means DISCONNECTED, not
clean. Never read "0 corrections" off a zero there.

    python3 .claude/hooks/pattern-extractor.py --days 7 --output json
    python3 .claude/hooks/pattern-extractor.py --days 14 --output text
"""

import argparse
import collections
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_paths import captures_dir, claude_transcript_dirs, codex_transcripts  # noqa: E402

CORRECTION_CUES = re.compile(
    r"^(no\b|nope\b|don'?t\b|stop\b|actually\b|wait\b|wrong\b|not\s|instead\b|"
    r"revert\b|undo\b|that'?s not\b|why did|you (shouldn'?t|didn'?t|were|keep)\b)",
    re.I,
)
CORRECTION_ANYWHERE = re.compile(
    r"\b(should have|shouldn'?t have|not what i|that'?s wrong|don'?t do that|"
    r"i said|i told you|stop doing|undo that|revert that|that'?s not right|"
    r"not like that|no need to|didn'?t ask)\b",
    re.I,
)
# Challenges: push-backs on a CLAIM ("did you really fix all of them?"). Often the
# highest-value signal a session produces, and invisible to a declarative detector.
CHALLENGE_CUES = re.compile(
    r"\b(are you sure|can'?t you|couldn'?t you|why can'?t you|why did(n'?t)? you|"
    r"did you (actually|really|even|check|verify|test|run|fix)|"
    r"is that (right|correct|true)|i thought you|you said|"
    r"shouldn'?t (you|it|that)|have you (actually|even|checked|verified))\b",
    re.I,
)
# A guess about result CONTENT, never a verdict about the call: a Read of any file
# with error handling matches. Feeds `tool_failures_suspected` only.
FAILURE_TEXT = re.compile(
    r"\b(error|failed|exception|traceback|not found|permission denied|exit code [1-9])\b",
    re.I,
)
# Machinery, not hand-typed text (incl. Codex's injected context blocks).
NOISE_MARKERS = re.compile(
    r"<command-name>|<system-reminder>|<local-command|tool_use_id|"
    r"<environment_context>|<user_instructions>|<user_shell_command>|"
    r"\[Request interrupted|caveat:|```",
    re.I,
)
THEME_WORDS = re.compile(r"\b([a-z]{4,})\b")
STOPWORDS = set(
    "that this with from have just dont don't your what when then than them they "
    "actually instead should would could there their about into your you the and "
    "but not for was were are use using used like need want make made does did "
    "right wrong because before after again still also only even more most some "
    "thing things stuff really very much".split()
)


def _clean(text):
    t = (text or "").strip()
    if not t or len(t) > 200 or NOISE_MARKERS.search(t):
        return None
    if t.startswith("/") or t.startswith("$") or t.count("\n") > 4:
        return None
    return t


def is_correction(text):
    t = _clean(text)
    # A long message that merely contains a cue word is an instruction, not a fix;
    # so is "x: <long body>".
    if not t or re.search(r":\s*\S.{40,}", t):
        return False
    return bool(CORRECTION_CUES.search(t) or CORRECTION_ANYWHERE.search(t))


def is_challenge(text):
    t = _clean(text)
    return bool(t) and not is_correction(t) and bool(CHALLENGE_CUES.search(t))


def user_text(content):
    """Hand-typed user text from a Claude message content (str or block list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for blk in content:
            if isinstance(blk, dict):
                if blk.get("type") == "tool_result":
                    return None
                if blk.get("type") == "text":
                    parts.append(str(blk.get("text", "")))
            elif isinstance(blk, str):
                parts.append(blk)
        return "\n".join(parts) if parts else None
    return None


def hook_failure_key(att):
    blob = " ".join(str(att.get(k) or "") for k in ("command", "hookName", "stderr"))
    m = re.search(r"hooks/([\w.-]+)", blob)
    script = m.group(1) if m else str(att.get("hookName") or "?")
    return f"{att.get('hookEvent') or att.get('hookName') or '?'} · {script} · exit {att.get('exitCode')}"


def _jsonl(fp):
    try:
        with open(fp, errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if isinstance(d, dict):
                    yield d
    except Exception:
        return


class Signal:
    def __init__(self):
        self.corrections, self.challenges = [], []
        self._seen_corr, self._seen_chal = set(), set()
        self.tool_failures = collections.Counter()
        self.tool_failures_suspected = collections.Counter()
        self.hook_failures = collections.Counter()
        self.tool_usage = collections.Counter()
        self.skill_usage = collections.Counter()

    def user_said(self, txt):
        if not txt:
            return
        key = re.sub(r"\s+", " ", txt.strip().lower())[:120]
        if is_correction(txt):
            if key not in self._seen_corr:
                self._seen_corr.add(key)
                self.corrections.append(" ".join(txt.split())[:280])
        elif is_challenge(txt):
            if key not in self._seen_chal:
                self._seen_chal.add(key)
                self.challenges.append(" ".join(txt.split())[:280])


def read_claude(fp, s):
    id_to_tool = {}
    for d in _jsonl(fp):
        att = d.get("attachment") if d.get("type") == "attachment" else None
        if isinstance(att, dict) and att.get("type") == "hook_non_blocking_error":
            s.hook_failures[hook_failure_key(att)] += 1
        msg = d.get("message")
        if not isinstance(msg, dict):
            continue
        role, content = msg.get("role"), msg.get("content")
        if role == "assistant" and isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    name = str(blk.get("name", "?"))
                    s.tool_usage[name] += 1
                    id_to_tool[blk.get("id")] = name
                    if name == "Skill":
                        inp = blk.get("input") or {}
                        sk = inp.get("skill") or inp.get("command") or inp.get("name")
                        if sk:
                            s.skill_usage[str(sk)] += 1
        if role == "user" and isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") == "tool_result":
                    body = blk.get("content")
                    text = body if isinstance(body, str) else json.dumps(body)
                    tname = id_to_tool.get(blk.get("tool_use_id"), "unknown")
                    if blk.get("is_error"):
                        s.tool_failures[tname] += 1
                    elif FAILURE_TEXT.search(text or ""):
                        s.tool_failures_suspected[tname] += 1
        if role == "user":
            s.user_said(user_text(content))


def read_codex(fp, s):
    """Best-effort; unknown record shapes are skipped (see module docstring)."""
    for d in _jsonl(fp):
        if d.get("type") != "response_item":
            continue
        p = d.get("payload")
        if not isinstance(p, dict):
            continue
        if (
            p.get("type") == "message"
            and p.get("role") == "user"
            and isinstance(p.get("content"), list)
        ):
            txt = "\n".join(
                str(b.get("text", ""))
                for b in p["content"]
                if isinstance(b, dict) and b.get("type") == "input_text"
            )
            s.user_said(txt)
        elif p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
            s.tool_usage[f"codex:{p.get('name') or p.get('type')}"] += 1


def extract(days, root=None):
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()
    claude_files = []
    for d in claude_transcript_dirs(root):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            fp = os.path.join(d, fn)
            try:
                if fn.endswith(".jsonl") and os.path.getmtime(fp) >= cutoff:
                    claude_files.append(fp)
            except OSError:
                continue
    codex_files = codex_transcripts(root, cutoff)

    s = Signal()
    for fp in claude_files:
        read_claude(fp, s)
    for fp in codex_files:
        read_codex(fp, s)

    themes = collections.Counter()
    for c in s.corrections + s.challenges:
        for w in set(THEME_WORDS.findall(c.lower())):
            if w not in STOPWORDS:
                themes[w] += 1

    # Skills used outside the sampled transcripts (typed /slash, $skill, older days).
    tracker = os.path.join(captures_dir(root), "skill-tracker.json")
    try:
        for k in json.load(open(tracker)):
            s.skill_usage.setdefault(k, 0)
    except Exception:
        pass

    return {
        "window_days": days,
        "transcripts_scanned": len(claude_files) + len(codex_files),
        "transcripts_by_agent": {"claude": len(claude_files), "codex": len(codex_files)},
        "corrections": s.corrections,
        "challenges": s.challenges,
        "correction_themes": {w: n for w, n in themes.most_common(12) if n >= 2},
        "tool_failures": dict(s.tool_failures.most_common()),
        "tool_failures_suspected": dict(s.tool_failures_suspected.most_common()),
        "hook_failures": dict(s.hook_failures.most_common()),
        "skill_usage": dict(s.skill_usage.most_common()),
        "tool_usage": dict(s.tool_usage.most_common()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--output", choices=["json", "text"], default="json")
    args = ap.parse_args()
    res = extract(args.days)

    if args.output == "json":
        print(json.dumps(res, indent=2))
        return
    by = res["transcripts_by_agent"]
    print(
        f"# Pattern extract: last {res['window_days']}d "
        f"({res['transcripts_scanned']} transcripts: {by['claude']} Claude, {by['codex']} Codex)\n"
    )
    if res["transcripts_scanned"] == 0:
        print(
            "!! 0 transcripts: the signal source is DISCONNECTED (or this is a fresh\n"
            "   install). Every count below is meaningless, not reassuring.\n"
        )
    print(f"## Corrections ({len(res['corrections'])})")
    for c in res["corrections"]:
        print(f"  - {c}")
    print(f"\n## Challenges: push-backs phrased as questions ({len(res['challenges'])})")
    for c in res["challenges"]:
        print(f"  - {c}")
    sections = [
        ("correction_themes", "Recurring themes (>=2)", None),
        ("tool_failures", "Tool failures (flagged as errors by the agent)", None),
        (
            "tool_failures_suspected",
            "Suspected: result TEXT looked failure-ish, call did NOT error",
            "   Low precision by construction; corroborate before acting on it.",
        ),
        ("hook_failures", "Hook failures (non-blocking, so otherwise silent)", None),
        ("skill_usage", "Skill usage", None),
        ("tool_usage", "Tool usage", None),
    ]
    for key, title, note in sections:
        if res[key] or key in ("skill_usage", "tool_usage"):
            print(f"\n## {title}")
            if note:
                print(note)
            for k, n in res[key].items():
                print(f"  - {k}: {n}")


if __name__ == "__main__":
    main()
