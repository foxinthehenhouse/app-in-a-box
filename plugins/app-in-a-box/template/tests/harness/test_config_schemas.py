"""Schema-ish validation of the JSON/TOML/YAML configs agents and builds depend on.

None of these files has a compiler, and every one fails SILENTLY when wrong: a hook
under a misspelled event never runs, a malformed matcher never matches, an MCP entry
with neither `url` nor `command` never loads, a `preview` EAS profile with no `env`
block ships a build with no API URL, a Codex config that doesn't parse is ignored.
Each validator is a pure function with a negative control. No network, no jsonschema
dependency: the shapes checked are the ones these tools actually read.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness_lib import ROOT, SETTINGS, load_json

# Claude Code hook events as of 2026-10-02 (reference: Claude Code docs, "Hooks reference"
# -> "Hook events"). The 2026-05 list had the first twelve; the second block was added
# since. A hook under an event missing here is reported as "unknown", so widen this set
# when Claude Code adds an event; never trim it to make a config pass.
CLAUDE_HOOK_EVENTS = {
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "UserPromptSubmit", "Notification",
    "Stop", "SubagentStart", "SubagentStop", "PreCompact", "SessionStart", "SessionEnd",
    "PermissionRequest",
    "Setup", "PostToolBatch", "StopFailure", "TaskCreated", "TaskCompleted",
    "InstructionsLoaded", "ConfigChange", "CwdChanged", "FileChanged", "WorktreeCreate",
    "WorktreeRemove", "PostCompact", "PreModelSwitch",
}  # fmt: skip
TOOL_EVENTS = {"PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest"}
# Events whose groups may carry a `matcher` (same reference, same date): tool events match
# the tool name; SessionStart the source; Notification the type; Subagent* the agent;
# PreCompact the trigger; InstructionsLoaded / ConfigChange the file or kind.
MATCHER_EVENTS = TOOL_EVENTS | {
    "SessionStart", "Notification", "SubagentStart", "SubagentStop", "PreCompact",
    "InstructionsLoaded", "ConfigChange",
}  # fmt: skip
PERMISSION_RE = re.compile(r"^(mcp__[\w-]+(__[\w-]+)?|[A-Z][A-Za-z]+(\(.+\))?)$")
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]+$")
BUNDLE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*(\.[a-zA-Z][a-zA-Z0-9]*){2,}$")


def _hook_group_problems(event: str, g: dict[str, Any]) -> list[str]:
    problems = []
    matcher = g.get("matcher")
    if matcher is not None:
        if event not in MATCHER_EVENTS:
            problems.append(f"hooks.{event}: `matcher` is ignored on this event")
        try:
            re.compile(matcher)
        except re.error:
            problems.append(f"hooks.{event}: matcher {matcher!r} is not a valid regex")
    hooks = g.get("hooks")
    if not isinstance(hooks, list) or not hooks:
        return [*problems, f"hooks.{event}: group without a `hooks` list"]
    for h in hooks:
        if h.get("type") != "command" or not isinstance(h.get("command"), str):
            problems.append(f"hooks.{event}: entry needs type=command and a command")
        if "timeout" in h and not isinstance(h["timeout"], int):
            problems.append(f"hooks.{event}: timeout must be an integer (seconds)")
    return problems


def claude_settings_problems(s: dict[str, Any]) -> list[str]:
    problems = []
    for event, groups in (s.get("hooks") or {}).items():
        if event not in CLAUDE_HOOK_EVENTS:
            problems.append(f"hooks: unknown event `{event}` (it will never fire)")
            continue
        for g in groups:
            problems += _hook_group_problems(event, g)
    for kind in ("allow", "deny", "ask"):
        for rule in (s.get("permissions") or {}).get(kind, []):
            if not PERMISSION_RE.match(rule):
                problems.append(f"permissions.{kind}: {rule!r} is not `Tool` or `Tool(spec)`")
    return problems


def mcp_problems(m: dict[str, Any]) -> list[str]:
    servers = m.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        return ["`mcpServers` missing or empty"]
    problems = []
    for name, cfg in servers.items():
        if "url" in cfg:
            if not str(cfg["url"]).startswith("https://"):
                problems.append(f"{name}: url must be https")
            if cfg.get("type") not in (None, "http", "sse"):
                problems.append(f"{name}: type must be http or sse for a url server")
        elif "command" in cfg:
            if not isinstance(cfg.get("args", []), list):
                problems.append(f"{name}: args must be a list")
        else:
            problems.append(f"{name}: needs `url` (remote) or `command` (stdio)")
        for v in (cfg.get("headers") or {}).values():
            if re.search(r"[A-Za-z0-9_-]{24,}", str(v)) and "${" not in str(v):
                problems.append(f"{name}: header looks like a literal secret; use ${{VAR}}")
    return problems


def codex_config_problems(cfg: dict[str, Any], mcp: dict[str, Any]) -> list[str]:
    problems = []
    if set(cfg.get("mcp_servers", {})) != set(mcp.get("mcpServers", {})):
        problems.append("`.codex/config.toml` mcp_servers differ from .mcp.json (stale adapter)")
    net = cfg.get("sandbox_workspace_write", {}).get("network_access")
    if not isinstance(net, bool):
        problems.append("sandbox_workspace_write.network_access must be a boolean")
    return problems


def eas_problems(e: dict[str, Any]) -> list[str]:
    problems = []
    build = e.get("build") or {}
    for profile in ("development", "preview", "production"):
        if profile not in build:
            problems.append(f"build.{profile} missing")
    for profile in ("preview", "production"):
        p = build.get(profile) or {}
        if not isinstance(p.get("env"), dict):
            problems.append(
                f"build.{profile}.env must be an object (check-eas-shipping-env reads it)"
            )
        if not isinstance(p.get("channel"), str):
            problems.append(f"build.{profile}.channel missing (OTA updates have nowhere to land)")
    return problems


def app_json_problems(a: dict[str, Any]) -> list[str]:
    ex = a.get("expo") or {}
    problems = []
    if not SLUG_RE.match(str(ex.get("slug", ""))):
        problems.append("expo.slug must be kebab-case")
    ios = (ex.get("ios") or {}).get("bundleIdentifier")
    android = (ex.get("android") or {}).get("package")
    if not (ios and BUNDLE_RE.match(ios)):
        problems.append("expo.ios.bundleIdentifier missing or malformed")
    if ios != android:
        problems.append("ios.bundleIdentifier and android.package differ")
    if not ex.get("scheme"):
        problems.append("expo.scheme missing (auth redirects need it)")
    if not ex.get("runtimeVersion"):
        problems.append(
            "expo.runtimeVersion missing (an OTA update could reach an incompatible binary)"
        )
    return problems


def dependabot_problems(d: dict[str, Any]) -> list[str]:
    problems = [] if d.get("version") == 2 else ["version must be 2"]
    ecosystems = set()
    for u in d.get("updates") or []:
        ecosystems.add(u.get("package-ecosystem"))
        if not u.get("directory") or not (u.get("schedule") or {}).get("interval"):
            problems.append(f"{u.get('package-ecosystem')}: needs directory + schedule.interval")
        # Cooldown: a fresh release waits before a PR proposes it, so a malicious or
        # broken publish is usually yanked first. A new major waits longer.
        cool = u.get("cooldown") or {}
        days = cool.get("default-days", 0)
        if not isinstance(days, int) or days < 7:
            problems.append(f"{u.get('package-ecosystem')}: cooldown.default-days must be >= 7")
        elif u.get("package-ecosystem") in ("pip", "npm") and not (
            cool.get("semver-major-days", 0) > days
        ):
            problems.append(
                f"{u.get('package-ecosystem')}: cooldown.semver-major-days must exceed default-days"
            )
    for need in ("pip", "npm", "github-actions"):
        if need not in ecosystems:
            problems.append(f"no `{need}` updates")
    return problems


# ---- the real files -------------------------------------------------------------


def test_claude_settings() -> None:
    assert claude_settings_problems(load_json(SETTINGS)) == []


def test_mcp_json() -> None:
    assert mcp_problems(load_json(ROOT / ".mcp.json")) == []


def test_codex_config_parses_and_mirrors_mcp() -> None:
    path = ROOT / ".codex" / "config.toml"
    assert path.exists(), ".codex/config.toml missing: re-run render.py --adapters-only"
    cfg = tomllib.loads(path.read_text(encoding="utf-8"))
    assert codex_config_problems(cfg, load_json(ROOT / ".mcp.json")) == []


@pytest.mark.parametrize(
    "path",
    sorted((ROOT / ".codex").rglob("*.toml")) + sorted((ROOT / ".codex").rglob("*.json")),
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_codex_files_parse(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    tomllib.loads(text) if path.suffix == ".toml" else json.loads(text)


def test_eas_json() -> None:
    assert eas_problems(load_json(ROOT / "mobile" / "eas.json")) == []


def test_app_json() -> None:
    assert app_json_problems(load_json(ROOT / "mobile" / "app.json")) == []


def test_dependabot() -> None:
    assert (
        dependabot_problems(yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())) == []
    )


@pytest.mark.parametrize(
    "path",
    [p for p in ROOT.glob("**/*.json") if "node_modules" not in p.parts and ".git" not in p.parts],
    ids=lambda p: p.relative_to(ROOT).as_posix(),
)
def test_every_json_file_parses(path: Path) -> None:
    json.loads(path.read_text(encoding="utf-8"))


def test_railway_healthcheck_is_health() -> None:
    path = ROOT / "railway.json"
    if not path.exists():
        pytest.skip("no backend (supabase-only stack)")
    assert load_json(path)["deploy"]["healthcheckPath"] == "/health"


# ---- negative controls ----------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "needle"),
    [
        ({"hooks": {"PreToolUze": []}}, "unknown event"),
        (
            {
                "hooks": {
                    "PreToolUse": [
                        {"matcher": "Bash(", "hooks": [{"type": "command", "command": "x"}]}
                    ]
                }
            },
            "valid regex",
        ),
        (
            {
                "hooks": {
                    "Stop": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]
                }
            },
            "ignored",
        ),
        ({"hooks": {"Stop": [{"hooks": []}]}}, "without a `hooks` list"),
        ({"hooks": {"Stop": [{"hooks": [{"type": "shell", "command": "x"}]}]}}, "type=command"),
        ({"permissions": {"allow": ["bash(ls:*)"]}}, "is not `Tool`"),
    ],
    ids=["event", "matcher-regex", "matcher-ignored", "empty-group", "type", "permission"],
)
def test_settings_rules_can_fail(settings: dict, needle: str) -> None:
    assert any(needle in p for p in claude_settings_problems(settings))


def test_newer_events_and_their_matchers_are_accepted() -> None:
    """The positive half of the event rule: a 2026 event is not "unknown", and a matcher on
    an event that takes one is not "ignored" (the `PreToolUze` control above still fails)."""
    hook = [{"type": "command", "command": "x"}]
    ok = {
        "hooks": {
            "PostCompact": [{"hooks": hook}],
            "WorktreeCreate": [{"hooks": hook}],
            "Notification": [{"matcher": "permission_prompt", "hooks": hook}],
            "SubagentStop": [{"matcher": "reviewer", "hooks": hook}],
            "PreCompact": [{"matcher": "auto", "hooks": hook}],
        }
    }
    assert claude_settings_problems(ok) == []


def test_mcp_rules_can_fail() -> None:
    assert mcp_problems({}) == ["`mcpServers` missing or empty"]
    assert any("needs `url`" in p for p in mcp_problems({"mcpServers": {"x": {}}}))
    assert any("https" in p for p in mcp_problems({"mcpServers": {"x": {"url": "http://a"}}}))
    leak = {
        "mcpServers": {
            "x": {"url": "https://a", "headers": {"Authorization": "Bearer " + "k" * 30}}
        }
    }
    assert any("literal secret" in p for p in mcp_problems(leak))


def test_codex_config_rules_can_fail() -> None:
    assert codex_config_problems({}, {"mcpServers": {"a": {}}})
    ok = {"mcp_servers": {"a": {}}, "sandbox_workspace_write": {"network_access": True}}
    assert codex_config_problems(ok, {"mcpServers": {"a": {}}}) == []


def test_eas_rules_can_fail() -> None:
    bad = {
        "build": {"development": {}, "preview": {"channel": "preview"}, "production": {"env": {}}}
    }
    problems = eas_problems(bad)
    assert any("preview.env" in p for p in problems)
    assert any(
        "production.channel" in p for p in problems
    )


def test_app_json_rules_can_fail() -> None:
    bad = {
        "expo": {
            "slug": "Bad Slug",
            "ios": {"bundleIdentifier": "com.a.b"},
            "android": {"package": "com.a.c"},
        }
    }
    problems = app_json_problems(bad)
    for needle in ("kebab-case", "differ", "scheme", "runtimeVersion"):
        assert any(needle in p for p in problems), needle


def test_dependabot_rules_can_fail() -> None:
    problems = dependabot_problems({"version": 1, "updates": [{"package-ecosystem": "pip"}]})
    assert "version must be 2" in problems
    assert any("`npm`" in p for p in problems)
    assert any("schedule.interval" in p for p in problems)
    assert any("pip: cooldown.default-days" in p for p in problems)
    sched = {"directory": "/", "schedule": {"interval": "weekly"}}
    no_major = dependabot_problems(
        {
            "version": 2,
            "updates": [
                {"package-ecosystem": "pip", **sched, "cooldown": {"default-days": 7}},
                {"package-ecosystem": "npm", **sched, "cooldown": {"default-days": 3}},
                {"package-ecosystem": "github-actions", **sched, "cooldown": {"default-days": 7}},
            ],
        }
    )
    assert no_major == [
        "pip: cooldown.semver-major-days must exceed default-days",
        "npm: cooldown.default-days must be >= 7",
    ]
