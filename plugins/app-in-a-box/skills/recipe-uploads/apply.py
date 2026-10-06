#!/usr/bin/env python3
"""Apply the recipe-uploads skill to an App in a Box app.

    python3 <plugin root>/skills/recipe-uploads/apply.py <app root>

1. Copies `files/` into the app: new files only (an existing one is left alone and
   reported), with the migration named for the current UTC time so it sorts after
   every migration the app already has.
2. Makes the wiring edits in files the app already has (router registration, the
   bucket in erasure_service.USER_FILE_BUCKETS so account deletion empties it, data
   export, wire-contract pairs, AGENTS.md map row, the DB negative control, the mobile
   API adapters, analytics event, demo routes, strings, the expo-image-picker config
   plugin, the privacy data map entries; and, for an app rendered before the kit
   stubbed Storage, the Storage stubs and test fake). Snippets live in `snippets/`.
3. Regenerates the privacy answers from the data map (the app's own
   `scripts/check_data_map.py --write`), so its CI sees them current.

Every edit is idempotent: a file that already has it is skipped, so re-running is
safe. Each edit is anchored on text the template ships; if the app has reworked that
file and the anchor is gone, NOTHING is written and the script names each edit to
make by hand (SKILL.md describes them too). It installs nothing: run
`npx expo install expo-image-picker` in mobile/ yourself.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = HERE / "files"
SNIPPETS = HERE / "snippets"
KIT = HERE.parents[
    1
]  # the plugin root: skills/recipe-uploads/ -> plugins/app-in-a-box/
STUBS = KIT / "template" / "supabase" / "ci" / "platform_stubs.sql"
FAKES = KIT / "template" / "tests" / "test_prod_fakes.py"


class Missing(Exception):
    """An anchor the edit needs is not in the file: do this edit by hand."""


def snippet(name: str) -> str:
    return (SNIPPETS / name).read_text(encoding="utf-8")


def insert_after(text: str, anchor: str, new: str, what: str) -> str:
    i = text.find(anchor)
    if i < 0:
        raise Missing(f"{what}: anchor not found: {anchor.strip()!r}")
    j = i + len(anchor)
    return text[:j] + new + text[j:]


def insert_before(text: str, anchor: str, new: str, what: str, start: int = 0) -> str:
    i = text.find(anchor, start)
    if i < 0:
        raise Missing(f"{what}: anchor not found: {anchor.strip()!r}")
    return text[:i] + new + text[i:]


def block_end(text: str, opener: str, closer: str, what: str) -> int:
    """Index of the first `closer` after `opener` (e.g. the `}` closing a dict literal)."""
    i = text.find(opener)
    if i < 0:
        raise Missing(f"{what}: anchor not found: {opener!r}")
    j = text.find(closer, i + len(opener))
    if j < 0:
        raise Missing(f"{what}: no {closer!r} after {opener!r}")
    return j


# ---- backend ---------------------------------------------------------------------------


def edit_main(t: str) -> str:
    m = re.search(
        r"^from backend\.routers import ([\w, ]+?)(\s+# noqa: E402)?$", t, re.M
    )
    if not m:
        raise Missing(
            "backend/main.py: add `uploads` to `from backend.routers import ...`"
        )
    names = sorted({*(n.strip() for n in m.group(1).split(",")), "uploads"})
    t = (
        t[: m.start()]
        + f"from backend.routers import {', '.join(names)}{m.group(2) or ''}"
        + t[m.end() :]
    )
    calls = list(re.finditer(r"^( +)app\.include_router\(\w+\.router\)\n", t, re.M))
    if not calls:
        raise Missing(
            "backend/main.py: add `app.include_router(uploads.router)` in create_app()"
        )
    last = calls[-1]
    return (
        t[: last.end()]
        + f"{last.group(1)}app.include_router(uploads.router)\n"
        + t[last.end() :]
    )


USER_FILE_BUCKETS = re.compile(
    r"^USER_FILE_BUCKETS: tuple\[str, \.\.\.\] = \(([^)]*)\)$", re.M
)
UPLOADS_LISTED = re.compile(r'^USER_FILE_BUCKETS: [^\n]*"uploads"', re.M)


def edit_erasure(t: str) -> str:
    """Account deletion empties every bucket in USER_FILE_BUCKETS (purge_storage(), before
    the auth user goes), so registering the bucket there is the whole deletion wiring."""
    m = USER_FILE_BUCKETS.search(t)
    if not m:
        raise Missing(
            'backend/services/erasure_service.py: add "uploads" to USER_FILE_BUCKETS'
        )
    names = [n.strip() for n in m.group(1).split(",") if n.strip()] + ['"uploads"']
    listed = ", ".join(names) + ("," if len(names) == 1 else "")  # ("uploads",) is a tuple
    return t[: m.start(1)] + listed + t[m.end(1) :]


def edit_export(t: str) -> str:
    what = "backend/routers/export.py"
    m = re.search(r"^from backend\.services import ([\w, ]+)$", t, re.M)
    if m:  # join the existing import, kept sorted (ruff's isort)
        names = sorted({*(n.strip() for n in m.group(1).split(",")), "uploads_service"})
        t = t[: m.start(1)] + ", ".join(names) + t[m.end(1) :]
    else:
        t = insert_after(
            t,
            "from backend.routers.me import Wire\n",
            "from backend.services import uploads_service\n",
            what,
        )
    t = insert_before(
        t,
        "# table -> scoped reader.",
        snippet("export.py"),
        f"{what}: add _read_uploads",
    )
    end = block_end(t, "EXPORTERS: dict[str, Reader] = {", "\n}", f"{what}: EXPORTERS")
    return t[:end] + '\n    "uploads": _read_uploads,' + t[end:]


def edit_wire_contract(t: str) -> str:
    what = "tests/test_wire_contract.py"
    imports = list(re.finditer(r"^from backend\.routers\.\w+ import .+\n", t, re.M))
    if not imports:
        raise Missing(f"{what}: import Upload, UploadList, UploadRequest, UploadTicket")
    last = imports[-1]
    t = (
        t[: last.end()]
        + "from backend.routers.uploads import Upload, UploadList, UploadRequest, UploadTicket\n"
        + t[last.end() :]
    )
    end = block_end(
        t,
        "RESPONSE_PAIRS: list[tuple[type[BaseModel], str]] = [",
        "\n]",
        f"{what}: RESPONSE_PAIRS",
    )
    t = (
        t[:end]
        + '\n    (UploadTicket, "UploadTicketWire"),\n    (Upload, "UploadWire"),\n    (UploadList, "UploadListWire"),'
        + t[end:]
    )
    end = block_end(
        t,
        "REQUEST_PAIRS: list[tuple[type[BaseModel], str]] = [",
        "\n]",
        f"{what}: REQUEST_PAIRS",
    )
    return t[:end] + '\n    (UploadRequest, "UploadRequestWire"),' + t[end:]


AGENTS_ROW = (
    "| Image uploads | `components/ui/ImageUpload.tsx`, `lib/uploads.ts` | `routers/uploads.py` "
    "| `services/uploads_service.py` | `uploads` (files: the private `uploads` Storage bucket) |\n"
)


def edit_agents(t: str) -> str:
    m = re.search(r"^## Where things live\s*$(.*?)(?=^## |\Z)", t, re.M | re.S)
    rows = list(re.finditer(r"^\|.*\|\n", m.group(1), re.M)) if m else []
    if not m or len(rows) < 3:
        raise Missing(
            "AGENTS.md: add an 'Image uploads' row to the '## Where things live' table"
        )
    at = m.start(1) + rows[-1].end()
    dev = next((r for r in rows if r.group(0).startswith("| Dev only")), None)
    if dev:  # keep the dev-only row last
        at = m.start(1) + dev.start()
    return t[:at] + AGENTS_ROW + t[at:]


def edit_negative_control(t: str) -> str:
    return t.rstrip("\n") + "\n" + snippet("negative_control.sql")


def edit_stubs(t: str) -> str:
    """An app rendered before the kit stubbed Storage gets the kit's storage section."""
    kit = STUBS.read_text(encoding="utf-8")
    i = kit.find("-- Storage:")
    if i < 0:
        raise Missing(
            "supabase/ci/platform_stubs.sql: copy the Storage stubs from the kit template"
        )
    return t.rstrip("\n") + "\n\n" + kit[i:]


