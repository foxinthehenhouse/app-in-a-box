# Apple + Google sign-in (optional, after the prototype works)

Email one-time codes work everywhere with zero setup, so ship with those first. Add
social sign-in when you're preparing a TestFlight build. On iOS, Apple **requires**
Sign in with Apple if you offer any other social login.

## Apple
1. Apple Developer → Identifiers → your bundle id → enable **Sign in with Apple**.
2. Supabase → Auth → Providers → Apple: enable, and add your bundle id to
   **Client IDs**. The native flow needs no secret key.
3. `npx expo install expo-apple-authentication`, then add `"usesAppleSignIn": true`
   under `ios` in `app.json`.
4. Call `AppleAuthentication.signInAsync({ requestedScopes: [FULL_NAME, EMAIL] })`,
   then `supabase.auth.signInWithIdToken({ provider: "apple", token: identityToken })`.

## Google
1. In the Google Cloud console, set up the OAuth consent screen, then create **Web**
   and **iOS** OAuth client IDs. The iOS one uses your bundle id.
2. Supabase → Auth → Providers → Google: add both client IDs. For native iOS, tick
   "Skip nonce check".
3. `npx expo install @react-native-google-signin/google-signin`, and add its config
   plugin with the iOS URL scheme (the reversed iOS client id).
4. `GoogleSignin.configure({ webClientId, iosClientId })` → `signIn()` →
   `supabase.auth.signInWithIdToken({ provider: "google", token: idToken })`.
5. The new env vars (`EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`, `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID`)
   must be wired for shipping builds: `eas env:create` + `EAS_MANAGED`. Forge once
   shipped Google sign-in as a silent no-op because they weren't.

Testing either one needs a **development or preview build**, not Expo Go.
