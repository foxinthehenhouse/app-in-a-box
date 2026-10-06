# Ship to TestFlight and Google Play

Your generated repo already has the release pipeline: EAS workflows that build and
submit store binaries, or send an over-the-air update when only JavaScript changed.
What it can't do is sign up for the stores or press their buttons. This page is the
path from "works on my phone" to testers on both platforms.

## Before you start

- **Apple Developer Program** ($99/yr) for TestFlight and the App Store. Enrolment
  needs identity verification, so only you can do it.
- **Google Play developer account** ($25 once).
- The generated app connected to EAS (the provision phase does this; see
  [provision](../../plugins/app-in-a-box/skills/provision/SKILL.md), step 5).

## 1. One-time store setup (you do this)

**iOS.** Create the app in App Store Connect, then run
`cd mobile && eas credentials -p ios` and choose App Store Connect → "Set up your
project to use an API Key for EAS Submit". Find the app's **Apple ID** (App Store
Connect → the app → General → App Information) and give it to your agent: it goes in
`mobile/eas.json` as `submit.production.ios.ascAppId`. Without it, every TestFlight
submit fails. A test in the repo checks it's an Apple ID and not a bundle id.

**Android.** Google Play needs the first upload by hand: Play Console → your app →
Internal testing → upload the first production `.aab`. Then run
`eas credentials -p android` and upload a Google service account key. Never put the
key file in the repo.

EAS Workflows need no token in GitHub: connect the expo.dev GitHub app to the repo
once, with base directory `mobile`.

## 2. Release: push to the `release` branch

The release order is always database, then backend, then app, because old app builds
stay installed for weeks:

1. Apply migrations (additive only) with `supabase db push`.
2. Merge to `main`; the backend host deploys it. Check `/health?deep=1`.
3. Ship the app: `git push origin main:release`.

`mobile/.eas/workflows/release.yml` fingerprints the native layer, per platform. If
nothing native changed, it publishes an **OTA update** to the `production` channel.
If something did (a new native module, permission or SDK bump), it **builds and
submits** to TestFlight and Play internal testing. Store review and phased rollout
stay human steps in App Store Connect and Play Console.

Every PR also gets a preview (an OTA update or a fresh preview build) and Maestro
smoke flows on an emulator and a simulator.

## 3. What the stores will ask for

Run the `ship` skill in the generated repo (`/ship` in Claude Code, `$ship` in
Codex). It walks the checklist and reports each line as done, missing or not
applicable:

- **Account deletion** inside the app: built in (Settings → delete account, backed by
  `DELETE /api/v1/me`). Google also needs a web URL for it.
- **Privacy nutrition label / Data safety form**: drafted from the app's analytics
  events, migrations and env vars; you submit them.
- **Privacy policy and support URLs.**
- **Sign in with Apple**, if you offer any other social sign-in (see the
  [social sign-in recipe](../../plugins/app-in-a-box/skills/recipe-social-auth/SKILL.md)).
- A **demo account** for App Review, screenshots and listing text.

The longer list, including store review gotchas, is the
[production checklist](../../plugins/app-in-a-box/docs/PRODUCTION.md).

## If something goes wrong

A JavaScript-only bug: fix it on a branch and ship an OTA update. A bad OTA update:
`scripts/rollback-ota.sh` shows what it would roll back, and `--yes` does it. A
native build can't be un-shipped; ship a new one.

## Has this been tested for real?

CI checks every EAS workflow against Expo's documented schema, and the rollback
script against a fake `eas`. A real TestFlight and Play submission needs real
accounts, so before each kit release someone runs [RELEASING.md](../../RELEASING.md)
with their own and posts the results. If you ship with the kit, your report helps.

## Related

- [Quickstart](../../README.md#quickstart)
- [What's in the generated repo, and why](what-you-get.md)
- [Add payments, AI, push, offline and social sign-in](add-payments-ai-push-offline-social-sign-in.md)
