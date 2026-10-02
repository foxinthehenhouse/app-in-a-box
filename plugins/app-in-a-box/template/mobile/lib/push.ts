/**
 * Push notifications, client side (expo-notifications -> Expo push token ->
 * POST /api/v1/me/push-token). The backend (push_tokens table, push_service,
 * receipts cron) ships with the template.
 *
 * - **Ask in context, never on launch.** The template asks from the Settings
 *   toggle. For a feature ("remind me when..."), call `enablePush()` from that
 *   moment, after a line explaining the value. iOS shows the system prompt once.
 * - **No-op where push can't work**: web, simulators/emulators, Expo Go, and before
 *   `eas init` gives the app a projectId. `pushSupported()` says which. There,
 *   expo-notifications is never even loaded (it's imported lazily), so Expo Go
 *   and web don't log its "not supported here" warnings.
 * - The token is remembered on the device WITH the id of the user who opted in,
 *   so sign-out can unregister it BEFORE the session ends (lib/session.ts), and a
 *   re-register on launch refreshes it. The device is shared: a token remembered
 *   for user A is invisible to user B (not refreshed, not "enabled", never
 *   unregistered as B), so B is never registered for pushes without opting in.
 *   Any auth-user change also forgets it (lib/auth.tsx).
 * - Taps: `usePushNavigation()` (app/_layout.tsx) routes `data.url` through
 *   lib/links.ts `resolveDeepLink`, so a payload can only open a linkable route.
 * - Analytics: `pushChanged` (success AND failure, with outcome) and `pushOpened`.
 * - Demo mode: the demo backend accepts the register/unregister calls, but a
 *   real token still needs a device build, so the toggle says "not available".
 */
import { useCallback, useEffect, useState } from "react";
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import Constants, { ExecutionEnvironment } from "expo-constants";
import * as Device from "expo-device";
import { router, type Href } from "expo-router";
import type * as NotificationsModule from "expo-notifications";

import { analytics, startTimer } from "./analytics";
import { ApiError, registerPushToken, unregisterPushToken } from "./api";
import { resolveDeepLink } from "./links";
import { currentUserId } from "./supabase";

export const PUSH_TOKEN_KEY = "push.token";

export type PushStatus = "enabled" | "disabled" | "denied" | "unsupported";
export type PushOutcome = PushStatus | "error";

type Notifications = typeof NotificationsModule;

function projectId(): string | undefined {
  const extra = Constants.expoConfig?.extra as { eas?: { projectId?: string } } | undefined;
  return extra?.eas?.projectId ?? Constants.easConfig?.projectId ?? undefined;
}

/** Where a remote push token can actually be obtained. */
export function pushSupported(): boolean {
  if (Platform.OS === "web") return false;
  if (!Device.isDevice) return false; // simulators/emulators have no push token
  if (Constants.executionEnvironment === ExecutionEnvironment.StoreClient) return false; // Expo Go
  return !!projectId();
}

let loaded: Promise<Notifications> | null = null;

/**
 * expo-notifications, loaded on first use (only where push is supported), with the
 * foreground handler installed once: show the banner while the app is open.
 */
export function loadNotifications(): Promise<Notifications> {
  loaded ??= Promise.resolve().then(() => {
    // A lazy require, not `import()`: evaluated only here (Metro and jest both
    // handle it), so Expo Go and web never load the module or log its warnings.
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- deliberate lazy load, see above
    const N = require("expo-notifications") as Notifications;
    N.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: false,
        shouldSetBadge: false,
      }),
    });
    return N;
  });
  return loaded;
}

function platform(): "ios" | "android" | null {
  return Platform.OS === "ios" || Platform.OS === "android" ? Platform.OS : null;
}

/** What's on the device: the token and the user who registered it. */
interface RememberedToken {
  token: string;
  userId: string;
}

