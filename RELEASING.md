# Releasing: the real-cloud check

The selftest proves everything a container can run: the renderer, every guard and its
negative control, the backend, a real `create-expo-app` build, and the syntax of every
Maestro flow and EAS workflow. What it can't prove needs real accounts: a phone, EAS
servers, and the app stores.

Before a release is tagged, someone runs this checklist **with their own accounts** and
posts the results on the release's tracking issue. It doesn't have to be a maintainer,
and the first section costs nothing. If you run it, you're helping: say which steps
you ran, on what (device, OS, Expo SDK), and paste anything that failed.

Use a throwaway app idea and throwaway accounts. Nothing here should touch an app you
care about.

## Free (GitHub, Supabase, Expo, PostHog and Sentry free tiers)

- [ ] **Start to finish:** in a new empty folder, run the plugin's `new-app` with a
      one-line idea. Shape, the idea check and the prototype complete, and scaffold
      produces a repo whose `npm run gates` and `pytest` both pass.
- [ ] **Provision:** `provision` creates the GitHub repo, the Supabase project and the
      Expo project, and wires every secret without printing one. Afterwards,
      `node mobile/scripts/check-eas-shipping-env.js` passes, and `/health` lists no
      `features_unavailable` for the services you picked.
- [ ] **On a phone:** the app runs in Expo Go or a dev build. You can sign in with a real
      email OTP, see Home, edit your name, toggle settings and sign out. The events
      show up in PostHog, and `GET /debug/sentry` on a non-production API shows up in Sentry.
- [ ] **Demo flows (Maestro):** with `EXPO_PUBLIC_DEMO=1 npx expo start` and a booted
      simulator, `maestro test -e APP_URL=exp://127.0.0.1:8081 mobile/.maestro/`
      passes. Do it once through the Maestro MCP from your agent too (`list_devices`
      → `run`).
- [ ] **PR preview (EAS):** open a PR. `.eas/workflows/pr-preview.yml` builds a preview,
      or OTAs to `pr-<n>` when native code hasn't changed. `e2e.yml` runs the `smoke`
      flows on an Android emulator and an iOS simulator.
- [ ] **Release + rollback:** push to `release`. With native code unchanged it OTAs
      to 10% of `production` (`eas update:list --branch production` shows the
      rollout) and the run waits on a "Roll out to 100%" approval per platform. Run
      `scripts/rollback-ota.sh` (it only plans): it names the update, says the rollout
      is in progress and prints the promote command. Approve one platform's step and
      check that update reaches 100%; reject the other and run
      `scripts/rollback-ota.sh --yes`, which reverts that rollout. Then, with nothing in
      progress, `scripts/rollback-ota.sh --yes` rolls back a full update; the app
      falls back to the previous one on the next launch or two.
- [ ] **Readable OTA crashes (Sentry):** in an OTA build, throw a test error from a
      button. In Sentry it shows a symbolicated stack trace (file names and lines from
      your source, not `index.android.bundle`), release `<app id>@<version>+<update id>`
      and the `expo-update-id` tag, and the update job's log shows the source maps
      uploaded.
- [ ] **Self-driving loop:** in the generated repo, ask "what should I work on next?"
      (`next`), file a ticket (`backlog`), and take one small feature through
      `feature-discovery` → `build-feature` → `land` to a merged PR.

## Paid (only if you're shipping to a store)

- [ ] **TestFlight** (Apple Developer Program, $99/yr): follow provision step 5 (App
      Store Connect API key, `ascAppId`). A native change on `release` builds and
      submits, and the build appears in TestFlight.
- [ ] **Play internal testing** (Google Play, $25 once): do the first upload by hand,
      then add the service-account key. A native change on `release` reaches internal
      testing.
- [ ] **Backend host:** Railway (about $5/mo after the trial), Fly.io or Render.
      `/health?deep=1` reports the deployed `version` and `db: ok`.

## Recording results

Open (or comment on) the tracking issue for the release with:

```
Ran: <which boxes>   Device/OS: <...>   Expo SDK: <...>   Kit commit: <sha>
Failed: <step> — <what happened, logs>
```

Every failure becomes an issue. Where it can, the fix adds a selftest check that fails
without it, so the next release doesn't need a human to catch it again.
