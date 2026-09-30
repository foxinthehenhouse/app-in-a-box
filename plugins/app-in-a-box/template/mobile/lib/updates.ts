/**
 * OTA updates (expo-updates + EAS Update).
 *
 * How it's configured (app.json + eas.json):
 * - `runtimeVersion: { policy: "fingerprint" }`: an update only reaches builds
 *   whose native code matches, so a JS update can never crash a binary that lacks
 *   a native module it needs. Native change => new build (the EAS workflows'
 *   fingerprint job decides).
 * - Channels match the eas.json build profiles: development, preview, production.
 *   `eas update --channel production` ships to store builds.
 * - `updates.checkAutomatically: "ON_LOAD"` + `fallbackToCacheTimeout: 0`: launch
 *   never waits on the network; a new update downloads in the background and
 *   applies on the next launch.
 * - `updates.url` is written by `eas update:configure` (provision phase). Until
 *   then `Updates.isEnabled` is false and everything here is a no-op.
 *
 * On top of that, `useUpdatePrompt()` checks again when the app returns to the
 * foreground (at most every 30 min) and, when an update has downloaded, offers
 * "Restart" (components/ui/UpdateBanner.tsx), so a same-day fix lands the same day.
 *
 * Always a no-op in dev (__DEV__), Expo Go, web and when updates are disabled.
 * Rollback: `eas update:rollback` (docs/runbooks/rollback.md).
 */
import { useEffect, useState } from "react";
import { AppState, Platform } from "react-native";
import * as Updates from "expo-updates";

import { analytics } from "./analytics";

export const CHECK_INTERVAL_MS = 30 * 60 * 1000;

/** True only where an OTA update can actually be fetched and applied. */
export function updatesSupported(): boolean {
  return !__DEV__ && Platform.OS !== "web" && Updates.isEnabled;
}

/** Check + download. Resolves true when a new update is downloaded and ready to apply. */
export async function fetchUpdateIfAvailable(): Promise<boolean> {
  if (!updatesSupported()) return false;
  try {
    const check = await Updates.checkForUpdateAsync();
    if (!check.isAvailable) return false;
    const fetched = await Updates.fetchUpdateAsync();
    return fetched.isNew;
  } catch {
    // offline, or the update server is down: try again next foreground
    return false;
  }
}

export async function applyUpdate(): Promise<void> {
  analytics.updateRestarted();
  if (!updatesSupported()) return;
  await Updates.reloadAsync();
}

/** Pure throttle: check on the first foreground, then at most every CHECK_INTERVAL_MS. */
export function shouldCheck(lastCheckedAt: number | null, now: number, interval = CHECK_INTERVAL_MS): boolean {
  return lastCheckedAt === null || now - lastCheckedAt >= interval;
}

/** { ready, restart, dismiss }: `ready` turns true once an update has downloaded. */
export function useUpdatePrompt(): { ready: boolean; restart: () => void; dismiss: () => void } {
  const [ready, setReady] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!updatesSupported()) return;
    let alive = true;
    let lastChecked: number | null = null;
    const check = () => {
      const now = Date.now();
      if (!shouldCheck(lastChecked, now)) return;
      lastChecked = now;
      void fetchUpdateIfAvailable().then((downloaded) => {
        if (!downloaded || !alive) return;
        analytics.updatePrompted();
        setReady(true);
      });
    };
    check();
    const sub = AppState.addEventListener("change", (s) => {
      if (s === "active") check();
    });
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);

  return {
    ready: ready && !dismissed,
    restart: () => void applyUpdate(),
    dismiss: () => setDismissed(true),
  };
}