async function readRemembered(): Promise<RememberedToken | null> {
  try {
    const raw = await AsyncStorage.getItem(PUSH_TOKEN_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<RememberedToken> | null;
    // An older build stored a bare token string (JSON.parse throws or yields a
    // non-object): it has no owner, so it belongs to nobody.
    return v && typeof v.token === "string" && typeof v.userId === "string" ? { token: v.token, userId: v.userId } : null;
  } catch {
    return null;
  }
}

async function remember(token: string): Promise<void> {
  const userId = await currentUserId();
  if (!userId) return; // signed out: nothing to own it
  await AsyncStorage.setItem(PUSH_TOKEN_KEY, JSON.stringify({ token, userId } satisfies RememberedToken));
}

/** This device's token, if the CURRENT user registered it. Another user's token reads as none. */
export async function storedPushToken(): Promise<string | null> {
  const saved = await readRemembered();
  if (!saved) return null;
  return saved.userId === (await currentUserId()) ? saved.token : null;
}

/** Current state for the Settings toggle, without prompting. */
export async function pushStatus(): Promise<PushStatus> {
  if (!pushSupported()) return "unsupported";
  const N = await loadNotifications();
  const perm = await N.getPermissionsAsync();
  if (!perm.granted && !perm.canAskAgain) return "denied";
  return perm.granted && (await storedPushToken()) ? "enabled" : "disabled";
}

async function getToken(N: Notifications): Promise<string> {
  if (Platform.OS === "android") {
    await N.setNotificationChannelAsync("default", {
      name: "Default",
      importance: N.AndroidImportance.DEFAULT,
    });
  }
  const { data } = await N.getExpoPushTokenAsync({ projectId: projectId() });
  return data;
}

function track(enabled: boolean, outcome: PushOutcome, elapsed: () => number, error?: unknown): PushOutcome {
  const ok = outcome !== "error";
  analytics.pushChanged({
    enabled,
    outcome,
    success: ok,
    error_code: ok ? null : error instanceof ApiError ? `http_${error.status}` : "push_failed",
    duration_ms: elapsed(),
  });
  return outcome;
}

/**
 * Ask (if needed), get the token, register it with the backend. Call from a
 * user action that explains why. Resolves the outcome; never throws.
 */
export async function enablePush(): Promise<PushOutcome> {
  const elapsed = startTimer();
  if (!pushSupported()) return track(true, "unsupported", elapsed);
  try {
    const N = await loadNotifications();
    let perm = await N.getPermissionsAsync();
    if (!perm.granted && perm.canAskAgain) perm = await N.requestPermissionsAsync();
    if (!perm.granted) return track(true, "denied", elapsed);
    const token = await getToken(N);
    await registerPushToken(token, platform());
    await remember(token);
    return track(true, "enabled", elapsed);
  } catch (e) {
    return track(true, "error", elapsed, e);
  }
}

/** Unregister this device's token (server first, then forget it locally). Never throws. */
export async function disablePush(): Promise<PushOutcome> {
  const elapsed = startTimer();
  const token = await storedPushToken();
  if (!token) return "disabled"; // nothing registered from this device: nothing to track
  try {
    await unregisterPushToken(token);
    await AsyncStorage.removeItem(PUSH_TOKEN_KEY);
    return track(false, "disabled", elapsed);
  } catch (e) {
    return track(false, "error", elapsed, e);
  }
}

/** Forget the local token without calling the server (the account is gone, or so is the session). */
export async function forgetPushToken(): Promise<void> {
  try {
    await AsyncStorage.removeItem(PUSH_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

/**
 * Re-register on launch when the CURRENT user turned push on: tokens rotate, and it
 * refreshes last_seen_at. A token remembered for someone else is forgotten, never
 * re-registered under this user.
 */
export async function refreshPushRegistration(): Promise<void> {
  if (!pushSupported()) return;
  if (!(await storedPushToken())) {
    if (await readRemembered()) await forgetPushToken();
    return;
  }
  try {
    const N = await loadNotifications();
    const perm = await N.getPermissionsAsync();
    if (!perm.granted) return;
    const token = await getToken(N);
    await registerPushToken(token, platform());
    await remember(token);
  } catch {
    // next launch tries again
  }
}

/** Notification payload -> a safe internal route, or null. Only `data.url` is read. */
export function routeFromNotification(data: unknown): string | null {
  const url = data && typeof data === "object" ? (data as { url?: unknown }).url : undefined;
  return typeof url === "string" ? resolveDeepLink(url) : null;
}

/** Route notification taps (warm and cold start). Mount once, while signed in. */
export function usePushNavigation(enabled: boolean): void {
  useEffect(() => {
    if (!enabled || !pushSupported()) return;
    let alive = true;
    let remove: (() => void) | undefined;
    const open = (response: NotificationsModule.NotificationResponse | null) => {
      const route = response ? routeFromNotification(response.notification.request.content.data) : null;
      if (!route || !alive) return;
      analytics.pushOpened(route);
      router.push(route as Href); // resolveDeepLink only returns routes from LINKABLE_ROUTES
    };
    void loadNotifications()
      .then(async (N) => {
        if (!alive) return;
        const sub = N.addNotificationResponseReceivedListener(open);
        remove = () => sub.remove();
        const last = await N.getLastNotificationResponseAsync();
        open(last);
        if (last) await N.clearLastNotificationResponseAsync();
      })
      .catch(() => undefined);
    void refreshPushRegistration();
    return () => {
      alive = false;
      remove?.();
    };
  }, [enabled]);
}

/** The Settings toggle's state machine. */
export function usePushSetting(): { status: PushStatus | null; busy: boolean; setEnabled: (on: boolean) => Promise<PushOutcome> } {
  const [status, setStatus] = useState<PushStatus | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    pushStatus()
      .then((s) => alive && setStatus(s))
      .catch(() => alive && setStatus("unsupported"));
    return () => {
      alive = false;
    };
  }, []);

  const setEnabled = useCallback(async (on: boolean) => {
    setBusy(true);
    const outcome = on ? await enablePush() : await disablePush();
    setBusy(false);
    if (outcome !== "error") setStatus(outcome);
    return outcome;
  }, []);

  return { status, busy, setEnabled };
}
