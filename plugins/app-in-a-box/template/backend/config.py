"""Environment contract for the __APP_NAME__ API.

Every env var that gates a real capability is registered in FEATURE_CONFIG, so a
missing value shows up in /health's `features_unavailable` instead of failing
silently or as a bare 5xx. That list is the truth about what's wired in a given
environment.

A call site that guards on config checks ITS OWN feature key via
`feature_missing("...")`, never "is anything missing?". A blanket check couples
every feature's config together.
"""

from __future__ import annotations

import os

# feature name -> required env vars. A tuple inside the tuple means "any of".
FEATURE_CONFIG: dict[str, tuple[str | tuple[str, ...], ...]] = {
    "database + auth (Supabase)": (
        "SUPABASE_URL",
        ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"),
    ),
    "error monitoring (Sentry)": ("SENTRY_DSN",),
    # Push needs the token store. EXPO_ACCESS_TOKEN is sent when set, but Expo only
    # requires it once you enable "enhanced push security"; then add it here.
    "push (Expo)": (
        "SUPABASE_URL",
        ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY"),
    ),
    # Register a feature here only when code actually uses it, e.g. when the scaffold
    # adds an AI module: "ai (Anthropic)": ("ANTHROPIC_API_KEY",). A listed-but-unused
    # feature leaves /health "degraded" forever, and a signal that never clears gets
    # ignored.
}

# Capabilities the template ships DORMANT: the code is live and guarded by its own
# key, but an app that hasn't switched them on is not "degraded". They fail closed
# with a named 503 at the call site and `/health?deep=1` lists them. Move an entry up
# into FEATURE_CONFIG once production depends on it (e.g. you scheduled the cron).
OPTIONAL_FEATURE_CONFIG: dict[str, tuple[str | tuple[str, ...], ...]] = {
    "scheduled jobs (cron)": ("CRON_SECRET",),
}


# Capabilities every HOSTED environment needs but local dev doesn't, so they only count
# when APP_ENV=production. Email sign-in is the one: Supabase, not this API, sends the
# OTP email, and its built-in mailer allows a couple of emails an hour, so real users
# can't sign in until the project has custom SMTP. The backend never holds the SMTP
# password. Provision sets AUTH_SMTP_HOST (the host, not a secret) on the API service
# only after Supabase accepted the SMTP config, so it's the API's record that email
# works. Local `supabase start` catches mail in its own inbox and needs none of this.
PRODUCTION_FEATURE_CONFIG: dict[str, tuple[str | tuple[str, ...], ...]] = {
    "email sign-in (custom SMTP)": ("AUTH_SMTP_HOST",),
}


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def app_env() -> str:
    return env("APP_ENV", "development").lower()


def is_production() -> bool:
    return app_env() == "production"


def _present(req: str | tuple[str, ...]) -> bool:
    if isinstance(req, tuple):
        return any(env(name) for name in req)
    return bool(env(req))


def _label(req: str | tuple[str, ...]) -> str:
    return " or ".join(req) if isinstance(req, tuple) else req


def feature_missing(feature: str) -> list[str]:
    """Missing env var names for one feature. Names only, never values."""
    for registry in (FEATURE_CONFIG, PRODUCTION_FEATURE_CONFIG, OPTIONAL_FEATURE_CONFIG):
        if feature in registry:
            return [_label(req) for req in registry[feature] if not _present(req)]
    raise KeyError(feature)


def check_feature_config(*, optional: bool = False) -> dict[str, list[str]]:
    """{feature: [missing var names]} for every feature that isn't fully wired.

    FEATURE_CONFIG always, plus PRODUCTION_FEATURE_CONFIG when APP_ENV=production.
    `optional=True` reports OPTIONAL_FEATURE_CONFIG instead.
    """
    if optional:
        features = list(OPTIONAL_FEATURE_CONFIG)
    else:
        features = list(FEATURE_CONFIG)
        if is_production():
            features += PRODUCTION_FEATURE_CONFIG
    out: dict[str, list[str]] = {}
    for feature in features:
        missing = feature_missing(feature)
        if missing:
            out[feature] = missing
    return out


def supabase_url() -> str:
    return env("SUPABASE_URL").rstrip("/")


def supabase_service_key() -> str:
    return env("SUPABASE_SERVICE_ROLE_KEY") or env("SUPABASE_SECRET_KEY")


def supabase_auth_apikey() -> str:
    """The `apikey` header for Supabase Auth's REST endpoints (`/auth/v1/user`).

    Any project API key passes the gateway; the user's Bearer token does the identifying.
    Least privilege first: SUPABASE_ANON_KEY when set, else the same secret key the DB
    client uses, so every key configuration FEATURE_CONFIG accepts works here too.
    SUPABASE_ANON_KEY is OPTIONAL and deliberately not in FEATURE_CONFIG: nothing else in
    the backend needs it. Empty only when the Supabase feature is unconfigured, which
    backend/auth.py turns into a 503, never a 401 (a 401 signs the user out).
    """
    return env("SUPABASE_ANON_KEY") or supabase_service_key()


def app_version() -> str | None:
    """The deployed git sha (Railway sets RAILWAY_GIT_COMMIT_SHA), or None locally."""
    for name in ("APP_VERSION", "RAILWAY_GIT_COMMIT_SHA", "GIT_SHA", "SENTRY_RELEASE"):
        if env(name):
            return env(name)[:40]
    return None


def cors_origins() -> list[str]:
    """Browser origins allowed to call the API. Native apps send no Origin header,
    so they never need CORS: the mobile-safe default in production is NO origins.

    Elsewhere it allows local Expo web. Set CORS_ORIGINS to a comma-separated list
    ("https://app.example.com,https://admin.example.com") when you add a web client.
    """
    raw = env("CORS_ORIGINS")
    if raw:
        return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if is_production():
        return []
    return ["http://localhost:8081", "http://localhost:19006"]
