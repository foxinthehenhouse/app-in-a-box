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
| **OTA update** | JS/assets only, same native build | push to `release` (`release.yml`), or by hand `eas update --branch production --rollout-percentage 10 --message "<summary>"` | Yes: revert the rollout, or roll back (`scripts/rollback-ota.sh`) |
| **TestFlight / internal** | New native build for testers | `eas build --profile preview` (Android APK) or `--profile production` + `eas submit -p ios` | Mostly |
| **Store release** | Public build | `eas build --profile production --platform all` then `eas submit --platform all` | **No** |

**OTA is only safe for JS changes.** `app.json` uses `runtimeVersion: {policy:
"appVersion"}`, so an update only reaches builds with the same `version`. Any new
native module, permission, config plugin or SDK bump needs a new build. When unsure,
build. Check with `npx expo install --check` and `git diff <last-release-tag> --
mobile/app.json mobile/package.json`.

## 1. Pre-flight (all releases)

- [ ] On a release branch or `main` at a tagged commit; `git status` clean.
- [ ] Gates green: `cd mobile && npm run gates` and `scripts/dev-venv.sh python -m pytest -q`.
- [ ] Backend deployed first, and `/health` shows `features_unavailable: []` for
      every feature this build uses. Old app builds must keep working against it
      (additive wire rule).
- [ ] Every `EXPO_PUBLIC_*` the app reads is set for the target EAS environment:
      `eas env:list --environment production`. Missing = a feature that silently
      does nothing in the store build.
- [ ] Sentry source maps upload, so crashes are readable: `SENTRY_AUTH_TOKEN`,
      `SENTRY_ORG` and `SENTRY_PROJECT` are set for the target EAS environment
      (`eas env:list --environment production`). Every OTA job in
      `mobile/.eas/workflows/` uploads with `upload_sentry_sourcemaps: true` and fails
      without them; that's deliberate, an unreadable OTA crash is worse than a red job.

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

## 5. OTA: promote the staged rollout

An OTA reaches 10% of users first and waits on a "Roll out to 100%" approval in the
workflow run. Report the numbers, then tell the owner which button to press (approving
is theirs, on expo.dev):

- [ ] The update's Sentry release is `<app id>@<version>+<update id>` (Sentry →
      Releases; the update id is in the workflow run). It has had 24 hours at 10%.
- [ ] Crash-free sessions are **99.5% or more** and no lower than the previous
      release's; no new issue first seen in this release. Under about 100 sessions,
      say so and list the release's issues instead of quoting a percentage.
- [ ] All ✅: **promote**, by approving the step (or `cd mobile && eas update:edit
      <group-id> --rollout-percentage 100 --non-interactive`).
- [ ] Any ❌: **don't promote.** Reject the approval and run
      `scripts/rollback-ota.sh` (it plans; `--yes` reverts the rollout).
- [ ] Either way, finish the rollout before the next release: EAS won't publish a new
      update on a runtime with a rollout still in progress.

The gate and its reasoning: `docs/runbooks/release.md` → "Staged OTA rollout".

## 6. After release

- [ ] Watch Sentry and the north-star funnel for 48h (`north-star-report` can read it).
- [ ] If a JS-only bug slips through: fix on a branch, then ship it as an OTA (it
      stages like any other), and say which builds it reaches.

Report: the checklist with ✅/❌/n/a, the build/submit URLs, and "What I need from you"
(the store-console steps and the rollout approval, which only the owner can do).

## Ask the owner

Follow `.agents/rules/product-judgement.md`: ask with a structured question (recommended option first), never decide these silently. In this skill that means: Release notes wording, store listing copy and screenshots, pricing or availability changes, releasing with a known issue, and promoting an OTA whose crash-free numbers miss the gate. Ask each before submitting; store changes can't be quietly undone.
