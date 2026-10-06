#!/usr/bin/env python3
"""Render the App in a Box template into a target directory.

Deterministic on purpose: the same answers always produce the same files, so the
scaffold is reviewable and re-runnable, and Claude spends its effort on the
app-specific parts, not on retyping boilerplate.

    render.py --target . --name "Penny Jar" --slug penny-jar \
        --bundle-id com.alex.pennyjar --owner alex --one-liner "Savers use ..." \
        [--force] [--dry-run]

Placeholders replaced in file contents AND paths:
    __APP_NAME__  __APP_SLUG__  __BUNDLE_ID__  __OWNER__  __ONE_LINER__  __SCHEME__

Then it generates the per-agent adapters from the shared, agent-neutral sources:

    AGENTS.md, .agents/{skills,agents,rules,memory}   (source of truth, both agents)
    .claude/skills, .claude/agents  -> symlinks into .agents/     (Claude Code)
    .codex/agents/*.toml            <- .agents/agents/*.md        (Codex)
    .codex/config.toml              <- .mcp.json (+ sandbox network for provisioning)
    .mcp.json                       synced to the services appbox.yaml's stack chose
    .codex/hooks.json               <- .claude/settings.json hooks (same scripts)
    mobile/lib/tokens.ts            <- design/tokens.json
    DESIGN.md                       <- design/tokens.json (generated blocks only; prose kept)
    privacy/data-map.yaml `packs`   <- design/brief.json risk.categories (the map is the app's)
    privacy/*.md, app.json privacyManifests <- privacy/data-map.yaml (the app's own generator)
    docs/design/TASTE.md            <- KIT/docs/TASTE.md (the taste rubric; never overwritten)
    docs/DEFAULTS.md                <- KIT/docs/DEFAULTS.md (the baked-in product defaults; same)

Existing files are skipped unless --force (PROTECTED files are never overwritten);
the summary lists every skip. Standard library only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]  # plugin root
TEMPLATE = KIT / "template"
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".sh",
    ".txt",
    ".css",
    ".example",
    ".gitignore",
    "",
}
# User decisions: written by the interview/design phases, never clobbered by --force.
# README.md is rendered once and is the owner's from then on (it carries the removable
# "Built with App in a Box" badge; a re-render must not put back a badge they deleted).
PROTECTED = {
    "README.md",
    "design/tokens.json",
    "design/brief.json",
    "appbox.yaml",
    "docs/product/BRIEF.md",
    "docs/product/VALIDATION.md",
    "docs/design/TASTE.md",
    "docs/DEFAULTS.md",
    "privacy/data-map.yaml",
}
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$")
BUNDLE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*(\.[a-zA-Z][a-zA-Z0-9]*){2,}$")


def placeholders(a: argparse.Namespace) -> dict[str, str]:
    return {
        "__APP_NAME__": a.name,
        "__APP_SLUG__": a.slug,
        "__BUNDLE_ID__": a.bundle_id,
        "__OWNER__": a.owner,
        "__ONE_LINER__": a.one_liner,
        "__SCHEME__": a.slug.replace("-", ""),
    }


def substitute(text: str, subs: dict[str, str]) -> str:
    for key, value in subs.items():
        text = text.replace(key, value)
    return text


# Tool caches a contributor's local run can leave in the template (ruff, pytest, npm...).
# They are never part of the product, and a binary cache file used to crash the render.
CACHE_DIRS = {"__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache", "node_modules", ".expo"}


def is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name.startswith(".")


# ---- Tokens v2 -> mobile/lib/tokens.ts, app.json theming, brand icons -----------
# The generators themselves (tokens.ts and the Codex adapters) live in the template's
# scripts/check_generated.py, so the generated repo's CI rebuilds those files with
# exactly this code and fails on a hand edit. One implementation, imported here.
_GEN_PATH = TEMPLATE / "scripts" / "check_generated.py"
_gen_spec = importlib.util.spec_from_file_location("check_generated", _GEN_PATH)
if _gen_spec is None or _gen_spec.loader is None:
    raise ImportError(f"generators not found at {_GEN_PATH}")
_gen = importlib.util.module_from_spec(_gen_spec)
_gen_spec.loader.exec_module(_gen)
theme_palettes = _gen.theme_palettes


def tokens_ts(tokens: dict) -> str:
    """design/tokens.json -> mobile/lib/tokens.ts. A hand-written atmosphere without
    frozen light colours gets them from the prototype's contrast search (kit-only)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from prototype import atmo_lights

    return _gen.tokens_ts(tokens, lights=atmo_lights)


