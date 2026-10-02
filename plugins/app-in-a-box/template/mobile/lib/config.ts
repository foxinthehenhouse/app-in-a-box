/**
 * Build-configuration honesty. A shipping build with an EXPO_PUBLIC_* value missing
 * used to fail like a dead network ("You're offline") or, for Supabase, bounce to a
 * provider error page. Both are lies: the device is fine, the BUILD is incomplete.
 * This is the one place that says so, and three surfaces read it:
 *   - app/_layout.tsx reports it to monitoring once at boot;
 *   - app/(auth)/sign-in.tsx shows t("errors.misconfigured") before the user types;
 *   - lib/api.ts and lib/auth.tsx return the same message when a call is attempted.
 * Demo mode needs none of these, so it reports nothing missing.
 * scripts/check-eas-shipping-env.js is the build-time half of the same guarantee.
 */
import { DEMO } from "./demo";

const REQUIRED: readonly [name: string, value: string | undefined][] = [
  ["EXPO_PUBLIC_API_URL", process.env.EXPO_PUBLIC_API_URL],
  ["EXPO_PUBLIC_SUPABASE_URL", process.env.EXPO_PUBLIC_SUPABASE_URL],
  ["EXPO_PUBLIC_SUPABASE_ANON_KEY", process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY],
];

/** Names of the shipping-build settings this build is missing (empty in demo mode). */
export const MISSING_CONFIG: readonly string[] = DEMO ? [] : REQUIRED.filter(([, v]) => !v).map(([k]) => k);

export const configured = MISSING_CONFIG.length === 0;
