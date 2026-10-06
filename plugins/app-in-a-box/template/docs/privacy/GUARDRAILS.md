# Guardrail packs

Privacy and safety rules this app enforces in code: lints that fail CI, defaults that
are already wired, and tests that prove both. Nothing here is advice you have to
remember. It is what `python3 scripts/check_guardrails.py` (CI's `python` job) and the
app's own tests check on every PR.

**Which packs are on** comes from `privacy/data-map.yaml` → `packs`, set from the idea's
risk screen at scaffold (`docs/product/RISK.md` says why). No file, or no list, means
`baseline` alone. `baseline` is always on.

**A pack that is off costs nothing.** Its checks don't run, so it can't slow you down or
raise a false alarm, and its code is never bundled: the location helpers aren't imported
by anything until a feature imports them, and the age gate renders only when `minors` is
on. `tests/test_guardrails.py` proves it per pack: the same planted violation passes
with the pack off and fails once it is on.

**Turning one on:** add it to `packs:` in the data map, then run
`python3 scripts/check_guardrails.py --write` (it regenerates `mobile/lib/packs.ts`,
which tells the app; CI fails while the two disagree), then fix what the check reports.

**Keeping a finding on purpose:** write `guardrail-ok(<pack>): <why>` on the line (or the
line above). The reason is the point: review reads it, and it has to name the pack.

Not legal advice. These are engineering defaults that make the common regimes easier
to meet; `docs/product/RISK.md` lists which may apply, and a high-risk idea needs a
lawyer, not a lint.

## baseline (always on)

| What | Enforced by | Where |
|---|---|---|
| No email, name, phone, postal address, precise location, free text, credential or birth date in an analytics payload | `check_guardrails.py` (`analytics_pii`) | helper keys in `mobile/lib/analytics.ts`, and the arguments of every `analytics.*(...)` call |
| Events only through `lib/analytics.ts` | `analytics_bypass` | any `posthog.capture/identify/...` elsewhere fails |
| The same data never in a backend log call | `logs_pii` | every `logger.*` / `logging.*` call under `backend/` (names, attributes, `extra` keys, f-string parts) |
| What slips past review is still stripped | `scrubProps()` + `scrubSentryEvent()` (`mobile/lib/privacy.ts`), `scrub_event` (`backend/observability.py`); `scrubbers_wired` keeps them wired | every PostHog and Sentry event |
| Backend security mistakes (eval, `shell=True`, `verify=False`, unsafe YAML or pickle, unverified JWTs, SQL from strings, wildcard CORS with credentials, logged request bodies) | Semgrep OSS, pinned in `requirements-semgrep.lock`, rules in `.semgrep/backend.yml` | `.github/workflows/security.yml` → `semgrep`; the rules' own test cases (`.semgrep/backend.py`) run first |
| A migration that adds a personal-looking column gets the privacy checklist | `.agents/rules/privacy-columns.md` (the path-rule hook fires only when the edit adds such a column) | `supabase/migrations/**` |

Send ids, counts and categories to analytics, never the value. `duration_ms`,
`error_code`, `screen` and `route` are fine; `email`, `note`, `latitude` are not.

## location

- **Background location only with a reason.** If `app.json` asks for it
  (`UIBackgroundModes: location`, `ACCESS_BACKGROUND_LOCATION`, the expo-location plugin's
  background flags) or code calls `startLocationUpdatesAsync`/`startGeofencingAsync`, the
  data map needs `permissions.location_background: "<why the user benefits>"` and the OS
  prompt needs a purpose string (`locationAlwaysAndWhenInUsePermission`). Google Play
  approves background location only for core features through a permission declaration
  ([Play Console help](https://support.google.com/googleplay/android-developer/answer/9799150));
  App Review guideline 5.1.5 asks the purpose be explained in the app.
- **Coarse by default.** Every position read (`getCurrentPositionAsync`,
  `watchPositionAsync`, ...) goes through `coarsen()` in `mobile/lib/location.ts`
  (about a kilometre). A feature that truly needs the exact point says why on that line.
- **Location expires.** A table with a location column (or a data-map column of category
  `location`) needs a TTL in `backend/services/jobs_service.py` → `RETENTION`; the
  existing daily prune cron (`/internal/cron/prune-rate-limits`) deletes older rows.
- **People can see who sees them.** If the app reads location, some screen renders
  `<WhoCanSeeMe audience=... onManage=...>` (`components/ui/WhoCanSeeMe.tsx`).

## minors

- **Age first.** The sign-in screen shows `<AgeGate>` before an email is collected: a
  neutral birth month + year, which the FTC's COPPA guidance recommends over a "you must
  be 13" checkbox. Only the outcome is kept (`lib/age.ts`), never the date, and it is
  kept so a child can't go back and pick an older year. `MIN_AGE` is 13 (COPPA); raise
  it where the app ships (the GDPR lets countries set 13 to 16; the UK Children's Code
  covers under-18s).
- **Analytics off for children, and until the answer is in.** With the pack on, PostHog
  starts opted out and `capture()` drops everything until an of-age answer; an under-age
  answer switches it off for good (the Settings toggle can't turn it back on).
- **No ads, attribution or third-party analytics SDKs** in `mobile/package.json`. Apple's
  Kids Category (guideline 1.3) bars third-party analytics and ads in all but limited cases.
- **Nothing public by default.** A visibility column can't default to public.
- **No user-to-user messaging by default.** A messaging-looking table needs
  `guardrail-ok(minors): <why>` on its create line: an owner decision, recorded.

**Parental consent is a decision, not a component.** Under-age users see "ask a parent";
how the app then gets a parent's verifiable consent is the owner's call, usually with
counsel. The options, roughly cheapest first:

- **Don't serve under-13s at all** (the gate stays a stop). Simplest, and common.
- **Let the platform tell you.** Apple's Declared Age Range API
  ([docs](https://developer.apple.com/documentation/declaredagerange)) and Google's Play
  Age Signals API ([docs](https://developer.android.com/google/play/age-signals)) return
  an age range a parent set up, with no birth date; Play's terms limit that signal to
  age-appropriate experiences, never analytics or ads.
- **A consent method the FTC lists** for verifiable parental consent: a signed form, a
  payment-card transaction, a call or video call with trained staff, a check of a
  government ID, or "email plus" for internal-only uses
  ([FTC COPPA FAQ](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions)).
- **A consent vendor** that runs those methods for you (ask counsel which they accept).

## health

Health values (weight, heart rate, glucose, sleep, symptoms, medication, mood, cycle...)
never reach analytics or log calls: the payload and log lints widen to them, and the
runtime scrubbers strip them from PostHog and Sentry. App Review guideline 5.1.3 forbids
using health data for advertising or data mining and storing it in iCloud. No diagnostic
or treatment claims in copy (`.agents/rules/optional/health-data.md`).

## financial

Amounts, balances, card and account numbers, IBANs, salaries and merchants never reach
analytics or log calls, and a money column is never floating point (`real`, `double
precision`, `float`, `money`): integer minor units plus a currency code.

## biometric

No biometric value in analytics or logs, and no column stores a face, fingerprint or
voice template. Match on the device (Face ID / Touch ID / BiometricPrompt through the OS)
and keep only the yes/no.

## ugc

App Review guideline 1.2: an app with user-generated content needs a way to filter
objectionable material, to report content with timely responses, to block abusive users,
and published contact details. When any table holds content users show each other (a
`posts`, `comments`, `messages`, `reviews` or similar table, or a data-map column of
category `ugc`), the check requires:

- a reports table (`content_reports`) with a `status` or `resolved_at`, so someone can
  work the queue,
- a blocks table (`user_blocks`),
- a POST endpoint whose path says `report`, and one whose path says `block`.

"Timely" is a promise the owner keeps: a support address in the app and store listing,
a daily look at open reports, and hiding reported content from the reporter at once.
Filtering (a word list, or a moderation API) and the response time are owner decisions.
