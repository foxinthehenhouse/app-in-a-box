#!/usr/bin/env python3
"""Install the recipe-ai-feature reference ("Ask your notes": pgvector RAG with citations)
into an App in a Box app, or tell you exactly which edit to make by hand.

    python3 <plugin root>/skills/recipe-ai-feature/reference/install.py <app dir> [--tracing]

Copies the reference files (the fenced module, the router, two migrations, a pgTAP test,
the tests and the eval set), then makes the wiring edits the app's own guards demand:
the AI fence in AGENTS.md and its map row, FEATURE_CONFIG, the router in main.py, the
data export, the wire contract pair + mobile/lib/api.ts types, the blanked test env, the
SDK pin, pgvector in the DB workflow and .env.example. `--tracing` also registers
Langfuse in FEATURE_CONFIG (tracing is off until that entry exists).

Each edit is anchored on template text and idempotent. When an anchor is missing (the
app has moved on from the template), the edit is skipped and listed at the end, and the
script exits 1: make those by hand, then run the app's tests. Nothing is ever guessed.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = "ai_ask"
FENCE = f"Claude API only in `backend/services/{MODULE}*`."
FEATURES = {
    "ai (Anthropic)": '("ANTHROPIC_API_KEY",)',
    "ai retrieval (embeddings)": '("EMBEDDINGS_API_KEY", "SUPABASE_ANON_KEY")',
}
TRACING = {"ai tracing (Langfuse)": '("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")'}
TEST_VARS = (
    "ANTHROPIC_API_KEY", "EMBEDDINGS_API_KEY", "EMBEDDINGS_BASE_URL", "EMBEDDINGS_MODEL",
    "AI_MODEL", "AI_DAILY_TOKEN_CAP", "AI_TRACE_CONTENT", "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
)  # fmt: skip
SDK_PIN = "anthropic>=1.11,<2"

todo: list[str] = []


def edit(path: Path, done_marker: str, apply, what: str) -> None:  # noqa: ANN001
    """Run `apply(text) -> text | None` unless `done_marker` is already there."""
    if not path.is_file():
        todo.append(f"{path.name}: missing; {what}")
        return
    text = path.read_text(encoding="utf-8")
    if done_marker in text:
        return
    new = apply(text)
    if new is None or new == text:
        todo.append(f"{path.relative_to(APP)}: {what}")
        return
    path.write_text(new, encoding="utf-8")


def insert_before(anchor: str, block: str):  # noqa: ANN201
    return lambda t: t.replace(anchor, block + anchor, 1) if anchor in t else None


def insert_after(anchor: str, block: str):  # noqa: ANN201
    return lambda t: t.replace(anchor, anchor + block, 1) if anchor in t else None


def dict_entries(name: str, entries: str):  # noqa: ANN201
    """Add entries before the closing brace of `NAME: ... = {`."""

    def apply(t: str) -> str | None:
        m = re.search(rf"^{name}\b[^=\n]*=\s*\{{\n", t, re.M)
        if not m:
            return None
        end = t.find("\n}\n", m.end())
        return None if end < 0 else t[: end + 1] + entries + t[end + 1 :]

    return apply


def list_entries(name: str, entries: str):  # noqa: ANN201
    def apply(t: str) -> str | None:
        m = re.search(rf"^{name}\b[^=\n]*=\s*\[\n", t, re.M)
        if not m:
            return None
        end = t.find("\n]\n", m.end())
        return None if end < 0 else t[: end + 1] + entries + t[end + 1 :]

    return apply


def copy_files() -> None:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M")
    existing = {p.name.split("_", 1)[1] for p in (APP / "supabase" / "migrations").glob("*.sql")}
    for src in sorted(HERE.rglob("*")):
        rel = src.relative_to(HERE)
        if src.is_dir() or rel.name in ("install.py",) or rel.suffix == ".pyc":
            continue
        if rel.name.endswith(".snippet.ts"):
            continue
        dest = APP / rel
        if rel.parts[:2] == ("supabase", "migrations"):
            body = rel.name.split("_", 1)[1]
            if body in existing:
                continue  # installed before (under its own timestamp)
            # Fresh versions, in the reference's order, after every existing migration.
            seq = sorted(p.name for p in (HERE / "supabase" / "migrations").glob("*.sql")).index(
                rel.name
            )
            dest = dest.with_name(f"{stamp}{seq:02d}_{body}")
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = src.read_text(encoding="utf-8")
        name = _app_name()
        dest.write_text(text.replace("__APP_NAME__", name), encoding="utf-8")


def _app_name() -> str:
    m = re.search(r"^# (.+?) API", (APP / "backend" / "main.py").read_text(), re.M)
    m = m or re.search(r'title="(.+?) API"', (APP / "backend" / "main.py").read_text())
    return m.group(1) if m else "App"


def wire() -> None:
    agents = APP / "AGENTS.md"

    def fence(t: str) -> str | None:
        new = re.sub(r"<!--\s*appbox:ai-fence:.*?-->", FENCE, t, count=1, flags=re.S)
        if new != t:
            return new
        return None

    edit(agents, FENCE, fence, f'rule 8: say "{FENCE}" (the AI fence)')
    edit(
        agents,
        f"`services/{MODULE}.py`",
        insert_before(
            "| Dev only |",
            f"| Ask your notes (AI) | | `routers/ask.py` | `services/{MODULE}.py` | `ai_chunks`, `ai_usage` |\n",
        ),
        "add a 'Where things live' row: routers/ask.py, services/ai_ask.py, `ai_chunks`, `ai_usage`",
    )
    features = dict(FEATURES, **(TRACING if "--tracing" in sys.argv else {}))
    cfg = APP / "backend" / "config.py"
    for name, reqs in features.items():
        edit(cfg, f'\n    "{name}": ', dict_entries("FEATURE_CONFIG", f'    "{name}": {reqs},\n'),
             f"FEATURE_CONFIG: add \"{name}\": {reqs}")  # fmt: skip

    main = APP / "backend" / "main.py"

    def router_import(t: str) -> str | None:
        m = re.search(r"^from backend\.routers import (.+?)(\s+# noqa: E402)?$", t, re.M)
        if not m:
            return None
        names = sorted({n.strip() for n in m.group(1).split(",")} | {"ask"})
        return (
            t[: m.start()]
            + f"from backend.routers import {', '.join(names)}{m.group(2) or ''}"
            + t[m.end() :]
        )

    edit(main, "import ask", router_import, "import backend.routers.ask")
    edit(main, "include_router(ask.router)", lambda t: _after_last(t, "    app.include_router(", "    app.include_router(ask.router)\n"),
         "app.include_router(ask.router) in create_app()")  # fmt: skip

    export = APP / "backend" / "routers" / "export.py"
    readers = """def _read_ai_chunks(db: Any, user_id: str, start: int, end: int) -> list[dict[str, Any]]:
    # The text the user indexed; the embedding is derived from it and omitted.
    return (
        db.table("ai_chunks")
        .select("source_id, title, ord, content, created_at")
        .eq("user_id", user_id)
        .order("id")
        .range(start, end)
        .execute()
        .data
        or []
    )