codex_agent_toml = _gen.codex_agent_toml
codex_skill_yaml = _gen.codex_skill_yaml
codex_config_toml = _gen.codex_config_toml
codex_hooks_json = _gen.codex_hooks_json


BRAND = "./assets/brand"


def theme_app_json(app: dict, tokens: dict) -> dict:
    """Point app.json at the generated brand assets and theme the splash per mode.

    userInterfaceStyle is `automatic` only when the tokens ship both palettes; a v1
    single-palette theme locks to its mode, so native chrome (tab bar, sheets,
    keyboard) matches the only palette that exists.
    """
    pals, supported = theme_palettes(tokens)
    expo = app.setdefault("expo", {})
    expo["userInterfaceStyle"] = "automatic" if len(supported) == 2 else supported[0]
    expo["icon"] = f"{BRAND}/icon.png"
    main = (
        pals[tokens.get("mode", supported[0])]
        if tokens.get("mode") in supported
        else pals[supported[0]]
    )
    expo.setdefault("android", {})["adaptiveIcon"] = {
        "foregroundImage": f"{BRAND}/adaptive-icon.png",
        "backgroundColor": main["accent"],
    }
    expo.setdefault("web", {})["favicon"] = f"{BRAND}/favicon.png"
    splash = [
        "expo-splash-screen",
        {
            "image": f"{BRAND}/splash-icon.png",
            "imageWidth": 120,
            "resizeMode": "contain",
            "backgroundColor": pals["light"]["bg"],
            "dark": {"image": f"{BRAND}/splash-icon.png", "backgroundColor": pals["dark"]["bg"]},
        },
    ]
    plugins = [
        p
        for p in expo.get("plugins", [])
        if (p[0] if isinstance(p, list) else p) != "expo-splash-screen"
    ]
    expo["plugins"] = [*plugins, splash]
    return app


class ContrastGateError(Exception):
    """design/tokens.json failed the WCAG/schema gate; the render finishes, then exits 2."""


