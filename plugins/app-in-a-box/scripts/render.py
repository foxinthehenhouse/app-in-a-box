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
    .codex/hooks.json               <- .claude/settings.json hooks (same scripts)
    mobile/lib/tokens.ts            <- design/tokens.json

Existing files are skipped unless --force (PROTECTED files are never overwritten);
the summary lists every skip. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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
PROTECTED = {"design/tokens.json", "appbox.yaml", "docs/product/BRIEF.md"}
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


def is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name.startswith(".")


# ---- Tokens v2 -> mobile/lib/tokens.ts, app.json theming, brand icons -----------
# Defaults fill any group a (v1 or hand-written) tokens.json leaves out, so older
# token files keep rendering. They mirror template/design/tokens.json.
DEFAULT_MOTION = {
    "duration": {
        "instant": 90,
        "fast": 140,
        "standard": 220,
        "screen": 320,
        "deliberate": 480,
        "ambient": 1400,
    },
    "easing": {
        "standard": [0.2, 0, 0, 1],
        "enter": [0.05, 0.7, 0.1, 1],
        "exit": [0.3, 0, 0.8, 0.15],
        "loop": [0.45, 0, 0.55, 1],
    },
    "spring": {
        "snappy": {"damping": 22, "stiffness": 320, "mass": 1},
        "gentle": {"damping": 20, "stiffness": 180, "mass": 1},
        "bouncy": {"damping": 12, "stiffness": 220, "mass": 1},
    },
    "pressScale": 0.97,
}
DEFAULT_ELEVATION = {
    "none": {"elevation": 0, "shadowOpacity": 0, "shadowRadius": 0, "shadowOffsetY": 0},
    "card": {"elevation": 2, "shadowOpacity": 0.08, "shadowRadius": 12, "shadowOffsetY": 4},
    "raised": {"elevation": 6, "shadowOpacity": 0.12, "shadowRadius": 20, "shadowOffsetY": 8},
    "overlay": {"elevation": 12, "shadowOpacity": 0.2, "shadowRadius": 32, "shadowOffsetY": 12},
}
DEFAULT_OPACITY = {"disabled": 0.45, "pressed": 0.12, "scrim": 0.45, "muted": 0.7}
MODES = ("light", "dark")


def _default_type(size: dict) -> dict:
    s = {"xs": 12, "sm": 14, "md": 16, "lg": 20, "xl": 28, "xxl": 40, **size}
    role = lambda font, px, lh, w, ls, cap, **kw: {  # noqa: E731
        "font": font,
        "size": px,
        "lineHeight": round(px * lh),
        "weight": w,
        "letterSpacing": ls,
        "maxScale": cap,
        **kw,
    }
    return {
        "display": role("display", s["xxl"], 1.15, "700", -0.8, 1.3),
        "title": role("display", s["xl"], 1.2, "700", -0.4, 1.4),
        "heading": role("display", s["lg"], 1.3, "600", -0.2, 1.6),
        "body": role("body", s["md"], 1.45, "400", 0, 2.0),
        "secondary": role("body", s["sm"], 1.45, "400", 0, 2.0),
        "meta": role("body", s["xs"], 1.35, "600", 0.6, 1.6, uppercase=True),
        "mono": role("mono", s["sm"], 1.45, "500", 0, 1.6),
    }


