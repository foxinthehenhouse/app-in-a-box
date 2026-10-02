#!/usr/bin/env python3
"""Memory RECALL: surface the long-tail memory notes that match a prompt.

`.agents/memory/MEMORY.md` is a one-line index; the notes behind it are only read
when something points at one. This hook scores notes against each prompt and
prints up to MAX pointers (path, title, description), never note bodies:

  1. BM25 over each note's title, tags, description and body (fields weighted),
  2. one hop along `[[links]]`: a linked note inherits half its parent's score.

Adapted from vectorize-io/hindsight's `recall` (MIT), keeping only the two
deterministic strategies that need no infra. Deliberately quiet: a note must match
MIN_TERMS distinct terms, clear MIN_SCORE, and score within REL of the best hit,
and each note is recalled once per session. Fails open on any error.
APPBOX_MEMORY_RECALL=0 turns it off. Runnable by hand:

    python3 .claude/hooks/memory_recall.py "why did the sign-in redirect loop"
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parents[2] / ".agents" / "memory"
MAX = 3
MIN_TERMS = 2
MIN_SCORE = 9.0
# ...and within this fraction of the best hit. BM25 has a long flat tail of notes
# sharing two common words with the prompt; a relative cut drops it.
REL = 0.5
K1, B = 1.2, 0.75
# Field weights: implemented by repeating a field's tokens. A title hit says far
# more about relevance than a passing mention in the body.
WEIGHTS = {"title": 3, "tags": 2, "description": 2, "body": 1}

STOPWORDS = set("""
the and for are but not you all any can had her was one our out has have this that with from
they will would there their what when which who how why about into than then them these those
been being were does did doing done just also only very more most some such like make made use
used using get got its it's let lets want need should could into over under after before again
here where while each both few other own same too can't don't won't isn't it’s please thanks
claude codex code file files note notes run running work working session sessions
""".split())

TOKEN = re.compile(r"[a-z0-9][a-z0-9_+-]{2,}")
LINK = re.compile(r"\[\[([^\]|#]+)")
HARNESS_TURN = re.compile(
    r"<task-notification>|\[SYSTEM NOTIFICATION|<system-reminder>|<agent-message|\[Subagent hand-back\]"
)


def _stem(w: str) -> str:
    # Deliberately light: fold plurals and common verb endings only. An aggressive
    # stemmer merges "deload"/"deloading" fine but also "migration"/"migrate"/"mig".
    for suf in ("ing", "ies", "es", "ed", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokens(text: str) -> list[str]:
    out = []
    for w in TOKEN.findall(text.lower()):
        for part in re.split(r"[_-]", w):
            if len(part) >= 3 and part not in STOPWORDS:
                out.append(_stem(part))
    return out


def _key(name: str) -> str:
    return re.sub(r"[-_\s]+", "_", name.strip().lower())


def load_notes(memory_dir: Path = MEMORY_DIR) -> list[dict]:
    notes = []
    for p in sorted(memory_dir.glob("*.md")):
        if p.name == "MEMORY.md" or p.name.startswith("_"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = {}, text
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                for line in text[3:end].splitlines():
                    k, sep, v = line.partition(":")
                    if sep:
                        meta[k.strip()] = v.strip()
                body = text[end + 4 :]
        title = meta.get("title") or p.stem.replace("_", " ")
        fields = {
            "title": title,
            "tags": meta.get("tags", "").strip("[]"),
            "description": meta.get("description", ""),
            "body": body,
        }
        tf: Counter = Counter()
        for f, w in WEIGHTS.items():
            for t in tokens(fields[f]):
                tf[t] += w
        notes.append(
            {
                "path": f".agents/memory/{p.name}",
                "keys": {_key(p.stem), _key(meta.get("name", p.stem))},
                "title": title,
                "description": meta.get("description", ""),
                "tf": tf,
                "len": sum(tf.values()),
                "links": {_key(m) for m in LINK.findall(body)},
            }
        )
    return notes


def score(prompt: str, notes: list[dict]) -> list[tuple[float, int, dict]]:
    """BM25 per note, plus one graph hop. Returns (score, distinct_terms, note), best first."""
    q = set(tokens(prompt))
    if not q or not notes:
        return []
    n = len(notes)
    avg = sum(x["len"] for x in notes) / n or 1.0
    df = Counter(t for x in notes for t in q if t in x["tf"])
    scored: dict[int, tuple[float, int]] = {}
    for i, x in enumerate(notes):
        s, hit = 0.0, 0
        for t in q:
            f = x["tf"].get(t, 0)
            if not f:
                continue
            hit += 1
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * x["len"] / avg))
        if hit:
            scored[i] = (s, hit)
    # Graph hop: a note linked FROM a strong hit is likely relevant too, even when it
    # shares no words with the prompt (the "why" note behind a "what" note).
    by_key = {k: i for i, x in enumerate(notes) for k in x["keys"]}
    for i, (s, hit) in list(scored.items()):
        if hit < MIN_TERMS:
            continue
        for link in notes[i]["links"]:
            j = by_key.get(link)
            if j is None or j == i:
                continue
            inherited = (s * 0.5, hit)
            if inherited[0] > scored.get(j, (0.0, 0))[0]:
                scored[j] = inherited
    ranked = sorted(((s, h, notes[i]) for i, (s, h) in scored.items()), key=lambda r: -r[0])
    return ranked


def recall(prompt: str, session_id: str = "", memory_dir: Path = MEMORY_DIR) -> list[dict]:
    ranked = [
        r for r in score(prompt, load_notes(memory_dir)) if r[1] >= MIN_TERMS and r[0] >= MIN_SCORE
    ]
    if ranked:
        ranked = [r for r in ranked if r[0] >= ranked[0][0] * REL]
    seen_file = None
    seen: set[str] = set()
    if session_id:
        safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:64]
        seen_file = Path(tempfile.gettempdir()) / f"appbox-recall-{safe}.json"
        try:
            seen = set(json.loads(seen_file.read_text()))
        except (OSError, ValueError):
            seen = set()
    picked = [x for _, _, x in ranked if x["path"] not in seen][:MAX]
    if seen_file and picked:
        try:
            seen_file.write_text(json.dumps(sorted(seen | {x["path"] for x in picked})))
        except OSError:
            pass
    return picked


def render(notes: list[dict]) -> str:
    if not notes:
        return ""
    lines = "\n".join(
        f"- `{x['path']}` — {x['title']}"
        + (f": {x['description'][:200]}" if x["description"] else "")
        for x in notes
    )
    return (
        "### Memory recall\n"
        "These memory notes match this prompt. Read any that apply before acting; skip the rest.\n"
        + lines
    )


def main() -> int:
    if len(sys.argv) > 1:  # manual: python3 memory_recall.py "<prompt>"
        print(render(recall(" ".join(sys.argv[1:]))) or "(no note clears the recall threshold)")
        return 0
    if os.environ.get("APPBOX_MEMORY_RECALL", "1") == "0":
        return 0
    try:
        d = json.load(sys.stdin)
        prompt = str(d.get("prompt") or "")
        # Typed slash commands are explicit; harness-generated turns (notifications,
        # subagent hand-backs) are not the user asking anything. 
        if prompt.lstrip().startswith("/") or HARNESS_TURN.search(prompt):
            return 0
        out = render(recall(prompt, str(d.get("session_id") or "")))
    except Exception:
        return 0
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