def theme_outputs(target: Path, tokens_file: Path, dry_run: bool, app_name: str = "") -> list[str]:
    """tokens.ts + themed app.json + brand icons (icons only when the tokens changed)."""
    import hashlib

    tokens = json.loads(tokens_file.read_text())
    made = ["mobile/lib/tokens.ts (from design/tokens.json)"]
    if dry_run:
        return made
    out = target / "mobile" / "lib" / "tokens.ts"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        ts = tokens_ts(tokens)
    except (KeyError, ValueError) as e:  # no usable palette, or a bad atmosphere knob
        print(f"ERROR: design/tokens.json can't be rendered: {e}")
        raise ContrastGateError([str(e)]) from e
    out.write_text(ts)
    from check_contrast import check

    problems = check(tokens)
    if problems:
        # A palette the gate rejects is a failed render, not a warning: the renderer still
        # writes everything else so the founder can see the output, refuses to build brand
        # assets from a palette it can't trust, and exits non-zero at the end (a WARNING
        # here used to read as a successful scaffold with sub-AA text in it).
        print("ERROR: design/tokens.json fails the contrast/schema check; skipped app.json theming + icons:")
        print(*(f"  - {p}" for p in problems[:8]), sep="\n")
        raise ContrastGateError(problems)
    from check_design import check as design_check

    # Taste, not legibility, so the render still completes; but say it loudly, because
    # the generated repo's `npm run gates` runs the same check and will fail on it.
    for tell in design_check(tokens):
        print(f"WARNING: design/tokens.json: {tell} (npm run gates will fail on this)")
    app_json = target / "mobile" / "app.json"
    if app_json.is_file():
        app_json.write_text(
            json.dumps(theme_app_json(json.loads(app_json.read_text()), tokens), indent=2) + "\n"
        )
        made.append("mobile/app.json (splash + icon from tokens)")
    brand = target / "mobile" / "assets" / "brand"
    custom = target / "design" / "icon.png"
    stamp = hashlib.sha256(
        tokens_file.read_bytes() + app_name.encode() + (custom.read_bytes() if custom.is_file() else b"")
    ).hexdigest()
    if (brand / ".stamp").is_file() and (brand / ".stamp").read_text() == stamp:
        return made
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from make_icon import render_icons

    glyph = (tokens.get("icon") or {}).get("glyph") or (app_name or tokens.get("name") or "A")[:1]
    render_icons(tokens, brand, glyph)
    if custom.is_file():
        shutil.copyfile(custom, brand / "icon.png")
    (brand / ".stamp").write_text(stamp)
    made.append("mobile/assets/brand/*.png (icon, adaptive, splash, favicon)")
    return made


def design_doc(target: Path, tokens_file: Path, dry_run: bool) -> list[str]:
    """DESIGN.md at the repo root, from design/tokens.json. Created when absent; when it
    exists only the frontmatter and the generated blocks are refreshed, so the founder's
    prose and Decisions log are never overwritten (--force or not). The generated repo
    checks it with the same code: `python3 scripts/design_md.py --check`."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from design_md import write

    if dry_run:
        return ["DESIGN.md (from design/tokens.json)"]
    tokens = json.loads(tokens_file.read_text())
    if not isinstance(tokens, dict):
        return []
    changed = write(target / "DESIGN.md", tokens)
    return ["DESIGN.md (from design/tokens.json)"] if changed else []


# ---- privacy/data-map.yaml: packs from the risk screen, outputs from the map ------------
# Category ids (design/brief.json risk.categories) that turn on a guardrail pack of the
# same name, used when the kit's scripts/risk/categories.json isn't there to say.
PACKS = ("location", "minors", "health", "ugc", "financial", "biometric")


def risk_packs(target: Path) -> list[str] | None:
    """The guardrail packs design/brief.json's risk block turns on, `baseline` first; None
    when the brief has no risk block (the map keeps what it has). Read defensively: the
    block is written by shape's risk screen, and an older brief has none."""
    try:
        risk = json.loads((target / "design" / "brief.json").read_text()).get("risk")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(risk, dict) or not isinstance(risk.get("categories"), list):
        return None
    ids = [c.get("id") if isinstance(c, dict) else c for c in risk["categories"]]
    guardrails: dict[str, list[str]] = {}
    try:
        cats = json.loads((KIT / "scripts" / "risk" / "categories.json").read_text())
        entries = cats.get("categories", cats) if isinstance(cats, dict) else cats
        if isinstance(entries, dict):
            entries = [{"id": k, **v} for k, v in entries.items() if isinstance(v, dict)]
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get("guardrails"), list):
                guardrails[str(e.get("id"))] = [str(g) for g in e["guardrails"]]
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    packs = {"baseline"}
    for cid in ids:
        if not isinstance(cid, str):
            continue
        packs.update(guardrails.get(cid, [cid] if cid in PACKS else []))
    return ["baseline", *sorted(packs - {"baseline"})]