def edit_fakes(t: str) -> str:
    """An app rendered before the kit's FakeDB grew a Storage gets the kit's fake."""
    what = "tests/test_prod_fakes.py: add the kit's FakeBucket/FakeStorage and FakeDB.storage"
    kit = FAKES.read_text(encoding="utf-8")
    i, j = kit.find("class FakeBucket:"), kit.find("class FakeDB:")
    if i < 0 or j < 0:
        raise Missing(what)
    t = insert_before(t, "class FakeDB:", kit[i:j], what)
    return insert_after(t, "        self.auth = FakeAuth()\n", "        self.storage = FakeStorage()\n", what)


# ---- mobile ----------------------------------------------------------------------------


def edit_api(t: str) -> str:
    return t.rstrip("\n") + "\n" + snippet("api.ts")


def edit_analytics(t: str) -> str:
    end = block_end(
        t,
        "export const analytics = {",
        "\n};",
        "mobile/lib/analytics.ts: the analytics object",
    )
    return t[:end] + "\n" + snippet("analytics.ts").rstrip("\n") + t[end:]


def edit_demo(t: str) -> str:
    return insert_after(
        t,
        "const ROUTES: Record<string, Handler> = {\n",
        snippet("demo.ts"),
        "mobile/lib/demo.ts: ROUTES",
    )


