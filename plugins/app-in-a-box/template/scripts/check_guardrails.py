#!/usr/bin/env python3
"""Guardrail packs: privacy and safety rules this app enforces in code, not prose.

Which packs are on comes from `privacy/data-map.yaml` → `packs` (no file, or no list,
means `baseline` alone). `baseline` is always on. A pack that is off runs no check at
all, so it can't slow anyone down or raise a false alarm. What each pack enforces, and
why, is in docs/privacy/GUARDRAILS.md:

    baseline   no personal data (email, name, phone, precise location, free text,
               credentials, birth date) in analytics payloads or backend log calls;
               events only through mobile/lib/analytics.ts; the Sentry/PostHog
               scrubbers stay wired; mobile/lib/packs.ts matches the data map
    location   background location only with a declared reason; positions pass
               through coarsen(); location tables have a retention TTL that the prune
               cron enforces; an app that reads location shows <WhoCanSeeMe>
    minors     the age gate stays mounted and turns analytics off for under-age users;
               no ads or third-party tracking SDKs; nothing public by default; no
               user-to-user messaging without a recorded reason
    health     health values never reach analytics or logs (Sentry/PostHog are
               scrubbed at runtime too)
    financial  amounts, balances and account numbers never reach analytics or logs;
               money columns are never floating point
    biometric  no biometric values in analytics or logs; no column stores a face,
               fingerprint or voice template
    ugc        any table holding user content has report and block endpoints and a
               moderation queue (App Store Review Guideline 1.2)

A finding you have a real reason to keep is waived on its own line (or the line above)
with `guardrail-ok(<pack>): <why>`. The reason is the point: review reads it.

Usage:
    python3 scripts/check_guardrails.py           # check (CI, .github/workflows/ci.yml)
    python3 scripts/check_guardrails.py --write   # regenerate mobile/lib/packs.ts
Standard library, plus PyYAML when present (CI installs it; without it only the
`packs:` line of the data map is read).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeGuard

ROOT = Path(__file__).resolve().parents[1]
PACKS = ("baseline", "location", "minors", "health", "ugc", "financial", "biometric")
DATA_MAP = "privacy/data-map.yaml"
PACKS_TS = "mobile/lib/packs.ts"
ANALYTICS_TS = "mobile/lib/analytics.ts"
JOBS = "backend/services/jobs_service.py"
MOBILE_DIRS = ("mobile/app", "mobile/components", "mobile/lib")

# ---- what counts as personal data, by pack ----------------------------------------
# Matched against an identifier split into snake_case words (`userEmail` -> user_email),
# so `page` never matches `age` and `display_name` does match `name`.
PII: dict[str, dict[str, str]] = {
    "baseline": {
        "an email address": r"(^|_)e_?mail(_|$)",
        "a phone number": r"(^|_)(phone|phone_number|mobile_number|msisdn)(_|$)",
        # A bare `name` is too often a thing's name (an upstream, an event, a file).
        "a person's name": r"^(first|last|full|display|real|given|family|legal|middle|user|nick|sur)_?name$",
        "a postal address": r"(^|_)(address|street|postcode|postal_code|zip|zipcode|zip_code)(_|$)",
        "a precise location": r"(^|_)(lat|lng|lon|latitude|longitude|coords?|coordinates|geohash)(_|$)",
        "free text": r"(^|_)(text|body|message|comment|comments|note|notes|query|search_term|content|caption|bio|description|transcript|prompt|reply)(_|$)",
        "a credential": r"(^|_)(password|passcode|secret|token|otp|api_key|jwt|cookie)(_|$)",
        "a date of birth": r"(^|_)(dob|birth|birthday|birthdate|date_of_birth)(_|$)",
    },
    "health": {
        "a health value": r"(^|_)(weight|height|bmi|heart_rate|hrv|bpm|blood|glucose|blood_pressure|symptom|symptoms|diagnosis|diagnoses|medication|medications|medical|vitals?|spo2|sleep|menstrual|cycle_day|pregnancy|pregnant|mood|calories|body_fat|allergy|allergies)(_|$)",
    },
    "financial": {
        "a financial value": r"(^|_)(amount|balance|iban|account_number|card|card_number|pan|cvv|cvc|routing_number|sort_code|bsb|salary|income|merchant|net_worth)(_|$)",
    },
    "biometric": {
        "a biometric value": r"(^|_)(face|faceprint|face_id|face_embedding|fingerprint|voiceprint|iris|retina|biometric|biometrics|palm)(_|$)",
    },
    "minors": {
        "a child's age or school": r"(^|_)(age|birth_year|school|grade|guardian)(_|$)",
    },
}
LOCATION_COLUMN = re.compile(
    r"(^|_)(lat|lng|lon|latitude|longitude|coords?|coordinates|geohash|geog|geom|location)(_|$)"
)
LOCATION_TYPE = re.compile(r"\b(geography|geometry|point)\b", re.I)
POSITION_API = re.compile(
    r"\b(getCurrentPositionAsync|watchPositionAsync|getLastKnownPositionAsync|startLocationUpdatesAsync)\s*\("
)
BACKGROUND_API = re.compile(r"\b(startLocationUpdatesAsync|startGeofencingAsync)\s*\(")
# Ads, attribution and third-party analytics SDKs. Under-age users get none of them;
# product analytics goes through lib/analytics.ts, which the age gate can switch off.
TRACKING_SDKS = re.compile(
    r"^(react-native-google-mobile-ads|expo-ads-\S+|react-native-admob|@react-native-admob/\S+"
    r"|react-native-fbads|react-native-fbsdk-next|react-native-applovin-max|react-native-unity-ads"
    r"|ironsource-mediation|react-native-appodeal|@react-native-firebase/(analytics|admob)"
    r"|@segment/analytics-react-native|@amplitude/analytics-react-native|mixpanel-react-native"
    r"|react-native-appsflyer|react-native-branch|react-native-adjust|@braze/react-native-sdk)$"
)
PUBLIC_DEFAULT = re.compile(
    r"\b(is_public|public|visible|visibility|discoverable|searchable|listed|is_listed|show_in_search)\b"
    r"[^,;]*?\bdefault\s+(true|'public'|'everyone')",
    re.I,
)
MESSAGING_TABLE = re.compile(
    r"^(messages?|direct_messages?|dms?|conversations?|chats?|chat_messages|inbox|threads?)$"
)
UGC_TABLE = re.compile(
    r"^(posts?|comments?|replies|reply|messages?|chat_messages|reviews?|threads?|stories|story|photos?|listings?)$"
)
MONEY_FLOAT = re.compile(
    r"^\s*\"?(\w*(amount|balance|price|total|cost|fee|salary|income)\w*)\"?\s+(real|float\d*|double\s+precision|money)\b",
    re.I | re.M,
)
# A bare `fingerprint` is usually a hash of a request or a key (idempotency_keys has
# one), so only a fingerprint's template, image or minutiae counts.
BIOMETRIC_COLUMN = re.compile(
    r"(^|_)(faceprint|face_(embedding|template|vector|geometry)|fingerprint_(template|image|minutiae)"
    r"|voiceprint|voice_(embedding|template)|iris|retina|palm_print|biometric|biometrics)(_|$)"
)
WAIVER = re.compile(r"guardrail-ok\((\w+)\):\s*(\S.{6,})")


# ---- reading the repo --------------------------------------------------------------


def _read(root: Path, rel: str) -> str:
    p = root / rel
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def load_data_map(root: Path) -> dict:
    """The data map, or {} when absent. Without PyYAML only `packs:` is understood."""
    text = _read(root, DATA_MAP)
    if not text:
        return {}
    try:
        import yaml
    except ImportError:
        return {"packs": _packs_line(text)}
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def _packs_line(text: str) -> list[str]:
    m = re.search(r"^packs:\s*\[([^\]]*)\]", text, re.M)
    if m:
        return [p.strip().strip("'\"") for p in m.group(1).split(",") if p.strip()]
    m = re.search(r"^packs:[ \t]*\n((?:[ \t]+-[ \t]*\S+[ \t]*(?:\n|$))+)", text, re.M)
    return re.findall(r"-\s*['\"]?(\w+)", m.group(1)) if m else []


def enabled_packs(data_map: dict) -> tuple[set[str], list[str]]:
    raw = data_map.get("packs") or []
    if not isinstance(raw, list):
        return {"baseline"}, [f"[baseline] {DATA_MAP}: `packs` must be a list, got {raw!r}"]
    unknown = [str(p) for p in raw if p not in PACKS]
    problems = [
        f"[baseline] {DATA_MAP}: unknown pack {u!r} (known: {', '.join(PACKS)})" for u in unknown
    ]
    return {"baseline"} | {str(p) for p in raw if p in PACKS}, problems


def _files(root: Path, dirs: Iterable[str], suffixes: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for d in dirs:
        base = root / d
        if base.is_dir():
            out += [
                p
                for p in base.rglob("*")
                if p.is_file()
                and p.suffix in suffixes
                and "__tests__" not in p.parts
                and "node_modules" not in p.parts
                and not p.name.endswith((".test.ts", ".test.tsx"))
            ]
    return sorted(out)


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def waived(lines: list[str], lineno: int, pack: str) -> bool:
    """`guardrail-ok(<pack>): <why>` on the finding's line or the line above."""
    for i in (lineno - 1, lineno - 2):
        if 0 <= i < len(lines):
            for m in WAIVER.finditer(lines[i]):
                if m.group(1) == pack:
                    return True
    return False