def privacy_outputs(target: Path) -> list[str]:
    """Set `packs` in privacy/data-map.yaml from the risk screen, then regenerate the store
    answers, PrivacyInfo entries and policy draft with the APP's own generator (the code
    its CI checks them with). The map itself is the app's: only the packs line changes."""
    made: list[str] = []
    dm = target / "privacy" / "data-map.yaml"
    if not dm.is_file():
        return made
    packs = risk_packs(target)
    if packs is not None:
        text = dm.read_text()
        new = re.sub(r"^packs:.*$", f"packs: [{', '.join(packs)}]", text, count=1, flags=re.M)
        if new != text:
            dm.write_text(new)
            made.append("privacy/data-map.yaml (packs from design/brief.json risk.categories)")
    gen = target / "scripts" / "check_data_map.py"
    if gen.is_file():
        r = subprocess.run(
            [sys.executable, str(gen), "--write"], cwd=target, capture_output=True, text=True
        )
        if r.returncode == 0:
            made += [ln[len("wrote ") :] for ln in r.stdout.splitlines() if ln.startswith("wrote ")]
        else:
            print(
                "Note: couldn't regenerate the privacy answers from privacy/data-map.yaml"
                f" ({(r.stdout + r.stderr).strip().splitlines()[-1:]}). In the app, run:"
                " python3 scripts/check_data_map.py --write"
            )
    return made + guardrail_packs_ts(target)


def guardrail_packs_ts(target: Path) -> list[str]:
    """mobile/lib/packs.ts (the app's copy of the packs) from the map's `packs` line, with
    the app's own check_guardrails.py --write, so a render never leaves the two disagreeing."""
    gen, ts = target / "scripts" / "check_guardrails.py", target / "mobile" / "lib" / "packs.ts"
    if not gen.is_file():
        return []
    before = ts.read_text() if ts.is_file() else None
    r = subprocess.run(
        [sys.executable, str(gen), "--write"], cwd=target, capture_output=True, text=True
    )
    if r.returncode != 0:
        print(
            "Note: couldn't regenerate mobile/lib/packs.ts from privacy/data-map.yaml. In the"
            " app, run: python3 scripts/check_guardrails.py --write"
        )
        return []
    return [] if ts.read_text() == before else ["mobile/lib/packs.ts (from the map's packs)"]


def _link(target: Path, link: str, to: str) -> str:
    """Symlink target/link -> to (relative); fall back to a copy where symlinks fail."""
    path = target / link
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.symlink_to(to, target_is_directory=True)
        return f"{link} -> {to}"
    except OSError:
        shutil.copytree(path.parent / to, path)
        return f"{link} (copy of {to}; symlinks unavailable)"


# An MCP server that only serves an opt-in service. It's dropped from the generated
# .mcp.json when appbox.yaml's stack declines that service, so nobody is asked to
# authorise a server they said no to. (The app's typed no-op calls stay.)
OPTIONAL_MCP = {
    "posthog": ("analytics", "posthog"),
    "sentry": ("errors", "sentry"),
    "linear": ("tracker", "linear"),
}


def read_stack(target: Path) -> dict[str, str]:
    """The flat `stack:` mapping from appbox.yaml (stdlib only, like progress.py)."""
    box = target / "appbox.yaml"
    if not box.is_file():
        return {}
    stack, inside = {}, False
    for raw in box.read_text().splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            inside = line.split(":", 1)[0] == "stack"
            continue
        if inside and line.startswith("  ") and not line.startswith("   "):
            key, _, value = line.strip().partition(":")
            stack[key] = value.strip().strip("\"'")
    return stack


