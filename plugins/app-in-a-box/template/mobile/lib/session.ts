/**
 * Ending a session, in the right order:
 *   1. unregister this device's push token (needs the auth header, so BEFORE sign-out;
 *      best-effort with a timeout, so a dead network never blocks signing out)
 *   2. forget every cached query + queued mutation for this user (lib/query.ts)
 *   3. sign out this device (the auth gate then shows sign-in)
 *
 * After account deletion the server already dropped the tokens (cascade), so
 * `endSession({ unregisterPush: false })` skips step 1's network call.
 */
import { clearUserCache } from "./query";
import { disablePush, forgetPushToken } from "./push";
import { signOutThisDevice } from "./supabase";

export const PUSH_UNREGISTER_TIMEOUT_MS = 3000;

export async function endSession({ unregisterPush = true }: { unregisterPush?: boolean } = {}): Promise<void> {
  if (unregisterPush) {
    let timer: ReturnType<typeof setTimeout> | undefined;
    await Promise.race([
      disablePush(),
      new Promise((resolve) => {
        timer = setTimeout(resolve, PUSH_UNREGISTER_TIMEOUT_MS);
      }),
    ]);
    clearTimeout(timer);
  }
  await forgetPushToken();
  await clearUserCache();
  await signOutThisDevice();
}

/**
 * Last resort when endSession() threw (storage error, a network hiccup in
 * sign-out): do each local step independently, ignoring failures, so the device
 * ends up signed out no matter which step broke. Used after account deletion,
 * where the server side is already done and staying signed in would be a lie.
 */
export async function forceLocalSignOut(): Promise<void> {
  const steps: (() => Promise<void>)[] = [forgetPushToken, () => clearUserCache(), signOutThisDevice];
  for (const step of steps) {
    try {
      await step();
    } catch {
      // keep going: the remaining steps still matter
    }
  }
}

/** The Settings "Sign out" button. */
export function signOut(): Promise<void> {
  return endSession();
}
