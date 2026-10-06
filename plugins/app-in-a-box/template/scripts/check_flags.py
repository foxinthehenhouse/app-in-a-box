#!/usr/bin/env python3
"""Feature-flag registry guard (CI): every flag has an owner and an expiry.

Reads both registries without importing them: FLAGS in `mobile/lib/flags.ts` and
FLAGS in `backend/flags.py`. A flag fails the build when it has

- no `owner` ("@handle": who decides when it goes),
- no `expires`, or one that isn't a real YYYY-MM-DD date, or one more than a year out
  (a flag "until 2099" is a flag nobody will remove),
- a name that isn't lowercase-hyphenated, or is `kill-*` without being a kill switch
  (or a kill switch not named `kill-*`),
- a kill switch whose default is anything but `false`: a kill switch is OFF in normal
  running, so a missing, deleted or unreachable PostHog flag leaves the feature on,
- a different default or kill-switch setting on the two sides for the same name.

A flag past its expiry is NOT a failure (CI must not go red because a date passed with
no change): it's printed as a warning here, and the `next` skill surfaces it from
`--stale` so someone removes the flag or extends it.

    python3 scripts/check_flags.py              # exit 1 on a broken registry
    python3 scripts/check_flags.py --stale      # JSON list of expired flags
    python3 scripts/check_flags.py --today 2027-01-01   # pin the date (tests)

Standard library only: `.agents/skills/next/signals.py` imports it.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MOBILE = Path("mobile/lib/flags.ts")
BACKEND = Path("backend/flags.py")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
OWNER_RE = re.compile(r"^@[A-Za-z0-9_.-]+$")
MAX_DAYS = 366
_BACKEND_FIELDS = ("default", "owner", "expires", "description", "kill_switch")


# ---- reading the registries ------------------------------------------------------


def _matching_brace(text: str, start: int) -> int:
    """Index of the `}` closing the `{` at `start` (strings and comments skipped)."""
    depth, i, n = 0, start, len(text)
    while i < n:
        c = text[i]
        if c in "\"'`":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
        elif text.startswith("/*", i):
            i = text.find("*/", i)
            i = n if i < 0 else i + 1
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces")


def _ts_value(raw: str) -> Any:
    raw = raw.strip().rstrip(",").strip()
    if raw in ("true", "false"):
        return raw == "true"
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'`":
        return raw[1:-1]
    return raw


def read_mobile(text: str) -> dict[str, dict[str, Any]]:
    """FLAGS from flags.ts: `"name": { default: ..., owner: "...", ... }` entries."""
    m = re.search(r"export\s+const\s+FLAGS\b[^=]*=\s*\{", text)
    if not m:
        raise ValueError("no `export const FLAGS = {` found")
    body = text[m.end() : _matching_brace(text, m.end() - 1)]
    flags: dict[str, dict[str, Any]] = {}
    pos = 0
    entry = re.compile(r"""["']?([A-Za-z0-9_-]+)["']?\s*:\s*\{""")
    while (e := entry.search(body, pos)) is not None:
        end = _matching_brace(body, e.end() - 1)
        inner = re.sub(r"//[^\n]*|/\*.*?\*/", "", body[e.end() : end], flags=re.S)
        fields = {
            k: _ts_value(v)
            for k, v in re.findall(r"""(\w+)\s*:\s*("[^"]*"|'[^']*'|`[^`]*`|[^,\n]+)""", inner)
        }
        flags[e.group(1)] = {
            "default": fields.get("default"),
            "owner": fields.get("owner"),
            "expires": fields.get("expires"),
            "description": fields.get("description"),
            "kill_switch": fields.get("killSwitch") is True,
        }
        pos = end + 1
    return flags


def _backend_flag(call: ast.expr) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if isinstance(call, ast.Call):
        fields.update(zip(_BACKEND_FIELDS, call.args, strict=False))
        fields.update({kw.arg: kw.value for kw in call.keywords if kw.arg})
    out: dict[str, Any] = {}
    for name in _BACKEND_FIELDS:
        try:
            out[name] = ast.literal_eval(fields[name]) if name in fields else None
        except ValueError:
            out[name] = None
    out["kill_switch"] = out["kill_switch"] is True
    return out


def read_backend(text: str) -> dict[str, dict[str, Any]]:
    """FLAGS from flags.py: `"name": Flag(default=..., owner=..., ...)` entries."""
    for node in ast.parse(text).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        value = getattr(node, "value", None)
        if not (isinstance(target, ast.Name) and target.id == "FLAGS"):
            continue
        if not isinstance(value, ast.Dict):
            raise ValueError("FLAGS is not a dict literal")
        flags: dict[str, dict[str, Any]] = {}
        for key, call in zip(value.keys, value.values, strict=True):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                raise ValueError("every FLAGS key must be a string literal")
            flags[key.value] = _backend_flag(call)
        return flags
    raise ValueError("no FLAGS registry found")


def registries(root: Path) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for rel, reader in ((MOBILE, read_mobile), (BACKEND, read_backend)):
        path = root / rel
        if path.is_file():
            out[str(rel)] = reader(path.read_text(encoding="utf-8"))
    return out


# ---- the rules ---------------------------------------------------------------------


def _date(value: Any) -> dt.date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def _owner_problems(owner: Any) -> list[str]:
    if not isinstance(owner, str) or not owner.strip():
        return ['no owner (who decides when it goes, e.g. "@alex")']
    if not OWNER_RE.match(owner):
        return [f'owner {owner!r} must be a "@handle"']
    return []


def _expiry_problems(expires: Any, today: dt.date) -> list[str]:
    when = _date(expires)
    if expires in (None, ""):
        return ['no expiry (add `expires: "YYYY-MM-DD"`: when to remove or extend it)']
    if when is None:
        return [f"expires {expires!r} is not a YYYY-MM-DD date"]
    if (when - today).days > MAX_DAYS:
        return [f"expires {expires} is more than a year out; pick a date within {MAX_DAYS} days"]
    return []


def _kill_switch_problems(name: str, spec: dict[str, Any]) -> list[str]:
    problems = []
    kill = spec.get("kill_switch") is True
    if name.startswith("kill-") and not kill:
        problems.append("is named kill-* but is not marked as a kill switch")
    if kill and not name.startswith("kill-"):
        problems.append("is a kill switch, so name it `kill-<feature>`")
    if kill and spec.get("default") is not False:
        problems.append(
            "is a kill switch, so its default must be false (feature on while PostHog is "
            "missing, deleted or down)"
        )
    return problems


def flag_problems(name: str, spec: dict[str, Any], today: dt.date) -> list[str]:
    problems = []
    if not NAME_RE.match(name):
        problems.append("name must be lowercase-hyphenated, e.g. `new-onboarding`")
    if spec.get("default") is None:
        problems.append("no `default` (the value every user gets without PostHog)")
    problems += _owner_problems(spec.get("owner"))
    problems += _expiry_problems(spec.get("expires"), today)
    if not isinstance(spec.get("description"), str) or not spec["description"].strip():
        problems.append("no description (what it gates, in one line)")
    return problems + _kill_switch_problems(name, spec)


def problems(root: Path, today: dt.date) -> list[str]:
    try:
        regs = registries(root)
    except (ValueError, SyntaxError) as exc:
        return [f"could not read a flag registry: {exc}"]
    out = []
    for source, flags in regs.items():
        for name, spec in flags.items():
            out += [f"{source}: {name}: {p}" for p in flag_problems(name, spec, today)]
    if len(regs) == 2:
        (a_src, a), (b_src, b) = regs.items()
        for name in sorted(set(a) & set(b)):
            for field in ("default", "kill_switch"):
                if a[name].get(field) != b[name].get(field):
                    out.append(
                        f"{name}: {field} is {a[name].get(field)!r} in {a_src} but "
                        f"{b[name].get(field)!r} in {b_src}; one switch, one meaning"
                    )
    return out


def stale(root: Path, today: dt.date) -> list[dict[str, Any]]:
    """Flags past their expiry, oldest first. Never raises (the SessionStart path reads it)."""
    try:
        regs = registries(root)
    except (ValueError, SyntaxError, OSError):
        return []
    found = []
    for source, flags in regs.items():
        for name, spec in flags.items():
            when = _date(spec.get("expires"))
            if when is not None and when < today:
                found.append(
                    {
                        "flag": name,
                        "where": source,
                        "owner": spec.get("owner"),
                        "expired": when.isoformat(),
                        "days_over": (today - when).days,
                    }
                )
    return sorted(found, key=lambda f: -f["days_over"])


def main(argv: list[str]) -> int:
    today = dt.date.today()
    if "--today" in argv:
        today = dt.date.fromisoformat(argv[argv.index("--today") + 1])
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else ROOT
    if "--stale" in argv:
        print(json.dumps(stale(root, today), indent=2))
        return 0
    found = problems(root, today)
    for f in stale(root, today):
        print(
            f"check_flags: warning: {f['where']}: {f['flag']} expired {f['expired']} "
            f"({f['owner']}): remove it, or extend `expires` if it must stay"
        )
    if found:
        print("check_flags FAILED:\n" + "\n".join(f"  - {p}" for p in found), file=sys.stderr)
        return 1
    count = sum(len(f) for f in registries(root).values())
    print(f"check_flags: {count} flag(s), each with an owner and an expiry")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