def sync_mcp(target: Path) -> list[str]:
    """Make the opt-in MCP servers match the stack: drop declined ones, and restore a
    chosen one (from the template) that an earlier render dropped, so switching a
    service on later is `stack.<key>: <service>` in appbox.yaml + `--adapters-only`."""
    mcp, stack = target / ".mcp.json", read_stack(target)
    if not mcp.is_file() or not stack:
        return []  # no appbox.yaml yet (a bare render): keep every server
    data = json.loads(mcp.read_text())
    servers = data.setdefault("mcpServers", {})
    shipped = json.loads((TEMPLATE / ".mcp.json").read_text()).get("mcpServers", {})
    changed = []
    for name, (key, wanted) in OPTIONAL_MCP.items():
        if key not in stack:
            continue
        if stack[key] != wanted and name in servers:
            del servers[name]
            changed.append(f"dropped {name} (not in the stack)")
        elif stack[key] == wanted and name not in servers and name in shipped:
            servers[name] = shipped[name]
            changed.append(f"restored {name} (back in the stack)")
    if changed:
        mcp.write_text(json.dumps(data, indent=2) + "\n")
    return changed


def adapters(target: Path) -> list[str]:
    """Generate Claude Code + Codex adapters from the shared .agents/ sources."""
    made: list[str] = [f".mcp.json: {c}" for c in sync_mcp(target)]
    agents_dir = target / ".agents"
    if (agents_dir / "skills").is_dir():
        made.append(_link(target, ".claude/skills", "../.agents/skills"))
        for skill in sorted((agents_dir / "skills").glob("*/SKILL.md")):
            yml = codex_skill_yaml(skill.read_text())
            out = skill.parent / "agents" / "openai.yaml"
            if yml:
                out.parent.mkdir(exist_ok=True)
                out.write_text(yml)
                made.append(str(out.relative_to(target)))
            elif out.is_file() and out.read_text().startswith("# GENERATED"):
                out.unlink()  # the skill became model-invocable again
    if (agents_dir / "agents").is_dir():
        made.append(_link(target, ".claude/agents", "../.agents/agents"))
        out = target / ".codex" / "agents"
        out.mkdir(parents=True, exist_ok=True)
        for md in sorted((agents_dir / "agents").glob("*.md")):
            (out / f"{md.stem}.toml").write_text(codex_agent_toml(md.read_text()))
            made.append(f".codex/agents/{md.stem}.toml")
    mcp = target / ".mcp.json"
    if mcp.is_file():
        (target / ".codex").mkdir(exist_ok=True)
        (target / ".codex" / "config.toml").write_text(
            codex_config_toml(json.loads(mcp.read_text()))
        )
        made.append(".codex/config.toml")
    settings = target / ".claude" / "settings.json"
    if settings.is_file():
        (target / ".codex").mkdir(exist_ok=True)
        (target / ".codex" / "hooks.json").write_text(
            codex_hooks_json(json.loads(settings.read_text()))
        )
        made.append(".codex/hooks.json")
    return made


