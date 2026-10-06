/**
 * Typed product analytics (PostHog). This is the ONLY place events are defined.
 *
 * Rules (enforced by scripts/check-analytics-coverage.js in `npm run gates`):
 *   - Every screen under app/(app)/ fires at least one analytics.* call on mount.
 *   - Every helper here has a real call site. An event nobody calls never fires.
 *   - A user-initiated mutation fires BOTH a success and a failure event
 *     (`success`, `error_code`, `duration_ms`), so a silent failure still shows up.
 *
 * Privacy: identify by user id only (never email). Session replay, if you turn
 * it on, masks all text and images, and scripts/check-replay-unmask.js fails CI
 * on any unmask API. Analytics is disabled in dev builds unless
 * EXPO_PUBLIC_ANALYTICS_IN_DEV=1.
 *
 * Guardrails (docs/privacy/GUARDRAILS.md): every payload passes through scrubProps()
 * (lib/privacy.ts), and scripts/check_guardrails.py fails CI on a payload key or
 * argument that looks like personal data. With the `minors` pack on, nothing is sent
 * until the age gate (lib/age.ts) has confirmed an adult, and never for a child.
 */
import * as SecureStore from "expo-secure-store";
import PostHog from "posthog-react-native";

import { packOn } from "./packs";
import { scrubProps } from "./privacy";

type Props = Record<string, string | number | boolean | null>;

const KEY = process.env.EXPO_PUBLIC_POSTHOG_API_KEY ?? "";
const HOST = process.env.EXPO_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";
const IN_DEV = process.env.EXPO_PUBLIC_ANALYTICS_IN_DEV === "1";
/** Where lib/age.ts keeps the age gate's outcome ("ofAge" | "underAge"). */
export const AGE_POLICY_KEY = "age_policy";
// The minors pack: nothing is collected until the age gate has an "of age" answer, and
// never for a child. Read synchronously at load, so no event slips out before it.
const AGE_GATED = packOn("minors");
let suppressed = AGE_GATED && storedAgeAnswer() !== "ofAge";

function storedAgeAnswer(): string | null {
  try {
    return SecureStore.getItem(AGE_POLICY_KEY);
  } catch {
    return null; // unreadable (web) reads as unanswered: collect nothing
  }
}

export const posthog: PostHog | null = KEY
  ? new PostHog(KEY, {
      host: HOST,
      disabled: __DEV__ && !IN_DEV,
      captureAppLifecycleEvents: true,
      defaultOptIn: !AGE_GATED,
      enableSessionReplay: false,
      sessionReplayConfig: { maskAllTextInputs: true, maskAllImages: true },
    })
  : null;

/**
 * Time a user action for `duration_ms`. Call it when the action starts and read it
 * when it ends. It lives here, not inline, because React's purity lint flags
 * `Date.now()` inside components.
 */
export function startTimer(): () => number {
  const started = Date.now();
  return () => Date.now() - started;
}

function capture(event: string, props: Props = {}): void {
  if (suppressed) return;
  try {
    posthog?.capture(event, scrubProps(props));
  } catch {
    // analytics must never crash the app
  }
}

export function identifyUser(userId: string): void {
  if (suppressed) return;
  try {
    posthog?.identify(userId);
  } catch {
    /* ignore */
  }
}

export function resetAnalytics(): void {
  try {
    posthog?.reset();
  } catch {
    /* ignore */
  }
}

export async function setAnalyticsOptIn(optIn: boolean): Promise<void> {
  try {
    if (optIn && suppressed) return; // an under-age user can't be opted back in
    if (optIn) await posthog?.optIn();
    else await posthog?.optOut();
  } catch {
    /* ignore */
  }
}

/**
 * Switch all analytics off (an under-age user, per the age gate in lib/age.ts) or lift
 * the switch. Turning it off also opts the SDK out, so its own automatic events stop and
 * the queue is dropped; lifting it never opts anyone in by itself.
 */
export async function setAnalyticsSuppressed(value: boolean): Promise<void> {
  suppressed = value;
  if (!value) return;
  try {
    await posthog?.optOut();
    posthog?.reset();
  } catch {
    /* ignore */
  }
}

export function analyticsSuppressed(): boolean {
  return suppressed;
}

export const analytics = {
  screenViewed: (screen: string, props: Props = {}) => capture("screen_viewed", { screen, ...props }),
  signInRequested: (method: "email_otp" | "apple" | "google") =>
    capture("sign_in_requested", { method }),
  /** The code email was (or wasn't) sent: the failure half of sign_in_requested. */
  signInCodeSent: (p: { success: boolean; error_code: string | null; duration_ms: number }) =>
    capture("sign_in_code_sent", p),
  signInCompleted: (p: { method: string; success: boolean; error_code: string | null; duration_ms: number }) =>
    capture("sign_in_completed", p),
  profileUpdated: (p: { success: boolean; error_code: string | null; duration_ms: number }) =>
    capture("profile_updated", p),
  apiFailed: (p: { path: string; status: number; duration_ms: number }) => capture("api_failed", p),
  analyticsOptChanged: (optIn: boolean) => capture("analytics_opt_changed", { opt_in: optIn }),
  themeChanged: (preference: "system" | "light" | "dark") => capture("theme_changed", { preference }),
  sheetOpened: (sheet: string) => capture("sheet_opened", { sheet }),
  accountDeleted: (p: { success: boolean; error_code: string | null; duration_ms: number }) =>
    capture("account_deleted", p),
  dataExported: (p: { success: boolean; error_code: string | null; duration_ms: number }) =>
    capture("data_exported", p),
  /** Push toggled on/off. `outcome`: enabled | disabled | denied | unsupported | error. */
  pushChanged: (p: { enabled: boolean; outcome: string; success: boolean; error_code: string | null; duration_ms: number }) =>
    capture("push_changed", p),
  /** A notification tap opened the app. `route` is the internal path (never the payload text). */
  pushOpened: (route: string) => capture("push_opened", { route }),
  deepLinkOpened: (p: { route: string; matched: boolean }) => capture("deep_link_opened", p),
  updatePrompted: () => capture("update_prompted"),
  updateRestarted: () => capture("update_restarted"),
  errorReferenceCopied: () => capture("error_reference_copied"),
};
