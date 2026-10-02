---
name: recipe-social-auth
description: Add Sign in with Apple and Google sign-in to an App in a Box app (Supabase Auth, native ID-token flow, no web redirect). Use when the prototype works on email codes and the owner is preparing a TestFlight / store build, or asks for "social login", "Apple sign in", "Google sign in". Covers provider setup, the mobile wiring, EAS env vars, tests and the done-means check.
---

# Recipe: Apple + Google sign-in

`$KIT` is the plugin root: `appbox.yaml` → `kit_root` if present, else
`${CLAUDE_PLUGIN_ROOT}` (Claude Code) or the folder two levels above this file (Codex /
pasted prompt).

Email one-time codes ship first (zero setup). Add social sign-in before the first
store build. **Apple requires Sign in with Apple on iOS if you offer any other social
login** (App Review guideline 4.8), so do both or neither. Source doc:
`$KIT/docs/SOCIAL_AUTH.md`.

No backend change: the API already verifies any Supabase session JWT
(`backend/auth.py`), whichever provider issued it.

## When to use

- The core loop works end to end with email sign-in, and
- you're about to cut a preview/production build (social sign-in can't be tested in
  Expo Go; it needs a development or preview build).

## Steps

### Apple (iOS)

1. **(owner)** Apple Developer → Identifiers → the app's bundle id → enable
   **Sign in with Apple**.
2. **(owner)** Supabase → Authentication → Providers → Apple: enable; add the bundle id
   under **Client IDs**. The native flow needs no secret key.
3. `cd mobile && npx expo install expo-apple-authentication expo-crypto`
4. `mobile/app.json`: `"ios": { "usesAppleSignIn": true }` and add
   `"expo-apple-authentication"` to `plugins`.
5. In `mobile/lib/auth.tsx`, add `signInWithApple()`:
   - `const nonce = Crypto.randomUUID()`; hash it with `Crypto.digestStringAsync(SHA256, nonce)`
   - `AppleAuthentication.signInAsync({ requestedScopes: [FULL_NAME, EMAIL], nonce: hashed })`
   - `supabase.auth.signInWithIdToken({ provider: "apple", token: credential.identityToken, nonce })`
   - Apple returns the name **only on the first sign-in**: if `credential.fullName`
     is present, `PATCH /api/v1/me` with `displayName` right away.
   - Treat `ERR_REQUEST_CANCELED` as a cancel, not an error.
6. Render `AppleAuthentication.AppleAuthenticationButton` (Apple's HIG requires their
   button) only when `AppleAuthentication.isAvailableAsync()` is true.

### Google (iOS + Android)

1. **(owner)** Google Cloud console: OAuth consent screen, then create a **Web** client
   and an **iOS** client (bundle id), plus an **Android** client (package name + the
   SHA-1 from `eas credentials`).
2. **(owner)** Supabase → Providers → Google: enable; add the Web + iOS client ids to
   Client IDs; tick **Skip nonce check** (the native iOS SDK doesn't pass one through).
3. `cd mobile && npx expo install @react-native-google-signin/google-signin`
4. `mobile/app.json` plugins:
   `["@react-native-google-signin/google-signin", { "iosUrlScheme": "com.googleusercontent.apps.<reversed-ios-client-id>" }]`
5. `GoogleSignin.configure({ webClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID, iosClientId: process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID })`
   → `GoogleSignin.signIn()` → `supabase.auth.signInWithIdToken({ provider: "google", token: idToken })`.
6. If either env var is empty, **hide the button and log once**; never render a button
   that silently does nothing (a real app shipped exactly that).

### Both

- Analytics: `signInStarted({ method })`, `signInSucceeded({ method })`,
  `signInFailed({ method, error_code })` (success AND failure, per the analytics rule).
- Accessibility: labels "Continue with Apple" / "Continue with Google", 48px targets.
- Account deletion (`DELETE /api/v1/me`) must be reachable in-app. For Apple, App
  Review also expects you to revoke the Apple token on deletion when you store refresh
  tokens; with the ID-token-only flow above you store none, so note that in review notes.

## Env / wiring checklist

| Where | What |
|---|---|
| EAS (preview + production) | `eas env:create --name EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID --value <id> --environment preview --environment production --visibility plaintext`, same for `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID` |
| `mobile/scripts/check-eas-shipping-env.js` | add both to `EAS_MANAGED` (the guard fails the build otherwise) |
| Railway / FEATURE_CONFIG | nothing: the backend doesn't see provider config |
| Supabase | providers enabled; redirect URLs untouched (native flow) |

## Tests to add

- `mobile/lib/__tests__/auth.test.ts`: mock `signInWithIdToken`; Apple cancel returns
  quietly; Apple first sign-in with a name PATCHes `/api/v1/me`; missing Google env
  hides the button (render test) instead of rendering a dead one.
- Maestro: a flow that asserts both buttons are visible on the sign-in screen of a
  preview build (the sign-in itself needs a real account; do it by hand once).

## Done means

- [ ] On a preview build, a fresh Apple ID and a fresh Google account each sign in, land
      in the app, and `GET /api/v1/me` returns their own id.
- [ ] `node mobile/scripts/check-eas-shipping-env.js` passes and lists both vars.
- [ ] PostHog shows `sign_in_succeeded` with `method=apple` and `method=google`.
- [ ] Deleting either account from the in-app settings returns 204 and signs out.
