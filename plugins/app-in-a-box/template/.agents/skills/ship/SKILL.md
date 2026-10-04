---
name: ship
description: Release checklist for getting a build to testers or the stores. Covers the version bump, EAS build and submit, OTA updates and when they're safe, changelog, store listing, privacy nutrition label / data safety form, and the account-deletion requirement. Guidance-level; it never handles signing secrets. Use when asked to ship, release, submit to TestFlight / App Store / Play, or push an OTA update.
disable-model-invocation: true
argument-hint: "[testflight|store|ota]"
---

# Ship

A release is the one step you can't take back: a store build lives on phones for
weeks. Go through the checklist in order, report each line as ✅ / ❌ / n/a with
evidence, and stop at the first ❌ that blocks. Store-account, signing and payment
steps are the owner's. Tell them exactly what to click; never ask for or handle
Apple/Google credentials, keystores or `.p8` keys (EAS stores those).

## 0. Which release?

| Kind | What changes | Command shape | Reversible? |
|---|---|---|---|
| **OTA update** | JS/assets only, same native build | `eas update --channel production --message "<summary>"` | Yes: republish the previous update |
| **TestFlight / internal** | New native build for testers | `eas build --profile preview` (Android APK) or `--profile production` + `eas submit -p ios` | Mostly |
| **Store release** | Public build | `eas build --profile production --platform all` then `eas submit --platform all` | **No** |

**OTA is only safe for JS changes.** `app.json` uses `runtimeVersion: {policy:
"appVersion"}`, so an update only reaches builds with the same `version`. Any new
native module, permission, config plugin or SDK bump needs a new build. When unsure,
build. Check with `npx expo install --check` and `git diff <last-release-tag> --
mobile/app.json mobile/package.json`.

## Decisions due before launch (first TestFlight or store release)

Some product calls were parked on day 0 because they're cheap to change and best made
once people use the app. They come due here. Read `design/brief.json` → `decisions` for
every `deferred` entry with `ask_at: pre-launch` (`next` lists them as
`decisions_due`). Ask them in one structured round before the checklist, recommended
option first, and write each answer back (`status: asked`). They always include:
- **Price and paywall placement** (only if `money.model` isn't `free`): what it costs,
  and where the paywall sits relative to the payoff (after it, never before the user has
  felt it). Payments themselves are `recipe-payments`.
- **Store listing**: name, subtitle, keywords and category, written for how the brief's
  `distribution` says the first 100 users will search.
- **Privacy labels**: the answers drafted in step 3 below, confirmed by the owner.
- **Support channel**: where users reach a human (an email, a form, a community), which
  becomes the store's support URL.

An unanswered one blocks a store release, not an OTA update.

## 1. Pre-flight (all releases)

- [ ] On a release branch or `main` at a tagged commit; `git status` clean.
- [ ] Gates green: `cd mobile && npm run gates` and `scripts/dev-venv.sh python -m pytest -q`.
- [ ] Backend deployed first, and `/health` shows `features_unavailable: []` for
      every feature this build uses. Old app builds must keep working against it
      (additive wire rule).
- [ ] Every `EXPO_PUBLIC_*` the app reads is set for the target EAS environment:
      `eas env:list --environment production`. Missing = a feature that silently
      does nothing in the store build.
- [ ] Sentry release + source maps configured, so crashes are readable.

## 2. Version + changelog (store/TestFlight)

- [ ] Bump `version` in `mobile/app.json` (semver: patch = fixes, minor = features).
      Build numbers are handled by EAS (`appVersionSource: remote`, `autoIncrement`).
- [ ] `CHANGELOG.md`: a dated section in plain language, built from merged PR titles
      since the last tag: `git log <last-tag>..HEAD --oneline`.
- [ ] "What's new" store text: 2–4 lines, user benefit first, in the project's voice.
- [ ] Tag after the build succeeds: `git tag v<version> && git push origin v<version>`.

## 3. Store requirements (first submission, and whenever they change)

- [ ] **Account deletion (Apple 5.1.1(v), Google Play policy).** An app with sign-up
      must let users delete their account *and data* from inside the app, and Google
      also needs a web URL for it. The backend ships `DELETE /api/v1/me` (body
      `{"confirm":"DELETE"}`); check the app has a Settings screen that calls it. If
      the screen or web URL is missing, this is ❌: file it with `backlog` as `p0` and stop.
- [ ] **Privacy nutrition label (App Store Connect) / Data safety (Play Console).**
      Declare what's collected: email (auth), user content (your tables), usage data
      (PostHog), diagnostics (Sentry), plus whatever `sensitive_data` in `appbox.yaml`
      lists. Draft the answers from `mobile/lib/analytics.ts`, the migrations and
      `.env.example`; the owner submits them.
- [ ] **Privacy policy URL** (required by both stores), and support URL.
- [ ] **Sign in with Apple** is required on iOS if the app offers any other
      third-party sign-in (e.g. Google).
- [ ] Listing assets: icon (1024×1024, no transparency), screenshots for each
      required device size, name, subtitle, description, keywords, category, age rating.
- [ ] Permission strings (`NSCameraUsageDescription` and so on) say *why* in plain
      words, if the app requests any.
- [ ] Health, financial or children's data: the matching `.agents/rules/` note has
      extra store rules. Read it.

## 4. Build + submit

- [ ] `eas build --profile production --platform <ios|android|all>`. Report the build URL.
- [ ] Install the build (TestFlight / internal track) and run the core loop once on a
      real device. Confirm a `screen_viewed` event lands in PostHog from that build.
- [ ] `eas submit --platform <…>`, then the owner completes review questions in App
      Store Connect / Play Console.

## 5. After release

- [ ] Watch Sentry and the north-star funnel for 48h (`north-star-report` can read it).
- [ ] If a JS-only bug slips through: fix on a branch, then `eas update`, and say
      which builds it reaches.

Report: the checklist with ✅/❌/n/a, the build/submit URLs, and "What I need from you"
(the store-console steps only the owner can do).

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: Release notes wording, store listing copy and screenshots, pricing or availability changes, and releasing with a known issue. Ask each before submitting; store changes can't be quietly undone.