def _read_ai_usage(db: Any, user_id: str, start: int, end: int) -> list[dict[str, Any]]:
    return (
        db.table("ai_usage")
        .select("day, input_tokens, output_tokens")
        .eq("user_id", user_id)
        .order("day")
        .range(start, end)
        .execute()
        .data
        or []
    )


"""
    edit(export, "_read_ai_chunks", insert_before("# table -> scoped reader.", readers),
         "add scoped readers for ai_chunks and ai_usage")  # fmt: skip
    edit(export, '"ai_chunks": _read_ai_chunks', dict_entries("EXPORTERS", '    "ai_chunks": _read_ai_chunks,\n    "ai_usage": _read_ai_usage,\n'),
         "EXPORTERS: add ai_chunks and ai_usage")  # fmt: skip

    contract = APP / "tests" / "test_wire_contract.py"
    edit(contract, "from backend.routers.ask import", insert_before(
        "from backend.routers.export import",
        "from backend.routers.ask import AskAnswer, AskCitation, AskQuestion, AskSource, AskSourceIndexed\n"),
        "import the Ask models")  # fmt: skip
    edit(contract, '(AskAnswer, "AskAnswerWire")', list_entries("RESPONSE_PAIRS",
        '    (AskAnswer, "AskAnswerWire"),\n    (AskCitation, "AskCitationWire"),\n    (AskSourceIndexed, "AskSourceIndexedWire"),\n'),
        "RESPONSE_PAIRS: add the Ask response models")  # fmt: skip
    edit(contract, '(AskQuestion, "AskQuestionWire")', list_entries("REQUEST_PAIRS",
        '    (AskQuestion, "AskQuestionWire"),\n    (AskSource, "AskSourceWire"),\n'),
        "REQUEST_PAIRS: add the Ask request models")  # fmt: skip
    api_ts = APP / "mobile" / "lib" / "api.ts"
    snippet = (HERE / "mobile" / "lib" / "api-ask.snippet.ts").read_text(encoding="utf-8")
    edit(api_ts, "interface AskAnswerWire", lambda t: t.rstrip("\n") + "\n" + snippet,
         "append mobile/lib/api-ask.snippet.ts")  # fmt: skip

    conftest = APP / "tests" / "conftest.py"
    edit(conftest, '"ANTHROPIC_API_KEY"', lambda t: _extend_tuple(t, "_FEATURE_VARS", TEST_VARS),
         "blank the AI env vars in _FEATURE_VARS")  # fmt: skip
    health = APP / "tests" / "test_health.py"
    edit(health, '"EMBEDDINGS_API_KEY"', lambda t: t.replace(
        '("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SENTRY_DSN")',
        '("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SENTRY_DSN", "ANTHROPIC_API_KEY",\n                 "EMBEDDINGS_API_KEY", "SUPABASE_ANON_KEY")', 1),
        "test_health_ok_when_everything_wired: also set the AI keys")  # fmt: skip

    hardening = APP / "tests" / "test_prod_hardening.py"
    edit(hardening, '"EMBEDDINGS_API_KEY"', lambda t: t.replace(
        '    monkeypatch.setenv("SENTRY_DSN", "x")\n',
        '    monkeypatch.setenv("SENTRY_DSN", "x")\n'
        '    for name in ("ANTHROPIC_API_KEY", "EMBEDDINGS_API_KEY", "SUPABASE_ANON_KEY"):\n'
        '        monkeypatch.setenv(name, "x")\n'),
        "the /health deep tests: also set the AI keys")  # fmt: skip
    if "--tracing" in sys.argv:
        for path in (health, hardening):
            edit(path, '"LANGFUSE_PUBLIC_KEY"', lambda t: t.replace(
                '"SUPABASE_ANON_KEY"):', '"SUPABASE_ANON_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):'),
                "the /health tests: also set the Langfuse keys")  # fmt: skip

    edit(
        APP / "requirements.txt",
        "anthropic",
        lambda t: t.rstrip("\n") + f"\n{SDK_PIN}\n",
        f"pin {SDK_PIN}",
    )
    edit(APP / ".github" / "workflows" / "db.yml", "pgvector", lambda t: t.replace(
        '"postgresql-${PGV}-pgtap"', '"postgresql-${PGV}-pgtap" "postgresql-${PGV}-pgvector"', 1),
        "install postgresql-<v>-pgvector next to pgtap")  # fmt: skip
    edit(APP / ".env.example", "EMBEDDINGS_API_KEY", insert_after("ANTHROPIC_API_KEY=\n",
        "# AI retrieval: an OpenAI-compatible /embeddings provider (default Voyage AI). The\n"
        "# backend also needs SUPABASE_ANON_KEY (above) to query as the signed-in user.\n"
        "EMBEDDINGS_API_KEY=\nEMBEDDINGS_BASE_URL=\nEMBEDDINGS_MODEL=\n"
        "# Optional: AI_MODEL, AI_DAILY_TOKEN_CAP; tracing: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY\n"),
        "document EMBEDDINGS_* and the optional AI vars")  # fmt: skip
    dm = APP / "privacy" / "data-map.yaml"
    if dm.is_file():  # an app made before the data map has none to update
        edit(dm, "  ai_chunks:", data_map, "add the ai_usage / ai_chunks tables and the AI vendors")


# privacy/data-map.yaml: the tables the migrations add, and the vendors that now process
# the user's notes. Each block goes under its top-level section.
DATA_MAP = {
    "processors": """  anthropic:
    role: "answers your questions from your notes (it receives the question and the matching passages)"
  embeddings:
    role: "turns your notes into search vectors so the app can find the right passages"