def render(a: argparse.Namespace) -> int:
    subs = placeholders(a)
    target = Path(a.target).resolve()
    written, skipped = [], []
    for src in sorted(TEMPLATE.rglob("*")):
        if src.is_dir() or CACHE_DIRS.intersection(src.relative_to(TEMPLATE).parts):
            continue
        rel = src.relative_to(TEMPLATE)
        if a.no_backend and rel.parts[0] in {
            "backend",
            "tests",
            "railway.json",
            "requirements.txt",
            "requirements.lock",
            "run.sh",
        }:
            continue
        rel_out = Path(substitute(str(rel), subs))
        if rel_out.name.endswith(".tmpl"):
            rel_out = rel_out.with_name(rel_out.name[: -len(".tmpl")])
        dst = target / rel_out
        if dst.exists() and (not a.force or str(rel_out) in PROTECTED):
            skipped.append(str(rel_out))
            continue
        written.append(str(rel_out))
        if a.dry_run:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            text = src.read_text() if is_text(src) else None
        except UnicodeDecodeError:  # looks like text by name, isn't: copy the bytes as-is
            text = None
        if text is not None:
            dst.write_text(substitute(text, subs))
        else:
            shutil.copyfile(src, dst)
        shutil.copymode(src, dst)

    # The taste rubric the prototype was judged by travels with the app, so the
    # generated repo's designers and reviewers read the same page the kit's team did.
    # It lives in the kit's docs/, not the template, so it is copied here; and it is
    # PROTECTED: a repo that edited its own copy keeps it, --force or not.
    # DEFAULTS.md travels the same way: the product defaults shape stated instead of
    # asking, which the app's feature-discovery, build-feature and ship skills build to.
    for kit_doc, rel in (("TASTE.md", "docs/design/TASTE.md"), ("DEFAULTS.md", "docs/DEFAULTS.md")):
        src, dst = KIT / "docs" / kit_doc, target / rel
        if not src.is_file():
            continue
        if dst.exists():
            skipped.append(rel)
        else:
            written.append(rel)
            if not a.dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(src.read_text())

    tokens_file = target / "design" / "tokens.json"
    contrast_failed = False
    if tokens_file.exists():
        try:
            written += theme_outputs(target, tokens_file, a.dry_run, a.name)
        except ContrastGateError:
            contrast_failed = True
            written.append("mobile/lib/tokens.ts (from design/tokens.json)")
        written += design_doc(target, tokens_file, a.dry_run)

    if not a.dry_run:
        written += privacy_outputs(target)
        written += adapters(target)

    print(f"{'Would write' if a.dry_run else 'Wrote'} {len(written)} file(s) to {target}")
    if skipped:
        print(f"Skipped {len(skipped)} existing file(s) (use --force to overwrite):")
        for s in skipped:
            print(f"  - {s}")
    leftover = [] if a.dry_run else find_leftovers(target, written)
    if leftover:
        print("ERROR: unreplaced placeholders in:", *leftover, sep="\n  - ")
        return 1
    if contrast_failed:
        print("ERROR: fix design/tokens.json (python3 scripts/check_contrast.py design/tokens.json) and re-run.")
        return 2
    return 0


def find_leftovers(target: Path, written: list[str]) -> list[str]:
    bad = []
    for rel in written:
        path = target / rel.split(" ")[0]
        if path.is_symlink():
            continue
        if path.is_file() and is_text(path):
            if re.search(
                r"__(APP_NAME|APP_SLUG|BUNDLE_ID|OWNER|ONE_LINER|SCHEME)__", path.read_text()
            ):
                bad.append(rel)
    return bad


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--target", default=".")
    p.add_argument("--name")
    p.add_argument("--slug")
    p.add_argument("--bundle-id")
    p.add_argument("--owner")
    p.add_argument("--one-liner", default="")
    p.add_argument(
        "--no-backend",
        action="store_true",
        help="not supported in v1 (a Supabase-only stack); exits with an explanation",
    )
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--adapters-only",
        action="store_true",
        help="only regenerate Claude/Codex adapters from .agents/ in an existing repo",
    )
    a = p.parse_args(argv)
    if a.no_backend:
        p.error(
            "--no-backend (a Supabase-only stack) isn't supported in v1: the CI, harness"
            " lint and runbooks assume the FastAPI backend. Use the default stack."
        )
    if a.adapters_only:
        made = adapters(Path(a.target).resolve())
        print("Regenerated adapters:", *made, sep="\n  - ")
        return 0
    missing = [f for f in ("name", "slug", "bundle_id", "owner") if not getattr(a, f)]
    if missing:
        p.error("required: " + ", ".join("--" + m.replace("_", "-") for m in missing))
    if not SLUG_RE.match(a.slug):
        p.error("--slug must be kebab-case, 3-40 chars, e.g. penny-jar")
    for field in ("name", "one_liner", "owner"):
        if re.search(r'["\\`<>{}$]', getattr(a, field)):
            p.error(f"--{field.replace('_', '-')} can't contain quotes, backslashes, <>, {{}} or $")
    if not BUNDLE_RE.match(a.bundle_id):
        p.error("--bundle-id must look like com.owner.app")
    if not TEMPLATE.is_dir():
        p.error(f"template not found at {TEMPLATE}")
    os.umask(0o022)
    return render(a)


if __name__ == "__main__":
    sys.exit(main())