def edit_en(t: str) -> str:
    end = block_end(
        t, "export const en = {", "\n} as const;", "mobile/locales/en.ts: the en object"
    )
    t = t[:end] + "\n" + snippet("en.ts").rstrip("\n") + t[end:]
    # The deletion screen says what goes; photos go too. Soft: skip if the copy changed.
    return t.replace(
        "Your profile, settings and devices",
        "Your profile, photos, settings and devices",
        1,
    )


def edit_ui_index(t: str) -> str:
    line = 'export { ImageUpload, type ImageUploadProps } from "./ImageUpload";\n'
    anchor = 'export { Icon } from "./Icon";\n'
    return (
        insert_after(t, anchor, line, "mobile/components/ui/index.ts")
        if anchor in t
        else t + line
    )


PICKER_PLUGIN = [
    "expo-image-picker",
    {
        "photosPermission": "Lets you choose photos to upload.",
        "cameraPermission": False,
        "microphonePermission": False,
    },
]


def edit_app_json(t: str) -> str:
    data = json.loads(t)
    plugins = data.get("expo", {}).setdefault("plugins", [])
    plugins.append(PICKER_PLUGIN)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def edit_data_map(t: str) -> str:
    """The uploads table, its analytics event and the photo-library permission, each under
    its section of privacy/data-map.yaml (the app's guard fails until they're there)."""
    blocks = re.split(r"^## (\w+)\n", snippet("data-map.yaml"), flags=re.M)[1:]
    for section, block in zip(blocks[::2], blocks[1::2], strict=True):
        m = re.search(rf"^{section}:[^\n]*\n", t, re.M)
        if not m:
            raise Missing(f"privacy/data-map.yaml: add the recipe's {section} entries (snippets/data-map.yaml)")
        line = m.group(0)
        if line.strip() != f"{section}:":  # `analytics: {}` and friends: make it a block
            line = f"{section}:\n"
        t = t[: m.start()] + line + block + t[m.end() :]
    return t


