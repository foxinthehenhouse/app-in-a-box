import { createClient } from "@supabase/supabase-js";
import { Platform } from "react-native";
import "react-native-url-polyfill/auto";

import { DEMO, demoAuth } from "./demo";
import { createSecureStorage } from "./secure-store";

const url = process.env.EXPO_PUBLIC_SUPABASE_URL ?? "";
const anonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? "";

export const supabaseConfigured = Boolean(url && anonKey);

// The anon/publishable key is safe to ship: RLS is what protects data.
// The session itself lives in the keychain / keystore (lib/secure-store.ts); web has no
// SecureStore, so supabase-js falls back to localStorage there. ⚖️ Kyle 2026-10-02.
export const supabase = createClient(url || "http://localhost", anonKey || "missing", {
  auth: {
    storage: Platform.OS === "web" ? undefined : createSecureStorage(),
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: Platform.OS === "web",
  },
});

/** Sign out on this device only (other devices stay signed in). */
export async function signOutThisDevice(): Promise<void> {
  if (DEMO) return demoAuth.signOut();
  await supabase.auth.signOut({ scope: "local" });
}

/**
 * The signed-in user's id from the stored session (demo: the demo user), or null.
 * Never throws: unreadable storage counts as signed out.
 */
export async function currentUserId(): Promise<string | null> {
  if (DEMO) return demoAuth.current()?.id ?? null;
  try {
    const { data } = await supabase.auth.getSession();
    return data.session?.user.id ?? null;
  } catch {
    return null;
  }
}
