import { Fragment, createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { identifyUser, resetAnalytics } from "./analytics";
import { DEMO, demoAuth } from "./demo";
import { forgetPushToken } from "./push";
import { setCacheOwner } from "./query";
import { supabase, supabaseConfigured } from "./supabase";

export interface AuthUser {
  id: string;
  email: string | null;
}

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
}

const AuthContext = createContext<AuthState>({ user: null, loading: true });

interface InternalAuthState extends AuthState {
  /** Bumped when one signed-in user replaces another (A -> B): the subtree remounts. */
  generation: number;
}

function toAuthUser(u: { id: string; email?: string | null } | null | undefined): AuthUser | null {
  return u ? { id: u.id, email: u.email ?? null } : null;
}

function useSupabaseAuth(): InternalAuthState {
  const [state, setState] = useState<InternalAuthState>(() => ({
    user: DEMO ? demoAuth.current() : null,
    loading: !DEMO,
    generation: 0,
  }));

  useEffect(() => {
    /**
     * Every auth change goes through here. The cache owner is updated (and, on a
     * real user change, the cache cleared) SYNCHRONOUSLY, before the new user's
     * screens render and subscribe: clearing in a later effect cancels the fetch
     * those screens just started and strands them on a skeleton.
     */
    const apply = (u: AuthUser | null) => {
      const changed = setCacheOwner(u?.id ?? null);
      // The push token is remembered per device: a user change (a 401, another
      // device's sign-out, another account) must not leave it for the next user.
      if (changed) void forgetPushToken();
      const switched = changed && u !== null;
      setState((prev) => ({ user: u, loading: false, generation: prev.generation + (switched ? 1 : 0) }));
      if (u) identifyUser(u.id);
      else resetAnalytics();
    };

    if (DEMO) {
      setCacheOwner(demoAuth.current()?.id ?? null);
      return demoAuth.subscribe(apply);
    }
    supabase.auth
      .getSession()
      .then(({ data }) => toAuthUser(data.session?.user))
      // Unreadable storage / a corrupt session: treat as signed out. `loading` MUST
      // clear, or the splash never hides and the app looks frozen.
      .catch(() => null)
      .then((u) => {
        setCacheOwner(u?.id ?? null);
        setState((prev) => ({ ...prev, user: u, loading: false }));
        if (u) identifyUser(u.id);
      });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => apply(toAuthUser(session?.user)));
    return () => sub.subscription.unsubscribe();
  }, []);

  return state;
}

/**
 * Whenever the signed-in user changes (sign-out, a 401, account deletion, another
 * account), lib/query.ts `setCacheOwner` drops the cached queries and queued
 * mutations: user B must never see user A's cache. A fresh sign-in from signed
 * out (null -> B) clears nothing: the cache is already empty (sign-out cleared
 * it, and a persisted cache from another user is dropped on restore).
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const { user, loading, generation } = useSupabaseAuth();
  const value = useMemo(() => ({ user, loading }), [user, loading]);
  return (
    <AuthContext.Provider value={value}>
      <Fragment key={generation}>{children}</Fragment>
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

/**
 * What went wrong signing in, as a stable code. The screen shows
 * `t("auth.errors." + code)`: Supabase's messages are English, change between
 * versions and sometimes leak internals, so they never reach the UI.
 */
export type AuthErrorCode = "invalidCode" | "expired" | "rateLimited" | "invalidEmail" | "network" | "misconfigured" | "generic";

interface AuthErrorLike {
  code?: string;
  status?: number;
  name?: string;
  message?: string;
}

// First match wins, so the order is the precedence (an expired code that also mentions
// the network is "expired").
const AUTH_ERROR_RULES: readonly [AuthErrorCode, (code: string, msg: string, err: AuthErrorLike) => boolean][] = [
  ["expired", (code, msg) => code === "otp_expired" || msg.includes("expired")],
  ["rateLimited", (code, msg, err) => code.startsWith("over_") || err.status === 429 || msg.includes("rate limit")],
  [
    "invalidEmail",
    (code, msg) => code === "email_address_invalid" || code === "email_address_not_authorized" || msg.includes("invalid email"),
  ],
  [
    "network",
    (_code, msg, err) =>
      err.name === "AuthRetryableFetchError" || err.status === 0 || msg.includes("failed to fetch") || msg.includes("network"),
  ],
];

/** Supabase AuthError (`code`, `status`, `name`) -> AuthErrorCode. `fallback` for anything unrecognised. */
export function authErrorCode(err: AuthErrorLike | null | undefined, fallback: AuthErrorCode = "generic"): AuthErrorCode | null {
  if (!err) return null;
  const code = err.code ?? "";
  const msg = (err.message ?? "").toLowerCase();
  return AUTH_ERROR_RULES.find(([, test]) => test(code, msg, err))?.[0] ?? fallback;
}

/** Email one-time code: works in Expo Go with no deep-link setup. */
export async function sendEmailCode(email: string): Promise<{ error: AuthErrorCode | null }> {
  if (DEMO) return { error: null };
  if (!supabaseConfigured) return { error: "misconfigured" }; // the build, not the user, is at fault
  try {
    const { error } = await supabase.auth.signInWithOtp({ email, options: { shouldCreateUser: true } });
    return { error: authErrorCode(error) };
  } catch (e) {
    return { error: authErrorCode(e instanceof Error ? e : {}, "network") };
  }
}

export async function verifyEmailCode(email: string, token: string): Promise<{ error: AuthErrorCode | null }> {
  if (DEMO) {
    const res = demoAuth.verify(email, token);
    return { error: authErrorCode(res.error ? { message: res.error } : null, "invalidCode") };
  }
  if (!supabaseConfigured) return { error: "misconfigured" };
  try {
    const { error } = await supabase.auth.verifyOtp({ email, token, type: "email" });
    return { error: authErrorCode(error, "invalidCode") };
  } catch (e) {
    return { error: authErrorCode(e instanceof Error ? e : {}, "network") };
  }
}
