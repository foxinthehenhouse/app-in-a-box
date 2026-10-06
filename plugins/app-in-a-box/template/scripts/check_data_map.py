#!/usr/bin/env python3
"""The privacy data map (privacy/data-map.yaml) stays complete, honest and published.

Every column, analytics prop and permission is declared in the map with what it is,
why it's collected, how long it's kept and who else gets it. The store answers, the
iOS privacy manifest and the privacy-policy draft are generated from it, so the answers
a reviewer reads are the answers the code gives. This script fails when:

  - a column a migration creates (scripts/schema_sql.py), an event or prop in
    mobile/lib/analytics.ts, or a permission mobile/app.json asks for is missing from
    the map (or the map lists one that no longer exists)
  - a sensitive category (contact, location, health, financial, biometric, ugc, minor)
    has no retention, or is sent to analytics
  - `retention: account` is claimed for a table that isn't deleted with the account
  - a permission's purpose is generic ("required for app functionality"), in the map
    or in the text the phone shows (app.json usage strings, plugin options)
  - a generated file is stale: privacy/APP_STORE.md, privacy/PLAY_DATA_SAFETY.md,
    privacy/PRIVACY_POLICY.md, or expo.ios.privacyManifests in mobile/app.json

    python3 scripts/check_data_map.py            check (CI, pre-commit)
    python3 scripts/check_data_map.py --write    regenerate the four outputs from the map

Exit 0 clean, 1 with one line per problem. Needs PyYAML (in requirements-dev.txt).
The vocabulary is documented at the top of privacy/data-map.yaml. The store field names
follow Apple's NSPrivacyCollectedDataType list and Google Play's Data safety form.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema_sql  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAP = "privacy/data-map.yaml"
APP_JSON = "mobile/app.json"
ANALYTICS = "mobile/lib/analytics.ts"
WRITE_CMD = "python3 scripts/check_data_map.py --write"

CATEGORIES = {
    "none", "identifier", "contact", "location", "health", "financial", "biometric",
    "ugc", "minor", "usage", "device", "diagnostics",
}  # fmt: skip
SENSITIVE = {"contact", "location", "health", "financial", "biometric", "ugc", "minor"}
TYPES = {
    "contact": {"name", "email", "phone", "address"},
    "location": {"precise", "coarse"},
    "health": {"health", "fitness"},
    "financial": {"payment", "credit", "purchases", "other"},
    "ugc": {"photos", "videos", "audio", "messages", "support", "other"},
    "diagnostics": {"crash", "performance", "other"},
}
PACKS = {"baseline", "location", "minors", "health", "ugc", "financial", "biometric"}
OWNERS = {"user", "org", "system"}
# uses -> (Apple purpose, Play purpose)
USES = {
    "app_functionality": ("AppFunctionality", "App functionality"),
    "analytics": ("Analytics", "Analytics"),
    "personalization": ("ProductPersonalization", "Personalization"),
    "account_management": ("AppFunctionality", "Account management"),
    "fraud_prevention": ("AppFunctionality", "Fraud prevention, security, and compliance"),
    "developer_communications": ("DeveloperAdvertising", "Developer communications"),
    "developer_advertising": ("DeveloperAdvertising", "Advertising or marketing"),
    "third_party_advertising": ("ThirdPartyAdvertising", "Advertising or marketing"),
}
APPLE_PURPOSE_NAMES = {
    "AppFunctionality": "App Functionality",
    "Analytics": "Analytics",
    "ProductPersonalization": "Product Personalization",
    "DeveloperAdvertising": "Developer's Advertising or Marketing",
    "ThirdPartyAdvertising": "Third-Party Advertising",
}
# (category, type) -> (Apple NSPrivacyCollectedDataType suffix, Apple label, Apple group,
# Play category, Play data type). `None` type is the category's default.
STORE: dict[tuple[str, str | None], tuple[str, str, str, str, str]] = {
    ("identifier", None): ("UserID", "User ID", "Identifiers", "Personal info", "User IDs"),
    ("contact", "name"): ("Name", "Name", "Contact Info", "Personal info", "Name"),
    ("contact", "email"): ("EmailAddress", "Email Address", "Contact Info", "Personal info", "Email address"),
    ("contact", "phone"): ("PhoneNumber", "Phone Number", "Contact Info", "Personal info", "Phone number"),
    ("contact", "address"): ("PhysicalAddress", "Physical Address", "Contact Info", "Personal info", "Address"),
    ("contact", None): ("OtherUserContactInfo", "Other User Contact Info", "Contact Info", "Personal info", "Other info"),
    ("location", "coarse"): ("CoarseLocation", "Coarse Location", "Location", "Location", "Approximate location"),
    ("location", None): ("PreciseLocation", "Precise Location", "Location", "Location", "Precise location"),
    ("health", "fitness"): ("Fitness", "Fitness", "Health & Fitness", "Health and fitness", "Fitness info"),
    ("health", None): ("Health", "Health", "Health & Fitness", "Health and fitness", "Health info"),
    ("financial", "payment"): ("PaymentInfo", "Payment Info", "Financial Info", "Financial info", "User payment info"),
    ("financial", "credit"): ("CreditInfo", "Credit Info", "Financial Info", "Financial info", "Credit score"),
    ("financial", "purchases"): ("PurchaseHistory", "Purchase History", "Purchases", "Financial info", "Purchase history"),
    ("financial", None): ("OtherFinancialInfo", "Other Financial Info", "Financial Info", "Financial info", "Other financial info"),
    ("biometric", None): ("SensitiveInfo", "Sensitive Info", "Sensitive Info", "Personal info", "Other info"),
    ("ugc", "photos"): ("PhotosorVideos", "Photos or Videos", "User Content", "Photos or videos", "Photos"),
    ("ugc", "videos"): ("PhotosorVideos", "Photos or Videos", "User Content", "Photos or videos", "Videos"),
    ("ugc", "audio"): ("AudioData", "Audio Data", "User Content", "Audio files", "Voice or sound recordings"),
    ("ugc", "messages"): ("EmailsOrTextMessages", "Emails or Text Messages", "User Content", "Messages", "Other messages"),
    ("ugc", "support"): ("CustomerSupport", "Customer Support", "User Content", "App activity", "Other user-generated content"),
    ("ugc", None): ("OtherUserContent", "Other User Content", "User Content", "App activity", "Other user-generated content"),
    ("minor", None): ("OtherDataTypes", "Other Data Types", "Other Data", "Personal info", "Other info"),
    ("usage", None): ("ProductInteraction", "Product Interaction", "Usage Data", "App activity", "App interactions"),
    ("device", None): ("DeviceID", "Device ID", "Identifiers", "Device or other IDs", "Device or other IDs"),
    ("diagnostics", "crash"): ("CrashData", "Crash Data", "Diagnostics", "App info and performance", "Crash logs"),
    ("diagnostics", "performance"): ("PerformanceData", "Performance Data", "Diagnostics", "App info and performance", "Diagnostics"),
    ("diagnostics", None): ("OtherDiagnosticData", "Other Diagnostic Data", "Diagnostics", "App info and performance", "Other app performance data"),
}  # fmt: skip
# What the policy calls each kind of data.
PLAIN = {
    ("contact", "email"): "Your email address",
    ("contact", "name"): "Your name",
    ("contact", "phone"): "Your phone number",
    ("contact", "address"): "Your address",
    ("contact", None): "Your contact details",
    ("identifier", None): "Account identifiers",
    ("location", "coarse"): "Your approximate location",
    ("location", None): "Your location",
    ("health", "fitness"): "Fitness and exercise data",
    ("health", None): "Health information",
    ("financial", None): "Financial information",
    ("biometric", None): "Biometric data",
    ("ugc", "photos"): "Photos you add",
    ("ugc", "videos"): "Videos you add",
    ("ugc", "audio"): "Recordings you add",
    ("ugc", "messages"): "Messages you send",
    ("ugc", None): "Content you create",
    ("minor", None): "Information about a child",
    ("usage", None): "How you use the app",
    ("device", None): "Device information",
    ("diagnostics", None): "Crash and performance data",
}
# Apple's required-reason API categories and the reason codes each accepts
# (developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api).
REQUIRED_REASONS = {
    "FileTimestamp": {"DDA9.1", "C617.1", "3B52.1", "0A2A.1"},
    "SystemBootTime": {"35F9.1", "8FFB.1", "3D61.1"},
    "DiskSpace": {"85F4.1", "E174.1", "7D9E.1", "B728.1"},
    "ActiveKeyboards": {"3EC4.1", "54BD.1"},
    "UserDefaults": {"CA92.1", "1C8F.1", "C56D.1", "AC6B.1"},
}
DURATION = re.compile(r"^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?$")

# ---- permissions: where mobile/app.json asks for one ---------------------------------
IOS_KEYS = {
    "NSLocationWhenInUseUsageDescription": "location_when_in_use",
    "NSLocationAlwaysAndWhenInUseUsageDescription": "location_always",
    "NSLocationAlwaysUsageDescription": "location_always",
    "NSCameraUsageDescription": "camera",
    "NSMicrophoneUsageDescription": "microphone",
    "NSPhotoLibraryUsageDescription": "photos",
    "NSPhotoLibraryAddUsageDescription": "photos_save",
    "NSContactsUsageDescription": "contacts",
    "NSCalendarsUsageDescription": "calendar",
    "NSCalendarsFullAccessUsageDescription": "calendar",
    "NSRemindersUsageDescription": "reminders",
    "NSRemindersFullAccessUsageDescription": "reminders",
    "NSFaceIDUsageDescription": "face_id",
    "NSMotionUsageDescription": "motion",
    "NSHealthShareUsageDescription": "health",
    "NSHealthUpdateUsageDescription": "health",
    "NSBluetoothAlwaysUsageDescription": "bluetooth",
    "NSUserTrackingUsageDescription": "tracking",
    "NSSpeechRecognitionUsageDescription": "speech",
    "NSLocalNetworkUsageDescription": "local_network",
}
ANDROID = {
    "ACCESS_FINE_LOCATION": "location_when_in_use",
    "ACCESS_COARSE_LOCATION": "location_when_in_use",
    "ACCESS_BACKGROUND_LOCATION": "location_always",
    "CAMERA": "camera",
    "RECORD_AUDIO": "microphone",
    "READ_MEDIA_IMAGES": "photos",
    "READ_MEDIA_VIDEO": "photos",
    "READ_EXTERNAL_STORAGE": "photos",
    "WRITE_EXTERNAL_STORAGE": "photos_save",
    "READ_CONTACTS": "contacts",
    "WRITE_CONTACTS": "contacts",
    "READ_CALENDAR": "calendar",
    "WRITE_CALENDAR": "calendar",
    "USE_BIOMETRIC": "face_id",
    "USE_FINGERPRINT": "face_id",
    "ACTIVITY_RECOGNITION": "motion",
    "BODY_SENSORS": "health",
    "BLUETOOTH_CONNECT": "bluetooth",
    "BLUETOOTH_SCAN": "bluetooth",
    "POST_NOTIFICATIONS": "notifications",
}
# Install-time Android permissions that read no personal data: nothing to declare.
ANDROID_NORMAL = {
    "INTERNET", "ACCESS_NETWORK_STATE", "ACCESS_WIFI_STATE", "VIBRATE", "WAKE_LOCK",
    "RECEIVE_BOOT_COMPLETED", "FOREGROUND_SERVICE", "MODIFY_AUDIO_SETTINGS",
    "SCHEDULE_EXACT_ALARM", "USE_EXACT_ALARM",
}  # fmt: skip
# Expo config plugins: permission -> the option that carries its text. A plugin in
# app.json asks for these; `false` turns one off; leaving the option out ships the
# plugin's default ("Allow $(PRODUCT_NAME) to access your camera"), which is generic.
# None: the permission has no text to set (iOS shows its own notification prompt).
PLUGINS: dict[str, dict[str, str | None]] = {
    "expo-notifications": {"notifications": None},
    "expo-location": {"location_when_in_use": "locationWhenInUsePermission"},
    "expo-camera": {"camera": "cameraPermission", "microphone": "microphonePermission"},
    "expo-image-picker": {
        "photos": "photosPermission",
        "camera": "cameraPermission",
        "microphone": "microphonePermission",
    },
    "expo-media-library": {"photos": "photosPermission", "photos_save": "savePhotosPermission"},
    "expo-contacts": {"contacts": "contactsPermission"},
    "expo-calendar": {"calendar": "calendarPermission", "reminders": "remindersPermission"},
    "expo-local-authentication": {"face_id": "faceIDPermission"},
    "expo-tracking-transparency": {"tracking": "userTrackingPermission"},
    "expo-sensors": {"motion": "motionPermission"},
}
PLUGIN_EXTRA_KEYS = {  # options that ADD a permission only when given
    "locationAlwaysAndWhenInUsePermission": "location_always",
    "locationAlwaysPermission": "location_always",
}
# A purpose a reviewer can't check against the app: Apple 5.1.1 rejects these.
GENERIC = [
    re.compile(p, re.I)
    for p in (
        r"\$\(PRODUCT_NAME\)",
        r"^(for |to provide |to enable )?(the )?(app('s)? )?(functionality|features?|services?)$",
        r"^(required|needed|necessary)\b.{0,40}$",
        r"^(to )?improve (the |your |our )?(app|experience|user experience|services?|product)\b.{0,30}$",
        r"^(this|the) app (needs?|requires?|uses?|wants?)\b.{0,40}$",
        r"^allow .{0,40} to (access|use) your \w+( \w+)?$",
        r"^(to )?(access|use) (your )?\w+( \w+)?$",
    )
]


def is_generic(text: str) -> bool:
    s = re.sub(r"[.!]+$", "", " ".join(str(text).split())).strip()
    return len(s.split()) < 4 or any(g.search(s) for g in GENERIC)


# ---- reading the sources ---------------------------------------------------------------


def _split_top(text: str, sep: str = ",") -> list[str]:
    """Split on `sep` outside brackets and string literals."""
    out, depth, buf, quote = [], 0, "", ""
    for ch in text:
        if quote:
            buf += ch
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    return [p for p in [*out, buf.strip()] if p]


def _inside(text: str, open_at: int) -> str:
    pairs = {"(": ")", "{": "}"}
    opener, closer, depth = text[open_at], pairs[text[open_at]], 0
    for i in range(open_at, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return text[open_at + 1 : i]
    return text[open_at + 1 :]


def _object_props(arg: str) -> set[str]:
    """Props of an inline object literal: `{ a, b: x, ...rest }` ("*" marks a spread)."""
    return {
        "*" if item.startswith("...") else re.split(r"[\s:]", item)[0]
        for item in _split_top(_inside(arg, 0))
    }


def _typed_props(name: str, entry: str, arg: str) -> tuple[set[str] | None, str | None]:
    """Props of a parameter passed whole, read from its inline type annotation."""
    params = entry[entry.index("(") + 1 :]
    t = re.search(rf"\b{arg}\??\s*:\s*\{{", params)
    if not t:
        return None, (
            f"{ANALYTICS}: can't read the props of analytics.{name}: type `{arg}` inline "
            "(`p: {{ a: string; b: number }}`) so the data map can see them"
        )
    body = _inside(params, t.end() - 1)
    return {re.split(r"[\s?:]", item)[0] for item in _split_top(body.replace(";", ","), ",")}, None


def _capture_props(name: str, entry: str, arg: str) -> tuple[set[str] | None, str | None]:
    """(props, problem) for one capture() payload. props is None when the event must be
    skipped entirely (its props can't be read at all)."""
    if arg.startswith("{"):
        return _object_props(arg), None
    if re.fullmatch(r"\w+", arg):
        return _typed_props(name, entry, arg)
    if arg:
        return set(), f"{ANALYTICS}: can't read the props of analytics.{name} ({arg[:40]})"
    return set(), None


def analytics_events(src: str) -> tuple[dict[str, set[str]], list[str]]:
    """event -> props, read from `export const analytics = {...}`. "*" marks a spread."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"(^|[^:])//[^\n]*", r"\1", src)
    m = re.search(r"export const analytics = \{", src)
    if not m:
        return {}, [f"{ANALYTICS}: no `export const analytics = {{` block to read"]
    events: dict[str, set[str]] = {}
    problems: list[str] = []
    for entry in _split_top(_inside(src, m.end() - 1)):
        name = entry.split(":", 1)[0].strip()
        call = re.search(r"\bcapture\(", entry)
        if not call:
            continue
        args = _split_top(_inside(entry, call.end() - 1))
        ev = re.fullmatch(r"[\"'](\w+)[\"']", args[0]) if args else None
        if not ev:
            problems.append(f"{ANALYTICS}: analytics.{name} captures a non-literal event name")
            continue
        props, problem = _capture_props(name, entry, args[1] if len(args) > 1 else "")
        if problem:
            problems.append(problem)
        if props is not None:
            events.setdefault(ev.group(1), set()).update(props)
    return events, problems


@dataclass
class Permission:
    id: str
    where: str
    text: str | None = None  # what the phone shows, when app.json sets it
    default_text: bool = False  # a plugin's built-in default (generic by definition)


def _ios_permissions(ex: dict[str, Any]) -> list[Permission]:
    return [
        Permission(IOS_KEYS.get(key) or str(key), f"{APP_JSON}: ios.infoPlist.{key}", str(val))
        for key, val in ((ex.get("ios") or {}).get("infoPlist") or {}).items()
        if key.endswith("UsageDescription")
    ]


def _android_permissions(ex: dict[str, Any]) -> list[Permission]:
    shorts = [
        str(perm).rsplit(".", 1)[-1] for perm in (ex.get("android") or {}).get("permissions") or []
    ]
    return [
        Permission(ANDROID.get(short, short.lower()), f"{APP_JSON}: android.permissions {short}")
        for short in shorts
        if short not in ANDROID_NORMAL
    ]


def _plugin_permission(
    name: str, pid: str, opt: str | None, opts: dict[str, Any]
) -> Permission | None:
    """What one plugin option asks for: None when the option turns it off (`false`)."""
    where = f"{APP_JSON}: plugin {name}" + (f" {opt}" if opt else "")
    if opt is None:
        return Permission(pid, where)
    if opts.get(opt) is False:
        return None
    if isinstance(opts.get(opt), str):
        return Permission(pid, where, opts[opt])
    return Permission(pid, where, default_text=True)


def _plugin_permissions(plugin: Any) -> list[Permission]:
    name, opts = (plugin, {}) if isinstance(plugin, str) else (plugin[0], (plugin[1:] or [{}])[0])
    opts = opts if isinstance(opts, dict) else {}
    found = [_plugin_permission(name, pid, opt, opts) for pid, opt in PLUGINS.get(name, {}).items()]
    extra = [
        Permission(pid, f"{APP_JSON}: plugin {name} {opt}", opts[opt])
        for opt, pid in PLUGIN_EXTRA_KEYS.items()
        if isinstance(opts.get(opt), str)
    ]
    return [p for p in found if p is not None] + extra


def app_permissions(app: dict[str, Any]) -> list[Permission]:
    ex = app.get("expo") or {}
    found = _ios_permissions(ex) + _android_permissions(ex)
    for plugin in ex.get("plugins") or []:
        found += _plugin_permissions(plugin)
    return found


# ---- the map ---------------------------------------------------------------------------


@dataclass
class Item:
    """One kind of data collected from one source, as the store forms see it."""

    category: str
    type: str | None
    source: str
    purpose: str
    retention: str | None
    uses: list[str]
    linked: bool = True
    optional: bool = False
    shared_with: list[str] = field(default_factory=list)

    def store(self) -> tuple[str, str, str, str, str]:
        return STORE.get((self.category, self.type)) or STORE[(self.category, None)]

    def plain(self) -> str:
        return PLAIN.get((self.category, self.type)) or PLAIN[(self.category, None)]


def _column(spec: Any) -> dict[str, Any]:
    return {"category": spec} if isinstance(spec, str) else dict(spec or {})


def _header_problems(m: dict[str, Any]) -> list[str]:
    out: list[str] = []
    packs = m.get("packs", ["baseline"])
    if not isinstance(packs, list) or not set(packs) <= PACKS:
        out.append(f"{MAP}: packs must be a list of {sorted(PACKS)}, got {packs!r}")
    if not isinstance(m.get("tracking", False), bool):
        out.append(f"{MAP}: tracking must be true or false")
    return out


def _processor_problems(m: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for name, p in (m.get("processors") or {}).items():
        if not isinstance(p, dict) or not str(p.get("role", "")).strip():
            out.append(f"{MAP}: processor {name} needs a role (what it does for the app)")
            continue
        out += [
            f"{MAP}: processor {name}: unknown use {u!r}"
            for u in p.get("uses") or []
            if u not in USES
        ]
        cats = [_column(c).get("category") for c in p.get("collects") or []]
        out += [
            f"{MAP}: processor {name} collects unknown category {cat!r}"
            for cat in cats
            if cat not in CATEGORIES - {"none"}
        ]
    return out


def _third_party_problems(m: dict[str, Any]) -> list[str]:
    return [
        f"{MAP}: third party {name} needs a purpose (what it does with the data)"
        for name, p in (m.get("third_parties") or {}).items()
        if not isinstance(p, dict) or not str(p.get("purpose", "")).strip()
    ]


def _type_problems(where: str, cat: str, c: dict[str, Any]) -> list[str]:
    if c.get("type") is None or c["type"] in TYPES.get(cat, set()):
        return []
    return [
        f"{MAP}: {where}: type {c['type']!r} isn't one of {sorted(TYPES.get(cat, []))} for {cat}"
    ]


def _purpose_problems(where: str, cat: str, c: dict[str, Any]) -> list[str]:
    if str(c.get("purpose", "")).strip():
        return []
    return [f"{MAP}: {where} is '{cat}' but has no purpose (why the app keeps it)"]


def _retention_problems(where: str, cat: str, c: dict[str, Any]) -> list[str]:
    ret = c.get("retention")
    if ret is None:
        if cat in SENSITIVE:
            return [
                f"{MAP}: {where} is '{cat}' (sensitive) but has no retention: say how long it's kept"
            ]
        return []
    if ret != "account" and not DURATION.match(str(ret)):
        return [
            f"{MAP}: {where}: retention {ret!r} must be `account` or an ISO-8601 duration (P30D)"
        ]
    return []


def _item_problems(where: str, c: dict[str, Any], third: Any) -> list[str]:
    """One column's declaration: known category and type, a purpose, a retention, known
    uses, and only third parties the map lists."""
    cat = c.get("category")
    if cat not in CATEGORIES:
        return [f"{MAP}: {where} has unknown category {cat!r} (one of {sorted(CATEGORIES)})"]
    if cat == "none":
        return []
    return [
        *_type_problems(where, cat, c),
        *_purpose_problems(where, cat, c),
        *_retention_problems(where, cat, c),
        *(f"{MAP}: {where}: unknown use {u!r} (one of {sorted(USES)})"
          for u in c.get("uses") or [] if u not in USES),
        *(f"{MAP}: {where} is shared with {s!r}, which isn't listed under third_parties"
          for s in c.get("shared_with") or [] if s not in third),
    ]  # fmt: skip


def _table_problems(m: dict[str, Any]) -> list[str]:
    third = m.get("third_parties") or {}
    out: list[str] = []
    for tname, t in (m.get("tables") or {}).items():
        if not isinstance(t, dict):
            out.append(f"{MAP}: table {tname} must be a mapping with owner + columns")
            continue
        if t.get("owner") not in OWNERS:
            out.append(f"{MAP}: table {tname}: owner must be one of {sorted(OWNERS)}")
        for col, spec in (t.get("columns") or {}).items():
            out += _item_problems(f"{tname}.{col}", _column(spec), third)
    return out


def _analytics_prop_problem(where: str, cat: Any) -> list[str]:
    if cat not in CATEGORIES:
        return [f"{MAP}: {where} has unknown category {cat!r}"]
    if cat in SENSITIVE:
        return [
            f"{MAP}: {where} is '{cat}': sensitive data never goes to analytics. "
            "Send a coarse, non-identifying value (a count, a bucket, a yes/no) instead"
        ]
    return []


def _analytics_map_problems(m: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for ev, e in (m.get("analytics") or {}).items():
        for prop, cat in ((e or {}).get("props") or {}).items():
            out += _analytics_prop_problem(f"analytics prop '{ev}.{prop}'", cat)
    return out


def _permission_map_problems(m: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for pid, purpose in (m.get("permissions") or {}).items():
        text = purpose.get("purpose") if isinstance(purpose, dict) else purpose
        if not text or is_generic(str(text)):
            out.append(
                f"{MAP}: permission '{pid}' has a generic purpose ({text!r}): say what the user "
                'gets for it, in their words ("show your runs on a map")'
            )
    return out


def _required_reason_problems(m: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for api, reasons in ((m.get("ios") or {}).get("required_reason_apis") or {}).items():
        if api not in REQUIRED_REASONS:
            out.append(f"{MAP}: ios.required_reason_apis: unknown API category {api!r}")
        elif not reasons or not set(reasons) <= REQUIRED_REASONS[api]:
            out.append(
                f"{MAP}: ios.required_reason_apis.{api}: reasons must be from {sorted(REQUIRED_REASONS[api])}"
            )
    return out


# The per-rule checks map_problems runs, in the order their problems are reported.
MAP_CHECKS = (
    _header_problems,
    _processor_problems,
    _third_party_problems,
    _table_problems,
    _analytics_map_problems,
    _permission_map_problems,
    _required_reason_problems,
)


def map_problems(m: dict[str, Any]) -> list[str]:
    """The map is well-formed: known vocabulary, sensitive data kept and fenced."""
    if not isinstance(m, dict):
        return [f"{MAP}: not a mapping"]
    return [problem for check in MAP_CHECKS for problem in check(m)]


def _sql_table_problems(name: str, t: schema_sql.Table, mt: Any) -> list[str]:
    """One table a migration creates against its entry in the map."""
    if not isinstance(mt, dict):
        return [f"data map: table {name} (supabase/migrations) is not in {MAP}"]
    cols = mt.get("columns") or {}
    out = [
        f"data map: column {name}.{col} (supabase/migrations) is not in {MAP}"
        for col in t.columns
        if col not in cols
    ]
    out += [
        f"data map: {name}.{col} is in {MAP} but no migration creates it"
        for col in cols
        if col not in t.columns
    ]
    if t.user_owned and mt.get("owner") == "system":
        out.append(
            f"data map: table {name} references auth.users (user data) but the map says owner: system"
        )
    if not t.deleted_with_account:
        out += [
            f"data map: {name}.{col} says retention: account, but {name} isn't deleted "
            "with the account (no `references auth.users ... on delete cascade`)"
            for col, spec in cols.items()
            if _column(spec).get("retention") == "account"
        ]
    return out


def _table_coverage(m: dict[str, Any], root: Path) -> list[str]:
    mtables = m.get("tables") or {}
    sql = schema_sql.parse(schema_sql.all_sql(root / "supabase" / "migrations"))
    out: list[str] = []
    for name, t in sql.items():
        out += _sql_table_problems(name, t, mtables.get(name))
    out += [
        f"data map: table {name} is in {MAP} but no migration creates it (or mark it external)"
        for name, mt in mtables.items()
        if name not in sql and not (isinstance(mt, dict) and mt.get("external"))
    ]
    return out


def _event_prop_problems(ev: str, props: set[str], mprops: dict[str, Any]) -> list[str]:
    out = [
        f"data map: analytics prop '{ev}.{p}' ({ANALYTICS}) is not in {MAP}"
        for p in sorted(props)
        if p not in mprops
    ]
    out += [
        f"data map: analytics prop '{ev}.{p}' is in {MAP} but {ANALYTICS} doesn't send it"
        for p in mprops
        if p not in props
    ]
    return out


def _analytics_coverage(m: dict[str, Any], root: Path) -> list[str]:
    src = root / ANALYTICS
    if not src.is_file():
        return []
    events, problems = analytics_events(src.read_text(encoding="utf-8"))
    out = list(problems)
    mevents = m.get("analytics") or {}
    for ev, props in sorted(events.items()):
        if ev not in mevents:
            out.append(f"data map: analytics event '{ev}' ({ANALYTICS}) is not in {MAP}")
            continue
        out += _event_prop_problems(ev, props, (mevents[ev] or {}).get("props") or {})
    out += [
        f"data map: analytics event '{ev}' is in {MAP} but {ANALYTICS} doesn't define it"
        for ev in mevents
        if ev not in events
    ]
    return out


def _app_config_problems(_m: dict[str, Any], root: Path) -> list[str]:
    return [
        f"data map: mobile/{cfg} exists, but permissions are read from {APP_JSON} only: "
        "keep permissions and their text in app.json"
        for cfg in ("app.config.ts", "app.config.js")
        if (root / "mobile" / cfg).exists()
    ]


def _app_permission_problems(p: Permission, mperms: dict[str, Any]) -> list[str]:
    """One permission app.json asks for: mapped, and with text a reviewer can check."""
    out: list[str] = []
    if p.id not in mperms:
        out.append(f"data map: permission '{p.id}' ({p.where}) is not in {MAP}")
    if p.default_text:
        out.append(
            f"data map: permission '{p.id}' ({p.where}) ships the plugin's generic default "
            "text: set it to what the user gets, in their words, or `false` if unused"
        )
    elif p.text is not None and is_generic(p.text):
        out.append(f"data map: permission '{p.id}' ({p.where}) has a generic purpose ({p.text!r})")
    return out


def _permission_coverage(m: dict[str, Any], root: Path) -> list[str]:
    app = root / APP_JSON
    if not app.is_file():
        return []
    mperms = m.get("permissions") or {}
    perms = app_permissions(json.loads(app.read_text(encoding="utf-8")))
    out: list[str] = []
    for p in perms:
        out += _app_permission_problems(p, mperms)
    seen = {p.id for p in perms}
    out += [
        f"data map: permission '{pid}' is in {MAP} but {APP_JSON} doesn't ask for it"
        for pid in mperms
        if pid not in seen
    ]
    return out


# The per-source checks coverage_problems runs, in the order their problems are reported.
COVERAGE_CHECKS = (_table_coverage, _analytics_coverage, _app_config_problems, _permission_coverage)


def coverage_problems(m: dict[str, Any], root: Path) -> list[str]:
    """The map lists exactly what the migrations, analytics.ts and app.json hold."""
    return [problem for check in COVERAGE_CHECKS for problem in check(m, root)]


def items(m: dict[str, Any]) -> list[Item]:
    """Everything collected, from tables, analytics and processor SDKs."""
    found: list[Item] = []
    for tname, t in (m.get("tables") or {}).items():
        for col, spec in ((t or {}).get("columns") or {}).items():
            c = _column(spec)
            if c.get("category", "none") == "none":
                continue
            found.append(
                Item(
                    c["category"],
                    c.get("type"),
                    f"{tname}.{col}",
                    str(c.get("purpose", "")),
                    c.get("retention"),
                    list(c.get("uses") or ["app_functionality"]),
                    bool(c.get("linked", True)),
                    bool(c.get("optional", False)),
                    list(c.get("shared_with") or []),
                )  # fmt: skip
            )
    for ev, e in (m.get("analytics") or {}).items():
        for prop, cat in ((e or {}).get("props") or {}).items():
            if cat != "none":
                found.append(
                    Item(cat, None, f"analytics {ev}.{prop}", "", None, ["analytics"], True, True)
                )
    for name, p in (m.get("processors") or {}).items():
        for c in (p or {}).get("collects") or []:
            c = _column(c)
            found.append(
                Item(
                    c["category"],
                    c.get("type"),
                    f"{name} SDK",
                    str(p.get("role", "")),
                    None,
                    list(p.get("uses") or ["app_functionality"]),
                    bool(c.get("linked", True)),
                    bool(p.get("optional", False)),
                )  # fmt: skip
            )
    return found


# ---- generated outputs -----------------------------------------------------------------

HEADER = (
    "<!-- Generated from privacy/data-map.yaml by scripts/check_data_map.py. Don't edit:\n"
    f"     change the map, then run `{WRITE_CMD}`. CI fails when this is stale. -->\n"
)


def _merge(found: list[Item], key: Any) -> dict[Any, list[Item]]:
    groups: dict[Any, list[Item]] = {}
    for it in found:
        groups.setdefault(key(it), []).append(it)
    return groups


def privacy_manifest(m: dict[str, Any]) -> dict[str, Any]:
    """expo.ios.privacyManifests: Expo writes PrivacyInfo.xcprivacy from it at prebuild."""
    collected = []
    for key, group in sorted(_merge(items(m), lambda i: i.store()[0]).items()):
        purposes = sorted({USES[u][0] for it in group for u in it.uses})
        collected.append(
            {
                "NSPrivacyCollectedDataType": f"NSPrivacyCollectedDataType{key}",
                "NSPrivacyCollectedDataTypeLinked": any(it.linked for it in group),
                "NSPrivacyCollectedDataTypeTracking": bool(m.get("tracking", False)),
                "NSPrivacyCollectedDataTypePurposes": [
                    f"NSPrivacyCollectedDataTypePurpose{p}" for p in purposes
                ],
            }
        )
    apis = [
        {
            "NSPrivacyAccessedAPIType": f"NSPrivacyAccessedAPICategory{api}",
            "NSPrivacyAccessedAPITypeReasons": sorted(reasons),
        }
        for api, reasons in sorted(((m.get("ios") or {}).get("required_reason_apis") or {}).items())
    ]
    return {
        "NSPrivacyTracking": bool(m.get("tracking", False)),
        "NSPrivacyTrackingDomains": list(m.get("tracking_domains") or []),
        "NSPrivacyCollectedDataTypes": collected,
        "NSPrivacyAccessedAPITypes": apis,
    }


def _yes(b: bool) -> str:
    return "Yes" if b else "No"


def _sources(group: list[Item]) -> str:
    """Tables and SDKs by name; analytics props folded into one list of events."""
    named = sorted({f"`{it.source}`" for it in group if not it.source.startswith("analytics ")})
    events = sorted(
        {it.source.split()[1].split(".")[0] for it in group if it.source.startswith("analytics ")}
    )
    if events:
        named.append("analytics events: " + ", ".join(f"`{e}`" for e in events))
    return ", ".join(named)


def app_store_md(m: dict[str, Any]) -> str:
    tracking = bool(m.get("tracking", False))
    rows = []
    for (_, label, cat), group in sorted(
        _merge(items(m), lambda i: (i.store()[2], i.store()[1], i.store()[2])).items()
    ):
        purposes = sorted({APPLE_PURPOSE_NAMES[USES[u][0]] for it in group for u in it.uses})
        rows.append(
            f"| {label} | {cat} | {_yes(any(it.linked for it in group))} | {_yes(tracking)} "
            f"| {', '.join(purposes)} | {_sources(group)} |"
        )
    apis = (m.get("ios") or {}).get("required_reason_apis") or {}
    return (
        HEADER + "\n# App Store privacy answers\n\n"
        "The answers for App Store Connect → your app → **App Privacy**, drafted from the data\n"
        "map. The owner reviews them against the running app and submits them; Apple holds the\n"
        "developer responsible for their accuracy.\n\n"
        "**Do you or your third-party partners collect data from this app?** Yes.\n\n"
        f"**Is data used to track people across apps and websites owned by other companies?** {_yes(tracking)}.\n\n"
        "| Data type | Apple's group | Linked to the user | Used for tracking | Purposes | Where it comes from |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        "## Privacy manifest (PrivacyInfo.xcprivacy)\n\n"
        "The same data types, plus the required-reason APIs below, are written to\n"
        "`mobile/app.json` → `expo.ios.privacyManifests`; Expo turns that into the app's\n"
        "`PrivacyInfo.xcprivacy` at build time.\n\n"
        "| Required-reason API | Reasons |\n|---|---|\n"
        + "\n".join(f"| {api} | {', '.join(sorted(r))} |" for api, r in sorted(apis.items()))
        + "\n"
    )


def play_md(m: dict[str, Any]) -> str:
    rows = []
    for (cat, dtype), group in sorted(_merge(items(m), lambda i: i.store()[3:5]).items()):
        purposes = sorted({USES[u][1] for it in group for u in it.uses})
        shared = sorted({s for it in group for s in it.shared_with})
        required = "Optional" if all(it.optional for it in group) else "Required"
        rows.append(
            f"| {cat} | {dtype} | Yes | {', '.join(shared) if shared else 'No'} | No | {required} "
            f"| {', '.join(purposes)} | {_sources(group)} |"
        )
    return (
        HEADER + "\n# Google Play Data safety answers\n\n"
        "The answers for Play Console → **App content → Data safety**, drafted from the data\n"
        "map. The owner reviews them against the running app and submits them.\n\n"
        "**Does your app collect or share any of the required user data types?** Yes.\n\n"
        "**Is all of the user data collected by your app encrypted in transit?** Yes: the app\n"
        "talks only to HTTPS endpoints (the API, Supabase, and any analytics and crash services).\n\n"
        "**Do you provide a way for users to request that their data is deleted?** Yes: Settings →\n"
        "Delete account deletes the account and its data. Play also asks for a web link where\n"
        "people can request deletion without the app: [add it at pre-launch].\n\n"
        "Service providers that process data for you (listed under `processors` in the map)\n"
        "don't count as sharing; only `third_parties` do.\n\n"
        "| Category | Data type | Collected | Shared | Processed ephemerally | Required or optional | Purposes | Where it comes from |\n"
        "|---|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n"
    )


def _duration_words(iso: str) -> str:
    m = DURATION.match(iso)
    if not m:
        return iso
    units = [
        ("year", 1),
        ("month", 2),
        ("week", 3),
        ("day", 4),
        ("hour", 6),
        ("minute", 7),
        ("second", 8),
    ]
    parts = []
    for unit, g in units:
        if m.group(g):
            n = int(m.group(g)[:-1])
            parts.append(f"{n} {unit}{'' if n == 1 else 's'}")
    return ", ".join(parts)


def _kept(ret: str | None) -> str:
    if ret == "account":
        return "Until you delete your account"
    return f"Up to {_duration_words(ret)}" if ret else "As long as the app needs it"


def policy_md(m: dict[str, Any], app_name: str) -> str:
    # The columns we store (analytics and SDK collection get their own sections): one row
    # per kind of data and how long it's kept, with every purpose it serves.
    grouped: dict[tuple[str, str], list[str]] = {}
    for it in items(m):
        if it.source.startswith("analytics ") or it.source.endswith(" SDK"):
            continue
        why = grouped.setdefault((it.plain(), _kept(it.retention)), [])
        purpose = it.purpose[:1].upper() + it.purpose[1:]
        if purpose not in why:
            why.append(purpose)
    rows = [f"| {what} | {'; '.join(why)} | {kept} |" for (what, kept), why in grouped.items()]
    procs = m.get("processors") or {}
    third = m.get("third_parties") or {}
    perms = m.get("permissions") or {}
    analytics_opt = any(
        (p or {}).get("optional") and "analytics" in ((p or {}).get("uses") or [])
        for p in procs.values()
    )
    cats = {it.category for it in items(m)}
    lines = [
        HEADER,
        f"# Privacy policy for {app_name} (DRAFT)\n",
        "> **This is a draft to review, not legal advice.** It was generated from the app's\n"
        "> data map (`privacy/data-map.yaml`), so it lists what the code actually collects. Have\n"
        "> it reviewed (by a lawyer if you handle sensitive data or sell into regulated markets),\n"
        "> fill in the bracketed parts, and publish it at a public URL for the store listings and\n"
        "> Settings. The law that applies depends on where you and your users are.\n",
        "Last updated: [date you publish this]\n",
        f"{app_name} is made by [your name or company]. This policy explains what the app\n"
        "collects, why, how long it's kept, and the choices you have.\n",
        "## What we collect and why\n",
        "| What | Why | Kept |\n|---|---|---|\n" + "\n".join(rows) + "\n",
        "We don't sell your personal information, and we don't use it for advertising."
        + (
            " We don't track you across other companies' apps or websites.\n"
            if not m.get("tracking")
            else "\n"
        ),
    ]
    if analytics_opt:
        lines.append(
            "## Analytics\n\nWe count which screens and actions get used, tied to an account id\n"
            "rather than your name or email, so we can see what helps and what doesn't. Nothing\n"
            "sensitive goes into analytics. You can turn analytics off in Settings → Privacy.\n"
        )
    if "diagnostics" in cats:
        lines.append(
            "## Crash reports\n\nWhen the app crashes, a report with technical details (device\n"
            "model, app version, what went wrong) is sent so we can fix it. It doesn't include\n"
            "your name, email or what you've written.\n"
        )
    if perms:
        lines.append(
            "## Permissions\n\nThe app asks for these when you first use the feature that needs\n"
            "them, never on launch:\n\n"
            + "\n".join(
                f"- **{pid.replace('_', ' ')}**: to "
                f"{(p.get('purpose') if isinstance(p, dict) else p)}"
                for pid, p in sorted(perms.items())
            )
            + "\n"
        )
    lines.append(
        "## Who handles your data for us\n\nThese service providers process data on our behalf, only\n"
        "to run the app [check each one's data processing terms before you publish]:\n\n"
        + "\n".join(
            f"- **{name}**: {(p or {}).get('role', '')}" for name, p in sorted(procs.items())
        )
        + "\n"
    )
    if third:
        lines.append(
            "## Who we share data with\n\n"
            + "\n".join(
                f"- **{n}**: {(p or {}).get('purpose', '')}" for n, p in sorted(third.items())
            )
            + "\n"
        )
    lines.append(
        "## Your choices and rights\n\n"
        "- **See and download your data:** Settings → Download my data.\n"
        "- **Delete your account and data:** Settings → Delete account. It's permanent, and the\n"
        '  data listed above as kept "until you delete your account" goes with it.\n'
        "- **Correct your details:** edit them in the app, or contact us.\n"
        "- Depending on where you live you may have further rights (to object, to restrict, to\n"
        "  complain to a data protection authority). Contact us to use them.\n"
    )
    lines.append(
        "## Children\n\n"
        + (
            "[This app handles information about children. Describe who gives consent (a parent\n"
            "or guardian), what a child can and can't do, and how a parent reviews or deletes the\n"
            "child's data. COPPA and similar laws apply: have this section reviewed.]\n"
            if "minor" in cats
            else "The app isn't directed at children under 13 [or the age that applies where you\n"
            "operate], and we don't knowingly collect their information.\n"
        )
    )
    lines.append(
        "## Security\n\nData travels over encrypted connections (HTTPS). Each person's data is\n"
        "isolated in the database, so one account can't read another's.\n"
    )
    lines.append(
        "## Changes and contact\n\nIf this policy changes we'll update the date above and, for\n"
        "significant changes, tell you in the app. Questions or requests: [support contact].\n"
    )
    return "\n".join(lines)


def outputs(m: dict[str, Any], app_name: str) -> dict[str, str]:
    return {
        "privacy/APP_STORE.md": app_store_md(m),
        "privacy/PLAY_DATA_SAFETY.md": play_md(m),
        "privacy/PRIVACY_POLICY.md": policy_md(m, app_name),
    }


def _app(root: Path) -> dict[str, Any]:
    p = root / APP_JSON
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def freshness_problems(m: dict[str, Any], root: Path) -> list[str]:
    out = []
    app = _app(root)
    for rel, text in outputs(m, str((app.get("expo") or {}).get("name", "the app"))).items():
        path = root / rel
        if not path.is_file():
            out.append(f"{rel} is missing: run {WRITE_CMD}")
        elif path.read_text(encoding="utf-8") != text:
            out.append(f"{rel} is stale (it no longer matches {MAP}): run {WRITE_CMD}")
    if app:
        have = ((app.get("expo") or {}).get("ios") or {}).get("privacyManifests")
        if have != privacy_manifest(m):
            out.append(
                f"{APP_JSON} expo.ios.privacyManifests is stale (it no longer matches {MAP}): run {WRITE_CMD}"
            )
    return out


def load(root: Path) -> dict[str, Any]:
    return yaml.safe_load((root / MAP).read_text(encoding="utf-8")) or {}


def check(root: Path) -> list[str]:
    if not (root / MAP).is_file():
        return [
            f"{MAP} is missing: every column, analytics prop and permission must be declared there"
        ]
    try:
        m = load(root)
    except yaml.YAMLError as exc:
        return [f"{MAP}: not valid YAML: {exc}"]
    problems = map_problems(m)
    if problems:
        return problems  # coverage and freshness read the map; fix its shape first
    return coverage_problems(m, root) + freshness_problems(m, root)


def write(root: Path) -> list[str]:
    m = load(root)
    if problems := map_problems(m):
        return problems
    app = _app(root)
    written = []
    for rel, text in outputs(m, str((app.get("expo") or {}).get("name", "the app"))).items():
        path = root / rel
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            written.append(rel)
    if app:
        ios = app.setdefault("expo", {}).setdefault("ios", {})
        if ios.get("privacyManifests") != privacy_manifest(m):
            ios["privacyManifests"] = privacy_manifest(m)
            (root / APP_JSON).write_text(
                json.dumps(app, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            written.append(f"{APP_JSON} (expo.ios.privacyManifests)")
    for rel in written:
        print(f"wrote {rel}")
    return []


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = ROOT
    if "--root" in args:
        root = Path(args[args.index("--root") + 1]).resolve()
    problems = write(root) if "--write" in args else check(root)
    for p in problems:
        print(p)
    if problems:
        print(f"data map check FAILED ({len(problems)} problem(s)). The map: {MAP}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
