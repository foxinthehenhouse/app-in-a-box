#!/usr/bin/env python3
"""Generated files match their sources: rebuild each one in memory, fail on any diff.

These files are GENERATED, never edited by hand:

    mobile/lib/tokens.ts                     <- design/tokens.json
    .codex/agents/<role>.toml                <- .agents/agents/<role>.md
    .codex/config.toml                       <- .mcp.json
    .codex/hooks.json                        <- .claude/settings.json (hooks)
    .agents/skills/<skill>/agents/openai.yaml <- that SKILL.md (explicit-only skills)

A hand edit to one of them works until the next regeneration quietly throws it away;
a source edited without regenerating ships yesterday's theme or agent instructions.
CI runs this on every PR. It is the same code the App in a Box renderer writes them
with (the renderer imports this module), so a fresh render always passes.

    python3 scripts/check_generated.py          check: exit 1 naming every stale file
    python3 scripts/check_generated.py --fix    rewrite them from their sources

Standard library only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_contrast import palettes  # noqa: E402  one shape reader for the gate and this

ROOT = Path(__file__).resolve().parent.parent

# ---- design/tokens.json -> mobile/lib/tokens.ts ------------------------------------
# Defaults fill any group a (v1 or hand-written) tokens.json leaves out, so older
# token files keep rendering. They mirror the template's design/tokens.json.
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


# ---- .agents/ + .mcp.json + .claude/settings.json -> the Codex adapters --------------


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


def codex_agent_toml(md: str) -> str:
    """Claude agent .md -> Codex agent role TOML.

    Model routing (see the kit's docs/MODEL_ROUTING.md): Claude `effort` maps onto Codex
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


# ---- the check ---------------------------------------------------------------------


def _skill_outputs(root: Path) -> dict[str, str | None]:
    """openai.yaml per skill: its text, or None where a GENERATED one must not exist."""
    out: dict[str, str | None] = {}
    for skill in sorted((root / ".agents" / "skills").glob("*/SKILL.md")):
        path = skill.parent / "agents" / "openai.yaml"
        yml = codex_skill_yaml(skill.read_text())
        if yml is not None:
            out[path.relative_to(root).as_posix()] = yml
        elif path.is_file() and path.read_text().startswith("# GENERATED"):
            out[path.relative_to(root).as_posix()] = None  # the skill became model-invocable
    return out


def expected(root: Path) -> dict[str, str | None]:
    """{relative path: the text it must have}, for every generated file whose source
    exists. None means the file must not exist (its source is gone)."""
    want: dict[str, str | None] = {}
    tokens = root / "design" / "tokens.json"
    if tokens.is_file():
        want["mobile/lib/tokens.ts"] = tokens_ts(json.loads(tokens.read_text()))
    roles = root / ".agents" / "agents"
    if roles.is_dir():
        sources = {md.stem: md for md in roles.glob("*.md")}
        for stem, md in sorted(sources.items()):
            want[f".codex/agents/{stem}.toml"] = codex_agent_toml(md.read_text())
        for toml in sorted((root / ".codex" / "agents").glob("*.toml")):
            if toml.stem not in sources:
                want[f".codex/agents/{toml.name}"] = None  # the role was deleted
    mcp = root / ".mcp.json"
    if mcp.is_file():
        want[".codex/config.toml"] = codex_config_toml(json.loads(mcp.read_text()))
    settings = root / ".claude" / "settings.json"
    if settings.is_file():
        want[".codex/hooks.json"] = codex_hooks_json(json.loads(settings.read_text()))
    want.update(_skill_outputs(root))
    return want


def stale(root: Path) -> list[str]:
    """Every generated file that differs from what its source produces, with why."""
    problems = []
    for rel, text in expected(root).items():
        path = root / rel
        if text is None:
            problems.append(f"{rel}: generated from a source that no longer exists")
        elif not path.is_file():
            problems.append(f"{rel}: missing")
        elif path.read_text() != text:
            problems.append(f"{rel}: differs from what its source generates (hand-edited?)")
    return problems


def fix(root: Path) -> list[str]:
    written = []
    for rel, text in expected(root).items():
        path = root / rel
        if text is None:
            path.unlink(missing_ok=True)
        elif not path.is_file() or path.read_text() != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        else:
            continue
        written.append(rel)
    return written


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--fix"]):
        print(__doc__)
        return 2
    if args == ["--fix"]:
        written = fix(ROOT)
        if written:
            print("Regenerated:", *written, sep="\n  - ")
        else:
            print("Nothing stale.")
        return 0
    problems = stale(ROOT)
    if problems:
        print("Generated files are stale:")
        print(*(f"  - {p}" for p in problems), sep="\n")
        print(
            "Edit the source, never the generated file, then run "
            "`python3 scripts/check_generated.py --fix` and commit the result."
        )
        return 1
    print(f"Generated files are current ({len(expected(ROOT))} checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