# (path, already-applied marker, edit). A file containing its marker (a substring, or a
# pattern that matches) is skipped.
EDITS: list[tuple[str, str | re.Pattern[str], Callable[[str], str]]] = [
    ("backend/main.py", "uploads.router", edit_main),
    ("backend/services/erasure_service.py", UPLOADS_LISTED, edit_erasure),
    ("backend/routers/export.py", "_read_uploads", edit_export),
    ("tests/test_wire_contract.py", "UploadTicketWire", edit_wire_contract),
    ("tests/test_prod_fakes.py", "class FakeStorage", edit_fakes),
    ("AGENTS.md", "routers/uploads.py", edit_agents),
    ("supabase/ci/negative_control.sql", "recipe-uploads", edit_negative_control),
    (
        "supabase/ci/platform_stubs.sql",
        "create schema if not exists storage",
        edit_stubs,
    ),
    ("mobile/lib/api.ts", "UploadTicketWire", edit_api),
    ("mobile/lib/analytics.ts", "imageUploaded", edit_analytics),
    ("mobile/lib/demo.ts", '"POST /api/v1/uploads"', edit_demo),
    ("mobile/locales/en.ts", "uploads: {", edit_en),
    ("mobile/components/ui/index.ts", "./ImageUpload", edit_ui_index),
    ("mobile/app.json", '"expo-image-picker"', edit_app_json),
]
# Edits to files an app made before that file existed won't have: skipped, not missing.
OPTIONAL_EDITS: list[tuple[str, str | re.Pattern[str], Callable[[str], str]]] = [
    ("privacy/data-map.yaml", "image_uploaded", edit_data_map),
]


def plan_copies(app: Path) -> list[tuple[Path, Path]]:
    copies = []
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    have_migration = any((app / "supabase" / "migrations").glob("*_uploads.sql"))
    for src in sorted(p for p in FILES.rglob("*") if p.is_file()):
        rel = src.relative_to(FILES)
        if rel.name.startswith("TIMESTAMP_"):
            if have_migration:
                continue
            rel = rel.with_name(rel.name.replace("TIMESTAMP", stamp, 1))
        copies.append((src, app / rel))
    return copies


def regenerate_privacy(app: Path) -> list[str]:
    """Re-run the app's privacy generator: the new table, event and permission change the
    store answers, PrivacyInfo entries and policy draft. Returns what it rewrote."""
    gen = app / "scripts" / "check_data_map.py"
    if not (gen.is_file() and (app / "privacy" / "data-map.yaml").is_file()):
        return []
    r = subprocess.run([sys.executable, str(gen), "--write"], cwd=app, capture_output=True, text=True)
    if r.returncode != 0:
        print("recipe-uploads: couldn't regenerate the privacy answers; run `python3 scripts/check_data_map.py --write`:")
        print(r.stdout + r.stderr)
        return []
    return [ln.split("wrote ", 1)[1] for ln in r.stdout.splitlines() if ln.startswith("wrote ")]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.split("\n\n")[1])
        return 2
    app = Path(argv[1]).resolve()
    if (
        not (app / "backend" / "main.py").is_file()
        or not (app / "mobile" / "lib" / "api.ts").is_file()
    ):
        print(
            f"recipe-uploads: {app} doesn't look like an App in a Box app (no backend/main.py or mobile/lib/api.ts)"
        )
        return 2

    # Plan every edit in memory first: one missing anchor and nothing is written.
    writes: dict[Path, str] = {}
    missing: list[str] = []
    skipped: list[str] = []
    for rel, marker, edit in EDITS + OPTIONAL_EDITS:
        path = app / rel
        if not path.is_file():
            if (rel, marker, edit) not in OPTIONAL_EDITS:
                missing.append(f"{rel}: file not found")
            continue
        text = path.read_text(encoding="utf-8")
        if marker.search(text) if isinstance(marker, re.Pattern) else marker in text:
            skipped.append(rel)
            continue
        try:
            writes[path] = edit(text)
        except Missing as exc:
            missing.append(str(exc))
    if missing:
        print(
            "recipe-uploads: nothing written. Make these edits by hand (see SKILL.md), then re-run:"
        )
        for m in missing:
            print(f"  - {m}")
        return 1

    copied, kept = [], []
    for src, dst in plan_copies(app):
        if dst.exists():
            kept.append(dst.relative_to(app).as_posix())
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied.append(dst.relative_to(app).as_posix())
    for path, text in writes.items():
        path.write_text(text, encoding="utf-8")
    regenerated = regenerate_privacy(app)

    for label, items in (
        ("added", copied),
        ("edited", [p.relative_to(app).as_posix() for p in writes] + regenerated),
        ("already there, left alone", kept + skipped),
    ):
        for item in items:
            print(f"recipe-uploads: {label}: {item}")
    print(
        "recipe-uploads: next: `cd mobile && npx expo install expo-image-picker`, then the tests (SKILL.md)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