def theme_palettes(tokens: dict) -> tuple[dict[str, dict], list[str]]:
    """({light, dark} palettes, supported modes). v1 single palette -> same map in both
    slots and only its own mode supported, so the app locks to it instead of crashing."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_contrast import palettes  # one shape reader for the gate and the renderer

    pals = palettes(tokens)
    supported = [m for m in MODES if m in pals]
    if not supported:
        raise ValueError("design/tokens.json has no colour palette")
    fallback = pals[supported[0]]
    return {m: pals.get(m, fallback) for m in MODES}, supported


def tokens_ts(tokens: dict) -> str:
    """design/tokens.json -> mobile/lib/tokens.ts (import-free, plain data)."""
    pals, supported = theme_palettes(tokens)
    default_mode = tokens.get("mode", supported[0])
    if default_mode not in supported:
        default_mode = supported[0]
    names = sorted(pals["dark"], key=list(pals["dark"]).index)
    type_ = tokens.get("type") or _default_type(tokens.get("size", {}))

    def js(value: object) -> str:
        return json.dumps(value, indent=2)

    lines = [
        "// GENERATED from design/tokens.json by the App in a Box renderer.",
        "// Edit design/tokens.json, then re-run the contrast check and the renderer.",
        "// Import-free on purpose so Node tooling (tests, codegen) can load it.",
        "// Screens never import this directly: use useTheme() from lib/theme.ts.",
        "",
        'export type ColorScheme = "light" | "dark";',
        "export type ColorName = " + (" | ".join(json.dumps(n) for n in names) or "never") + ";",
        "export type Palette = Readonly<Record<ColorName, string>>;",
        "",
        f"export const palettes: Readonly<Record<ColorScheme, Palette>> = {js(pals)};\n",
        "/** Modes this theme was designed (and contrast-checked) for. One entry = locked. */",
        f"export const schemes: readonly ColorScheme[] = {json.dumps(supported)};",
        # Typed as the union, not the literal: `mode === "dark"` must typecheck in light themes.
        "/** The mode used when the OS reports none (and the icon's palette). */",
        f'export const mode: "light" | "dark" = {json.dumps(default_mode)};',
        "/** Default-mode palette for Node tooling. Screens use useTheme().color. */",
        "export const color: Palette = palettes[mode];\n",
    ]
    for group in ("font", "size", "space", "radius"):
        lines.append(f"export const {group} = {js(tokens.get(group, {}))} as const;\n")
    lines.append(f"export const typeRoles = {js(type_)} as const;\n")
    lines.append(
        f"export const motion = {js({**DEFAULT_MOTION, **tokens.get('motion', {})})} as const;\n"
    )
    lines.append(
        f"export const elevation = {js(tokens.get('elevation') or DEFAULT_ELEVATION)} as const;\n"
    )
    lines.append(
        f"export const opacity = {js({**DEFAULT_OPACITY, **tokens.get('opacity', {})})} as const;\n"
    )
    lines.append(f"export const minTapTarget = {int(tokens.get('minTapTarget', 48))};")
    lines.append(f"export const themeName = {json.dumps(tokens.get('name', 'custom'))};\n")
    return "\n".join(lines)


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


def theme_outputs(target: Path, tokens_file: Path, dry_run: bool, app_name: str = "") -> list[str]:
    """tokens.ts + themed app.json + brand icons (icons only when the tokens changed)."""
    import hashlib

    tokens = json.loads(tokens_file.read_text())
    made = ["mobile/lib/tokens.ts (from design/tokens.json)"]
    if dry_run:
        return made
    out = target / "mobile" / "lib" / "tokens.ts"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(tokens_ts(tokens))
    from check_contrast import check

    problems = check(tokens)
    if problems:
        # The contrast gate is the place that fails; the renderer only refuses to
        # build brand assets from a palette it can't trust.
        print("WARNING: design/tokens.json fails the contrast/schema check; skipped app.json theming + icons:")
        print(*(f"  - {p}" for p in problems[:8]), sep="\n")
        return made
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


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2).strip()


def _toml_str(s: str) -> str:
    return json.dumps(s)  # a JSON string literal is a valid TOML basic string


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


def codex_agent_toml(md: str) -> str:
    """Claude agent .md -> Codex agent role TOML.

    Model routing (see KIT/docs/MODEL_ROUTING.md): Claude `effort` maps onto Codex
    `model_reasoning_effort` (Codex has no `max` on every model, so max -> xhigh).
    Claude's `model` alias (opus/sonnet/haiku/fable) has no stable Codex equivalent,
    so the role inherits the session's model unless the .md pins one with
    `codex_model:`. The Claude tier is kept as a comment so the intent survives.
    A role whose `tools:` can't write files becomes `sandbox_mode = "read-only"`.
    """
    meta, body = _frontmatter(md)
    effort = {"low": "low", "medium": "medium", "high": "high", "max": "xhigh"}.get(
        meta.get("effort", "").lower()
    )
    out = [
        "# GENERATED from .agents/agents/*.md by the App in a Box renderer. Edit the .md.",
        f"name = {_toml_str(meta.get('name', ''))}",
        f"description = {_toml_str(meta.get('description', ''))}",
    ]
    if meta.get("model"):
        out.insert(1, f"# Claude tier: model={meta['model']} effort={meta.get('effort', '-')}")
    if meta.get("codex_model"):
        out.append(f"model = {_toml_str(meta['codex_model'])}")
    if effort:
        out.append(f"model_reasoning_effort = {_toml_str(effort)}")
    # A Claude role whose tools can't write files (no Edit/Write/MultiEdit/NotebookEdit)
    # is a read-only role; Codex enforces that with its sandbox, not a tool list.
    tools = {x.strip() for x in meta.get("tools", "").split(",") if x.strip()}
    if tools and not tools & {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        out.append('sandbox_mode = "read-only"')
    out.append(f"developer_instructions = {_toml_str(body)}")
    return "\n".join(out) + "\n"


def codex_skill_yaml(skill_md: str) -> str | None:
    """Codex reads per-skill policy from <skill>/agents/openai.yaml. Mirror Claude's
    `disable-model-invocation: true` (explicit-only skills) as
    `policy.allow_implicit_invocation: false`; other skills need no file."""
    meta, _ = _frontmatter(skill_md)
    if meta.get("disable-model-invocation", "").lower() != "true":
        return None
    return (
        "# GENERATED from SKILL.md (disable-model-invocation) by the App in a Box renderer.\n"
        "policy:\n"
        "  allow_implicit_invocation: false\n"
    )


def codex_config_toml(mcp: dict) -> str:
    out = [
        "# GENERATED from .mcp.json by the App in a Box renderer. Project config is only",
        "# read when this project is trusted in Codex.",
        "",
        "[sandbox_workspace_write]",
        "network_access = true  # CLIs (supabase, eas, gh, npm) need the network",
        "",
    ]
    for name, cfg in mcp.get("mcpServers", {}).items():
        out.append(f"[mcp_servers.{name}]")
        if "url" in cfg:
            out.append(f"url = {_toml_str(cfg['url'])}")
            auth = cfg.get("headers", {}).get("Authorization", "")
            m = re.match(r"Bearer \$\{(\w+)\}", auth)
            if m:
                out.append(f"bearer_token_env_var = {_toml_str(m.group(1))}")
        else:
            out.append(f"command = {_toml_str(cfg['command'])}")
            out.append("args = [" + ", ".join(_toml_str(x) for x in cfg.get("args", [])) + "]")
        out.append("")
    return "\n".join(out)


def codex_hooks_json(claude_settings: dict) -> str:
    """Same hook scripts, same event names; Codex has no $CLAUDE_PROJECT_DIR, so
    resolve the repo root with git. Codex asks you to trust each hook once."""
    root = '"$(git rev-parse --show-toplevel)'
    hooks = {}
    for event, groups in claude_settings.get("hooks", {}).items():
        new_groups = []
        for g in groups:
            g2 = dict(g)
            g2["hooks"] = [
                {**h, "command": h["command"].replace('"$CLAUDE_PROJECT_DIR', root)}
                for h in g.get("hooks", [])
            ]
            new_groups.append(g2)
        hooks[event] = new_groups
    return json.dumps({"hooks": hooks}, indent=2) + "\n"


def adapters(target: Path) -> list[str]:
    """Generate Claude Code + Codex adapters from the shared .agents/ sources."""
    made: list[str] = []
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
        if src.is_dir() or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(TEMPLATE)
        if a.no_backend and rel.parts[0] in {
            "backend",
            "tests",
            "railway.json",
            "requirements.txt",
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
        if is_text(src):
            dst.write_text(substitute(src.read_text(), subs))
        else:
            shutil.copyfile(src, dst)
        shutil.copymode(src, dst)

    tokens_file = target / "design" / "tokens.json"
    if tokens_file.exists():
        written += theme_outputs(target, tokens_file, a.dry_run, a.name)

    if not a.dry_run:
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