""",
    "tables": """  ai_usage:
    owner: user
    columns:
      user_id: {category: identifier, purpose: "counts your daily AI use against the cap", retention: account}
      day: none
      input_tokens: {category: usage, purpose: "keep AI costs under the daily cap", retention: account}
      output_tokens: {category: usage, purpose: "keep AI costs under the daily cap", retention: account}
  ai_chunks:
    owner: user
    columns:
      id: none
      user_id: {category: identifier, purpose: "keeps your notes searchable only by you", retention: account}
      source_id: none
      title: {category: ugc, purpose: "cite which of your notes an answer came from", retention: account}
      ord: none
      content: {category: ugc, purpose: "find the passages of your notes that answer your question", retention: account}
      embedding: {category: ugc, purpose: "search your notes by meaning (a numeric form of their text)", retention: account}
      created_at: none
""",
}


def data_map(t: str) -> str | None:
    for section, block in DATA_MAP.items():
        m = re.search(rf"^{section}:[^\n]*\n", t, re.M)
        if not m:
            return None
        line = m.group(0) if m.group(0).strip() == f"{section}:" else f"{section}:\n"
        t = t[: m.start()] + line + block + t[m.end() :]
    return t


def regenerate_privacy() -> None:
    gen = APP / "scripts" / "check_data_map.py"
    if not gen.is_file():
        return
    r = subprocess.run([sys.executable, str(gen), "--write"], cwd=APP, capture_output=True, text=True)
    if r.returncode != 0:
        todo.append("privacy answers: run `python3 scripts/check_data_map.py --write` and fix what it says")


def _after_last(text: str, prefix: str, line: str) -> str | None:
    i = text.rfind(prefix)
    if i < 0:
        return None
    end = text.index("\n", i) + 1
    return text[:end] + line + text[end:]


def _extend_tuple(text: str, name: str, names: tuple[str, ...]) -> str | None:
    m = re.search(rf"^{name} = \(\n(.*?)^\)", text, re.M | re.S)
    if not m:
        return None
    add = "".join(f'    "{n}",\n' for n in names if f'"{n}"' not in m.group(1))
    return text[: m.end(1)] + add + text[m.end(1) :]


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1 or not (Path(args[0]) / "backend" / "config.py").is_file():
        sys.exit(__doc__)
    APP = Path(args[0]).resolve()
    copy_files()
    wire()
    regenerate_privacy()
    if todo:
        print("install.py: copied the files, but make these edits by hand:")
        print("\n".join(f"  - {t}" for t in todo))
        sys.exit(1)
    print("install.py: done. Next: pip install the new pin, run the tests, then fill in the")
    print("  owner decisions (model, cap, providers) and the privacy policy (see SKILL.md).")
