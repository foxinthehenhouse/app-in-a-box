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

import base64
import json
import re
import struct
import sys
import zlib
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_contrast import palettes  # noqa: E402  one shape reader for the gate and this

# The kit's contrast search for atmosphere light colours: (palette, mode, intensity) -> colours.
LightsFn = Callable[[dict, str, str], dict]
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
# A token file from before atmospheres existed never chose a light, so it gets none.
DEFAULT_ATMOSPHERE = {"mode": "none", "intensity": "medium", "grain": False, "surface": "solid"}
MODES = ("light", "dark")
# The atmosphere's knobs and default light geometry, as the kit's prototype defines them
# (the kit selftest fails if the two copies disagree).
ATMO_DEFAULT = {"mode": "glow", "intensity": "medium", "grain": True, "surface": "solid"}
ATMO_KEYS = {
    "mode": ("none", "glow", "field"),
    "intensity": ("low", "medium", "high"),
    "surface": ("solid", "glass"),
}
ATMO_LIGHTS = ((0.18, -0.06, 0.78, 0.44), (1.02, 0.74, 0.70, 0.40))


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


def atmo_errors(a: object) -> list[str]:
    """Problems with an atmosphere object (the prototype's rule, same messages)."""
    if not isinstance(a, dict):
        return [": must be an object"]
    errs = [f".{k}: unknown key" for k in sorted(set(a) - set(ATMO_DEFAULT))]
    for k, options in ATMO_KEYS.items():
        if k in a and a[k] not in options:
            errs.append(f".{k}: {a[k]!r} is not one of {', '.join(options)}")
    if "grain" in a and not isinstance(a["grain"], bool):
        errs.append(".grain: must be true or false")
    return errs


def atmosphere_tokens(tokens: dict, pals: dict[str, dict], lights: LightsFn | None = None) -> dict:
    """design/tokens.json -> `atmosphere` as the app paints it. The prototype's freeze
    writes the light colours and their contrast-capped alpha into tokens.json, so this
    only copies them. A hand-written block without them needs the contrast search, which
    lives in the kit: the renderer passes it as `lights`; here it is an error, so the app
    never paints an unchecked colour. Mode none paints nothing (alpha 0)."""
    raw = tokens.get("atmosphere")
    if not isinstance(raw, dict):
        raw = DEFAULT_ATMOSPHERE
    bad = atmo_errors({k: v for k, v in raw.items() if k in ATMO_DEFAULT})
    if bad:
        raise ValueError("; ".join("atmosphere" + e for e in bad))
    a = {**ATMO_DEFAULT, **{k: raw[k] for k in ATMO_DEFAULT if k in raw}}
    color = raw.get("color") if isinstance(raw.get("color"), dict) else {}
    a["lights"] = raw.get("lights") or [list(x) for x in ATMO_LIGHTS]

    def lit(m: str) -> dict:
        if a["mode"] == "none":  # never painted; the ground colour keeps the shape honest
            c = color.get(m) or {"light1": pals[m]["bg"], "light2": pals[m]["bg"]}
            return {**c, "alpha": 0}
        if color.get(m):
            return color[m]
        if lights is None:
            raise ValueError(
                f"atmosphere.color.{m} is missing: freeze the design again so the light "
                "colours are contrast-checked and written to design/tokens.json"
            )
        return lights(pals[m], m, a["intensity"])

    a["color"] = {m: lit(m) for m in MODES}
    return a


def settle_spring(sp: dict) -> dict:
    """The spring every screen-scale move uses: `gentle`, damped to at least critical so
    it arrives without passing the mark (the prototype's settle_spring)."""
    crit = 2 * (float(sp["stiffness"]) * float(sp.get("mass", 1))) ** 0.5
    return dict(sp, damping=max(float(sp["damping"]), crit))


def grain_png(size: int = 48, seed: int = 7) -> bytes:
    """A tileable film-grain square: greyscale noise around mid-grey, the same every run
    (the kit's make_icon.grain_png, byte for byte)."""
    x, rows = seed, []
    for _ in range(size):
        row = bytearray(b"\x00")
        for _ in range(size):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF  # LCG: deterministic, no imports
            row.append(64 + (x >> 16) % 128)
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + kind + data + crc

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def tokens_ts(tokens: dict, lights: LightsFn | None = None) -> str:
    """design/tokens.json -> mobile/lib/tokens.ts (import-free, plain data). `lights`:
    see atmosphere_tokens."""
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
    motion = {**DEFAULT_MOTION, **tokens.get("motion", {})}
    gentle = (motion.get("spring") or {}).get("gentle") or DEFAULT_MOTION["spring"]["gentle"]
    lines.append(
        "/** The settle spring: `gentle` damped to at least critical, so screens and content"
        " arrive without passing the mark (the prototype's settle_spring). */"
    )
    lines.append(f"export const settle = {js(settle_spring(gentle))} as const;\n")
    lines += [
        "export interface AtmosphereLight {",
        "  light1: string;",
        "  light2: string;",
        "  /** Peak alpha of both lights, capped so every ink keeps AA on the lit ground. */",
        "  alpha: number;",
        "}",
        "export interface Atmosphere {",
        '  mode: "none" | "glow" | "field";',
        '  intensity: "low" | "medium" | "high";',
        "  grain: boolean;",
        '  surface: "solid" | "glass";',
        "  /** Each light as fractions of the screen: [centre x, centre y, radius x, radius y]. */",
        "  lights: readonly (readonly [number, number, number, number])[];",
        "  color: Readonly<Record<ColorScheme, AtmosphereLight>>;",
        "}",
        "/** The light the app sits in, frozen from the prototype (components/ui/ScreenAtmosphere). */",
        f"export const atmosphere: Atmosphere = {js(atmosphere_tokens(tokens, pals, lights))};\n",
        "/** A tileable film-grain square, laid over the atmosphere when `grain` is on. */",
        f'export const grainTile = "data:image/png;base64,{base64.b64encode(grain_png()).decode()}";\n',
    ]
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
    try:
        want = expected(root)
    except (KeyError, ValueError) as e:  # no usable palette, or a bad atmosphere knob
        return [f"design/tokens.json: can't generate mobile/lib/tokens.ts: {e}"]
    problems = []
    for rel, text in want.items():
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