def _snake(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


# A measure of the thing, or a yes/no about it, is not the thing: `query_length`,
# `note_count`, `has_email` are fine to send. Mirrored in mobile/lib/privacy.ts.
MEASURE = re.compile(r"(^(has|is)_|_(count|length|len|size|chars|words|ms|total|bucket)$)")


def classify(identifier: str, packs: set[str]) -> tuple[str, str] | None:
    """(pack, what) if this identifier names personal data an enabled pack forbids."""
    word = _snake(identifier)
    if MEASURE.search(word):
        return None
    for pack, kinds in PII.items():
        if pack not in packs:
            continue
        for what, pattern in kinds.items():
            if re.search(pattern, word):
                return pack, what
    return None


def _strip_js(text: str) -> str:
    """Comments and string contents blanked (newlines kept, so line numbers hold).
    A template literal keeps its `${...}` expressions."""

    def blank(m: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", m.group(0))

    def template(m: re.Match[str]) -> str:
        return re.sub(
            r"\$\{([^}]*)\}|[^\n]",
            lambda x: x.group(1) or (" " if x.group(0) != "\n" else "\n"),
            m.group(0),
        )

    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    text = re.sub(r"(?<![:\\])//[^\n]*", blank, text)
    text = re.sub(r"`(?:\\.|[^`\\])*`", template, text, flags=re.S)
    return re.sub(r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'", blank, text)


def _balanced(text: str, start: int, open_: str = "(", close: str = ")") -> int:
    """Index just past the bracket that closes the one at `start`."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == open_:
            depth += 1
        elif text[i] == close:
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def migrations(root: Path) -> list[tuple[str, str]]:
    d = root / "supabase" / "migrations"
    return [(_rel(root, p), p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.sql"))]


def _sql_code(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", re.sub(r"/\*.*?\*/", "", sql, flags=re.S))


def tables(root: Path) -> dict[str, dict[str, str]]:
    """{table: {column: type}} from every `create table` and `add column` in the migrations."""
    out: dict[str, dict[str, str]] = {}
    for _, sql in migrations(root):
        code = _sql_code(sql)
        for m in re.finditer(
            r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?(\w+)\"?\s*\(", code, re.I
        ):
            body = code[m.end() : _balanced(code, m.end() - 1) - 1]
            cols = out.setdefault(m.group(1).lower(), {})
            for part in _split_top(body):
                cm = re.match(r"\s*\"?(\w+)\"?\s+(.+)", part, re.S)
                if cm and cm.group(1).lower() not in {
                    "primary",
                    "unique",
                    "constraint",
                    "foreign",
                    "check",
                    "exclude",
                }:
                    cols[cm.group(1).lower()] = " ".join(cm.group(2).split()).lower()
        for m in re.finditer(
            r"alter\s+table\s+(?:if\s+exists\s+)?(?:only\s+)?(?:public\.)?\"?(\w+)\"?\s+([^;]*)",
            code,
            re.I,
        ):
            for cm in re.finditer(
                r"add\s+column\s+(?:if\s+not\s+exists\s+)?\"?(\w+)\"?\s+([^,]+)", m.group(2), re.I
            ):
                out.setdefault(m.group(1).lower(), {})[cm.group(1).lower()] = " ".join(
                    cm.group(2).split()
                ).lower()
    return out


def _split_top(body: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    return parts + [cur]


def mapped_columns(data_map: dict) -> dict[str, dict[str, str]]:
    """{table: {column: category}} from the data map (when it has one)."""
    out: dict[str, dict[str, str]] = {}
    specs = data_map.get("tables")
    for table, spec in (specs if isinstance(specs, dict) else {}).items():
        cols = spec.get("columns") if isinstance(spec, dict) else None
        for col, meta in (cols if isinstance(cols, dict) else {}).items():
            cat = meta.get("category", "") if isinstance(meta, dict) else ""
            out.setdefault(str(table).lower(), {})[str(col).lower()] = str(cat)
    return out


# ---- baseline ----------------------------------------------------------------------


def _analytics_helper_keys(root: Path, packs: set[str]) -> list[str]:
    """The object keys inside lib/analytics.ts's `analytics = {...}` (helper names aside)."""
    problems: list[str] = []
    src = _read(root, ANALYTICS_TS)
    if not src:
        return problems
    lines = src.splitlines()
    code = _strip_js(src)
    m = re.search(r"export\s+const\s+analytics\s*=\s*\{", code)
    if not m:
        return problems
    start = m.end() - 1
    block = code[start : _balanced(code, start, "{", "}")]
    helpers = set(re.findall(r"^\s{2}(\w+)\s*:\s*\(", block, re.M))
    for km in re.finditer(r"(\w+)\s*\??\s*:", block):
        name = km.group(1)
        if name in helpers:
            continue
        hit = classify(name, packs)
        lineno = code.count("\n", 0, start + km.start()) + 1
        if hit and not waived(lines, lineno, hit[0]):
            problems.append(
                f"[{hit[0]}] {ANALYTICS_TS}:{lineno}: analytics payload key `{name}` "
                f"looks like {hit[1]}; send an id, a count or a category instead"
            )
    return problems


def _analytics_call_args(rel: str, text: str, packs: set[str]) -> list[str]:
    """The identifiers passed to any `analytics.*(...)` call in one file."""
    problems: list[str] = []
    lines, code = text.splitlines(), _strip_js(text)
    for cm in re.finditer(r"\banalytics\.\w+\s*\(", code):
        args = code[cm.end() - 1 : _balanced(code, cm.end() - 1)]
        seen: set[str] = set()
        for im in re.finditer(r"[A-Za-z_]\w*", args):
            name = im.group(0)
            hit = classify(name, packs)
            lineno = code.count("\n", 0, cm.end() - 1 + im.start()) + 1
            if hit and name not in seen and not waived(lines, lineno, hit[0]):
                seen.add(name)
                problems.append(
                    f"[{hit[0]}] {rel}:{lineno}: `{name}` passed to analytics looks like "
                    f"{hit[1]}; analytics gets ids, counts and categories, never the value"
                )
    return problems


def analytics_pii(root: Path, packs: set[str]) -> list[str]:
    """Personal data in an analytics payload: in a helper's parameters or object keys in
    lib/analytics.ts, or in the arguments of any `analytics.*(...)` call."""
    problems = _analytics_helper_keys(root, packs)
    for path in _files(root, MOBILE_DIRS, (".ts", ".tsx")):
        rel = _rel(root, path)
        if rel != ANALYTICS_TS:
            problems += _analytics_call_args(rel, path.read_text(encoding="utf-8"), packs)
    return problems


def analytics_bypass(root: Path, _packs: set[str]) -> list[str]:
    """PostHog called directly: the payload lint, the scrubber and the age gate all live
    in lib/analytics.ts, so an event fired around it skips every one of them."""
    problems = []
    for path in _files(root, MOBILE_DIRS, (".ts", ".tsx")):
        rel = _rel(root, path)
        if rel in (ANALYTICS_TS, "mobile/lib/analytics-optin.ts"):
            continue
        text = path.read_text(encoding="utf-8")
        lines, code = text.splitlines(), _strip_js(text)
        for m in re.finditer(r"\bposthog\??\.(capture|identify|screen|register|alias)\s*\(", code):
            lineno = code.count("\n", 0, m.start()) + 1
            if not waived(lines, lineno, "baseline"):
                problems.append(
                    f"[baseline] {rel}:{lineno}: posthog.{m.group(1)}() called directly; add a "
                    f"helper to {ANALYTICS_TS} so the payload lint, scrubber and age gate apply"
                )
    return problems


_LOG_LEVELS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
_LOGGERS = {"logger", "log", "logging", "_logger", "_log", "LOGGER", "LOG"}
_LOG_KWARGS = {"exc_info", "stack_info", "stacklevel"}


def _is_log_call(node: ast.AST) -> TypeGuard[ast.Call]:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LOG_LEVELS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in _LOGGERS
    )


def _node_names(sub: ast.AST) -> list[str]:
    """The names one AST node contributes: a variable, an attribute, or a dict's str keys."""
    if isinstance(sub, ast.Name):
        return [sub.id]
    if isinstance(sub, ast.Attribute):
        return [sub.attr]
    if isinstance(sub, ast.Dict):
        return [
            k.value for k in sub.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
    return []


def _logged_names(call: ast.Call) -> list[str]:
    """Every name in a log call's arguments (exc_info and friends aside), first-seen order."""
    names: list[str] = []
    for arg in [*call.args, *(k.value for k in call.keywords if k.arg not in _LOG_KWARGS)]:
        for sub in ast.walk(arg):
            names += _node_names(sub)
    return list(dict.fromkeys(names))


def _logs_pii_file(rel: str, text: str, packs: set[str]) -> list[str]:
    problems: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return problems
    lines = text.splitlines()
    for node in ast.walk(tree):
        if not _is_log_call(node):
            continue
        for name in _logged_names(node):
            hit = classify(name, packs)
            if hit and not waived(lines, node.lineno, hit[0]):
                problems.append(
                    f"[{hit[0]}] {rel}:{node.lineno}: `{name}` logged; it looks like "
                    f"{hit[1]}. Log the id or the error type instead"
                )
    return problems


def logs_pii(root: Path, packs: set[str]) -> list[str]:
    """Personal data handed to the backend logger. Logs land in Railway (and anything it
    ships them to) for weeks, outside the database's RLS and the account deletion."""
    problems: list[str] = []
    base = root / "backend"
    for path in sorted(base.rglob("*.py")) if base.is_dir() else []:
        problems += _logs_pii_file(_rel(root, path), path.read_text(encoding="utf-8"), packs)
    return problems


def _function_body(code: str, name: str) -> str:
    m = re.search(rf"function\s+{name}\s*\([^)]*\)[^{{]*\{{", code)
    return code[m.end() - 1 : _balanced(code, m.end() - 1, "{", "}")] if m else ""


def scrubbers_wired(root: Path, _packs: set[str]) -> list[str]:
    """The runtime half of the lints: values that slip past review are still stripped."""
    problems = []
    analytics = _strip_js(_read(root, ANALYTICS_TS))
    if analytics and "scrubProps(" not in _function_body(analytics, "capture"):
        problems.append(
            f"[baseline] {ANALYTICS_TS}: capture() no longer runs scrubProps() (lib/privacy.ts)"
        )
    wants = [
        (
            "mobile/lib/monitoring.ts",
            r"beforeSend:\s*scrubSentryEvent",
            "Sentry.init has no beforeSend: scrubSentryEvent",
        ),
        (
            "backend/observability.py",
            r"before_send=scrub_event",
            "sentry_sdk.init has no before_send=scrub_event",
        ),
    ]
    for rel, pattern, what in wants:
        text = _read(root, rel)
        if text and not re.search(pattern, text):
            problems.append(f"[baseline] {rel}: {what}")
    return problems


def packs_ts_text(packs: set[str]) -> str:
    on = ", ".join(json.dumps(p) for p in PACKS if p in packs)
    ids = " | ".join(json.dumps(p) for p in PACKS)
    return (
        "/**\n"
        " * The guardrail packs this app has turned on, from privacy/data-map.yaml → packs.\n"
        " * GENERATED by `python3 scripts/check_guardrails.py --write`; the check fails in CI\n"
        " * while this file and the data map disagree. What each pack does:\n"
        " * docs/privacy/GUARDRAILS.md.\n"
        " */\n"
        f"export type PackId = {ids};\n\n"
        f"export const PACKS: readonly PackId[] = [{on}];\n\n"
        "export function packOn(id: PackId): boolean {\n"
        "  return PACKS.includes(id);\n"
        "}\n"
    )


def packs_ts_current(root: Path, packs: set[str]) -> list[str]:
    if not (root / "mobile" / "lib").is_dir():
        return []
    if _read(root, PACKS_TS) != packs_ts_text(packs):
        return [
            f"[baseline] {PACKS_TS} does not match {DATA_MAP} → packs ({', '.join(sorted(packs))}); "
            "run: python3 scripts/check_guardrails.py --write"
        ]
    return []


# ---- location ----------------------------------------------------------------------


def _permission_reasons(data_map: dict) -> dict[str, str]:
    perms = data_map.get("permissions") or {}
    return (
        {str(k).lower(): str(v or "") for k, v in perms.items()} if isinstance(perms, dict) else {}
    )


def background_location(root: Path, _packs: set[str], data_map: dict | None = None) -> list[str]:
    """Background location is the permission stores and users scrutinise most: it needs a
    reason in the data map AND a purpose string the OS shows the user."""
    data_map = data_map if data_map is not None else load_data_map(root)
    try:
        expo = json.loads(_read(root, "mobile/app.json") or "{}").get("expo", {})
    except json.JSONDecodeError:
        return []
    where, purpose = _background_location_config(expo)
    where += [
        _rel(root, path)
        for path in _files(root, MOBILE_DIRS, (".ts", ".tsx"))
        if BACKGROUND_API.search(_strip_js(path.read_text(encoding="utf-8")))
    ]
    if not where:
        return []
    return _background_location_problems(where, purpose, _permission_reasons(data_map))


def _background_location_config(expo: dict) -> tuple[list[str], str]:
    """Where app.json asks for background location, and the purpose string it gives."""
    plist = (expo.get("ios") or {}).get("infoPlist") or {}
    where: list[str] = []
    if "location" in (plist.get("UIBackgroundModes") or []):
        where.append("ios.infoPlist.UIBackgroundModes")
    perms = [str(p) for p in ((expo.get("android") or {}).get("permissions") or [])]
    if any(p.endswith("ACCESS_BACKGROUND_LOCATION") for p in perms):
        where.append("android.permissions ACCESS_BACKGROUND_LOCATION")
    purpose = str(plist.get("NSLocationAlwaysAndWhenInUseUsageDescription") or "")
    for opts in _expo_location_options(expo):
        if opts.get("isAndroidBackgroundLocationEnabled") or opts.get(
            "isIosBackgroundLocationEnabled"
        ):
            where.append("the expo-location plugin's background options")
        purpose = purpose or str(opts.get("locationAlwaysAndWhenInUsePermission") or "")
    return where, purpose


def _expo_location_options(expo: dict) -> list[dict]:
    """The options dict of each expo-location plugin entry ({} when it has none)."""
    out = []
    for plugin in expo.get("plugins") or []:
        if isinstance(plugin, list) and plugin and plugin[0] == "expo-location":
            out.append(plugin[1] if len(plugin) > 1 and isinstance(plugin[1], dict) else {})
    return out


def _background_location_problems(
    where: list[str], purpose: str, reasons: dict[str, str]
) -> list[str]:
    problems = []
    reason = next(
        (v for k, v in reasons.items() if "location" in k and ("background" in k or "always" in k)),
        "",
    )
    if len(reason.strip()) < 20:
        problems.append(
            f"[location] background location is requested ({'; '.join(where)}) but {DATA_MAP} → "
            'permissions declares no reason (a `location_background: "<why the user benefits>"` entry)'
        )
    if len(purpose.strip()) < 20:
        problems.append(
            "[location] background location is requested but no purpose string tells the user why "
            "(expo-location plugin `locationAlwaysAndWhenInUsePermission`, or "
            "ios.infoPlist.NSLocationAlwaysAndWhenInUseUsageDescription)"
        )
    return problems


def _position_readers(root: Path) -> list[tuple[str, str, list[str], int]]:
    out = []
    for path in _files(root, MOBILE_DIRS, (".ts", ".tsx")):
        rel = _rel(root, path)
        if rel == "mobile/lib/location.ts":
            continue
        text = path.read_text(encoding="utf-8")
        code = _strip_js(text)
        for m in POSITION_API.finditer(code):
            out.append((rel, code, text.splitlines(), code.count("\n", 0, m.start()) + 1))
    return out


def precise_location(root: Path, _packs: set[str]) -> list[str]:
    problems = []
    for rel, code, lines, lineno in _position_readers(root):
        if "coarsen(" not in code and not waived(lines, lineno, "location"):
            problems.append(
                f"[location] {rel}:{lineno}: reads a position without coarsen() "
                "(mobile/lib/location.ts); round it, or say why it must be precise with "
                "`guardrail-ok(location): <why>`"
            )
    return problems


def retention_registry(root: Path) -> set[str]:
    text = _read(root, JOBS)
    if not text:
        return set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "RETENTION" for t in targets) and isinstance(
            value, ast.Dict
        ):
            return {
                k.value
                for k in value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    return set()


def location_tables(root: Path, data_map: dict) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for table, cols in tables(root).items():
        hits = [c for c, t in cols.items() if LOCATION_COLUMN.search(c) or LOCATION_TYPE.search(t)]
        if hits:
            found[table] = hits
    for table, cols in mapped_columns(data_map).items():
        hits = [c for c, cat in cols.items() if cat == "location"]
        if hits:
            found.setdefault(table, []).extend(h for h in hits if h not in found.get(table, []))
    return found


def location_retention(root: Path, _packs: set[str], data_map: dict | None = None) -> list[str]:
    """A location history is the most revealing table an app can hold; it is pruned on a
    TTL by the existing prune cron (RETENTION in backend/services/jobs_service.py)."""
    data_map = data_map if data_map is not None else load_data_map(root)
    kept = retention_registry(root)
    return [
        f"[location] table `{t}` stores location ({', '.join(cols)}) but has no TTL in "
        f"{JOBS} → RETENTION, so the prune cron never deletes it"
        for t, cols in sorted(location_tables(root, data_map).items())
        if t not in kept
    ]


def who_can_see_me(root: Path, _packs: set[str]) -> list[str]:
    readers = _position_readers(root)
    if not readers:
        return []
    shown = any(
        "<WhoCanSeeMe" in p.read_text(encoding="utf-8")
        for p in _files(root, ("mobile/app",), (".tsx",))
    )
    if shown:
        return []
    return [
        f"[location] the app reads location ({readers[0][0]}) but no screen under mobile/app/ "
        "renders <WhoCanSeeMe> (components/ui/WhoCanSeeMe.tsx), so users can't see who sees them"
    ]


# ---- minors ------------------------------------------------------------------------


def age_gate(root: Path, _packs: set[str]) -> list[str]:
    problems = []
    app_files = _files(root, ("mobile/app",), (".tsx",))
    if not any("<AgeGate" in p.read_text(encoding="utf-8") for p in app_files):
        problems.append(
            "[minors] no screen under mobile/app/ renders <AgeGate> (components/ui/AgeGate.tsx); "
            "ask age before collecting anything"
        )
    analytics = _strip_js(_read(root, ANALYTICS_TS))
    if analytics and "suppressed" not in _function_body(analytics, "capture"):
        problems.append(
            f"[minors] {ANALYTICS_TS}: capture() no longer checks the age gate's suppression, "
            "so events still fire for under-age users"
        )
    return problems


def tracking_sdks(root: Path, _packs: set[str]) -> list[str]:
    try:
        pkg = json.loads(_read(root, "mobile/package.json") or "{}")
    except json.JSONDecodeError:
        return []
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    return [
        f"[minors] mobile/package.json depends on `{d}`, an ads/attribution/analytics SDK; "
        "under-age users get none (product analytics goes through lib/analytics.ts)"
        for d in sorted(deps)
        if TRACKING_SDKS.match(d)
    ]


def public_by_default(root: Path, _packs: set[str]) -> list[str]:
    problems = []
    for rel, sql in migrations(root):
        lines = sql.splitlines()
        for i, line in enumerate(lines, 1):
            code = re.sub(r"--.*", "", line)
            if PUBLIC_DEFAULT.search(code) and not waived(lines, i, "minors"):
                problems.append(
                    f"[minors] {rel}:{i}: a visibility column defaults to public; a child's "
                    "profile and content start private (default false / 'private')"
                )
    return problems


def _table_waived(sql: str, table: str, pack: str) -> bool:
    lines = sql.splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(
            rf"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?{table}\b", line, re.I
        ):
            return waived(lines, i, pack)
    return False


def messaging(root: Path, _packs: set[str]) -> list[str]:
    problems = []
    for rel, sql in migrations(root):
        for m in re.finditer(
            r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?(\w+)", _sql_code(sql), re.I
        ):
            name = m.group(1).lower()
            if MESSAGING_TABLE.match(name) and not _table_waived(sql, name, "minors"):
                problems.append(
                    f"[minors] {rel}: table `{name}` looks like user-to-user messaging, which a "
                    "children's app leaves off by default; if the owner chose it, record why on "
                    "the create line with `guardrail-ok(minors): <why>`"
                )
    return problems


# ---- financial / biometric ---------------------------------------------------------


def money_columns(root: Path, _packs: set[str]) -> list[str]:
    problems = []
    for rel, sql in migrations(root):
        lines = sql.splitlines()
        code = _sql_code(sql)
        for m in MONEY_FLOAT.finditer(code):
            lineno = code.count("\n", 0, m.start()) + 1
            if not waived(lines, lineno, "financial"):
                problems.append(
                    f"[financial] {rel}:{lineno}: money column `{m.group(1)}` is {m.group(3)}; "
                    "store an integer in minor units (bigint cents) plus a currency code"
                )
    return problems


def biometric_columns(root: Path, _packs: set[str]) -> list[str]:
    problems = []
    for rel, sql in migrations(root):
        for table, cols in _tables_in(sql).items():
            for col in cols:
                if BIOMETRIC_COLUMN.search(col) and not _column_waived(sql, col, "biometric"):
                    problems.append(
                        f"[biometric] {rel}: `{table}.{col}` looks like a stored biometric "
                        "template; match on the device (Face ID / fingerprint APIs) and store none"
                    )
    return problems


def _tables_in(sql: str) -> dict[str, list[str]]:
    code = _sql_code(sql)
    out: dict[str, list[str]] = {}
    for m in re.finditer(
        r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?\"?(\w+)\"?\s*\(", code, re.I
    ):
        body = code[m.end() : _balanced(code, m.end() - 1) - 1]
        out[m.group(1).lower()] = [
            cm.group(1).lower()
            for part in _split_top(body)
            if (cm := re.match(r"\s*\"?(\w+)\"?\s+\S", part))
        ]
    for m in re.finditer(
        r"alter\s+table\s+(?:[\w\s]*?)(?:public\.)?\"?(\w+)\"?\s+add\s+column\s+(?:if\s+not\s+exists\s+)?\"?(\w+)",
        code,
        re.I,
    ):
        out.setdefault(m.group(1).lower(), []).append(m.group(2).lower())
    return out


def _column_waived(sql: str, col: str, pack: str) -> bool:
    lines = sql.splitlines()
    return any(
        re.search(rf"\b{col}\b", ln) and waived(lines, i, pack) for i, ln in enumerate(lines, 1)
    )


# ---- ugc ---------------------------------------------------------------------------


# Template tables the data map files under `ugc` for the store answers, but that hold no
# content other users can see: idempotency_keys.response_body replays a save's own answer
# to the phone that retried it, for 24 hours. Reporting and blocking have nothing to act on.
_NOT_SHARED_CONTENT = {"idempotency_keys"}


def ugc_tables(root: Path, data_map: dict) -> list[str]:
    found = set()
    for table in tables(root):
        if UGC_TABLE.match(table):
            found.add(table)
    for table, cols in mapped_columns(data_map).items():
        if "ugc" in cols.values() and table not in _NOT_SHARED_CONTENT:
            found.add(table)
    return sorted(found)


def ugc_moderation(root: Path, _packs: set[str], data_map: dict | None = None) -> list[str]:
    """App Store Review Guideline 1.2: an app with user-generated content needs a way to
    report it (with timely responses) and to block abusive users."""
    data_map = data_map if data_map is not None else load_data_map(root)
    content = ugc_tables(root, data_map)
    if not content:
        return []
    have = tables(root)
    routes = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted((root / "backend" / "routers").rglob("*.py"))
    )
    route_paths = re.findall(r"@\w+\.(?:post|put)\(\s*[\"']([^\"']*)", routes)
    problems = []
    tag = f"[ugc] user content in {', '.join(f'`{t}`' for t in content)}, but"
    reports = [t for t in have if re.search(r"reports?$", t)]
    if not reports:
        problems.append(f"{tag} no reports table (e.g. `content_reports`) to queue what users flag")
    elif not any("status" in have[t] or "resolved_at" in have[t] for t in reports):
        problems.append(
            f"{tag} the reports table has no `status`/`resolved_at`, so nobody can work the queue"
        )
    if not any(re.search(r"(blocks?|blocked_users)$", t) for t in have):
        problems.append(f"{tag} no blocks table (e.g. `user_blocks`) so users can block an abuser")
    if not any("report" in p for p in route_paths):
        problems.append(f"{tag} no POST endpoint under backend/routers/ whose path says `report`")
    if not any("block" in p for p in route_paths):
        problems.append(f"{tag} no POST endpoint under backend/routers/ whose path says `block`")
    return problems


# ---- the packs ---------------------------------------------------------------------

Check = Callable[..., list[str]]
CHECKS: dict[str, list[Check]] = {
    "baseline": [analytics_pii, analytics_bypass, logs_pii, scrubbers_wired],
    "location": [background_location, precise_location, location_retention, who_can_see_me],
    "minors": [age_gate, tracking_sdks, public_by_default, messaging],
    # health / financial / biometric widen the analytics + logs lints (PII above), which
    # run under baseline with every enabled pack's patterns.
    "health": [],
    "financial": [money_columns],
    "biometric": [biometric_columns],
    "ugc": [ugc_moderation],
}


def check(root: Path) -> list[str]:
    data_map = load_data_map(root)
    packs, problems = enabled_packs(data_map)
    problems += packs_ts_current(root, packs)
    for pack in PACKS:
        if pack not in packs:
            continue  # a pack that is off costs nothing
        for fn in CHECKS[pack]:
            if "data_map" in fn.__code__.co_varnames:
                problems += fn(root, packs, data_map)
            else:
                problems += fn(root, packs)
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else ROOT
    if "--write" in argv:
        packs, _ = enabled_packs(load_data_map(root))
        (root / PACKS_TS).write_text(packs_ts_text(packs), encoding="utf-8")
        print(f"check_guardrails: wrote {PACKS_TS} ({', '.join(p for p in PACKS if p in packs)})")
        return 0
    problems = check(root)
    for p in problems:
        print(f"check_guardrails: {p}")
    if not problems:
        packs, _ = enabled_packs(load_data_map(root))
        print(f"check_guardrails: clean ({', '.join(p for p in PACKS if p in packs)})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
