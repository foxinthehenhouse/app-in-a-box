/**
 * The analytics opt-in switch (Settings → Privacy), as two honest operations.
 *
 * Lives beside lib/analytics.ts rather than in it on purpose: analytics.ts DEFINES
 * events and never fires them, and scripts/check-analytics-coverage.js counts call
 * sites everywhere except there. Tested in lib/__tests__/analytics-optin.test.ts.
 */
import { analytics, posthog, setAnalyticsOptIn } from "./analytics";

/**
 * The user's current choice, from the SDK's persisted flag (after it has loaded), so
 * the Settings toggle shows what is actually in force. Without a client (no key) there
 * is nothing to opt out of: report "in".
 */
export async function readAnalyticsOptIn(): Promise<boolean> {
  if (!posthog) return true;
  try {
    await posthog.ready();
    return !posthog.optedOut;
  } catch {
    return true;
  }
}

/**
 * Change the choice AND record it, in the only order that leaves a trail: an opt-in is
 * captured after opting in (before, the SDK drops it as opted out); an opt-out is
 * captured before opting out (after, it would be dropped). Settings calls this.
 */
export async function changeAnalyticsOptIn(optIn: boolean): Promise<void> {
  if (!optIn) analytics.analyticsOptChanged(false);
  await setAnalyticsOptIn(optIn);
  if (optIn) analytics.analyticsOptChanged(true);
}
