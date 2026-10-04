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

## Free (GitHub, Supabase, Expo, Resend, PostHog and Sentry free tiers)

- [ ] **Start to finish:** in a new empty folder, run the plugin's `new-app` with a
      one-line idea. Shape, the idea check and the prototype complete, and scaffold
      produces a repo whose `npm run gates` and `pytest` both pass.
- [ ] **Provision:** `provision` creates the GitHub repo, the Supabase project and the
      Expo project, and wires every secret without printing one. Afterwards,
      `node mobile/scripts/check-eas-shipping-env.js` passes, and `/health` lists no
      `features_unavailable` for the services you picked.
- [ ] **Sign-in email (Resend free tier):** provision step 2.7 with a domain you've
      verified at Resend sets Supabase's custom SMTP without printing the key. Then a
      sign-in code reaches a fresh address from that domain, and the deployed API's
      `/health` (`APP_ENV=production`) stops listing "email sign-in (custom SMTP)".
      Before the step, it lists it.
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
      to `production`. Then run `scripts/rollback-ota.sh` (it only plans), check that
      it names the update you just published, and run `scripts/rollback-ota.sh --yes`.
      The app falls back to the previous update on the next launch or two.
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
