/**
 * The age gate's policy (the `minors` guardrail pack, docs/privacy/GUARDRAILS.md).
 *
 * With the pack on, the app asks for a birth month and year before anything else
 * (components/ui/AgeGate.tsx, mounted on the sign-in screen) and keeps ONLY the outcome
 * on the device: of age, or under age. Never the birth date. Until an answer exists,
 * and forever for an under-age user, analytics is off (lib/analytics.ts). The answer
 * is kept so a child can't go back and pick an older year: the FTC's guidance for a
 * neutral age screen. Getting a parent's verifiable consent is a separate, owner-level
 * decision; the options are in docs/privacy/GUARDRAILS.md.
 *
 * With the pack off, nothing here runs: the status is "ofAge" without a read.
 */
import * as SecureStore from "expo-secure-store";

import { AGE_POLICY_KEY, setAnalyticsOptIn, setAnalyticsSuppressed } from "./analytics";
import { packOn } from "./packs";

/**
 * Under this age a user is treated as a child: COPPA's line in the US. ⚖️ A default,
 * not a ruling: the GDPR lets each EU country set 13 to 16 for consent to online
 * services, and the UK's Children's Code covers everyone under 18. Raise it to match
 * where the app ships.
 */
export const MIN_AGE = 13;

export type AgeStatus = "unknown" | "ofAge" | "underAge";

function storedStatus(): AgeStatus {
  try {
    const v = SecureStore.getItem(AGE_POLICY_KEY);
    return v === "ofAge" || v === "underAge" ? v : "unknown";
  } catch {
    return "unknown"; // unreadable reads as unanswered: ask, and collect nothing meanwhile
  }
}

// Read once, synchronously, so the sign-in screen knows on its first render. With the
// pack off there is no read at all.
let status: AgeStatus = packOn("minors") ? storedStatus() : "ofAge";

/** Whole years old on `today`, from a birth month (1-12) and year. */
export function ageFrom(birthYear: number, birthMonth: number, today: Date = new Date()): number {
  const months = (today.getFullYear() - birthYear) * 12 + (today.getMonth() + 1 - birthMonth);
  return Math.floor(months / 12);
}

/** A birth month and year a person could have: month 1-12, not in the future, under 120. */
export function validBirth(birthYear: number, birthMonth: number, today: Date = new Date()): boolean {
  if (!Number.isInteger(birthYear) || !Number.isInteger(birthMonth)) return false;
  if (birthMonth < 1 || birthMonth > 12) return false;
  const age = ageFrom(birthYear, birthMonth, today);
  return age >= 0 && age < 120;
}

export function currentAgeStatus(): AgeStatus {
  return status;
}

/**
 * Record the age screen's answer: keep the outcome, drop the date. An adult is opted in
 * to analytics once, here (Settings can opt out later); a child is switched off for good.
 */
export async function recordAge(birthYear: number, birthMonth: number, today: Date = new Date()): Promise<AgeStatus> {
  status = ageFrom(birthYear, birthMonth, today) < MIN_AGE ? "underAge" : "ofAge";
  try {
    await SecureStore.setItemAsync(AGE_POLICY_KEY, status);
  } catch {
    /* the answer still applies for this session */
  }
  await setAnalyticsSuppressed(status !== "ofAge");
  if (status === "ofAge") await setAnalyticsOptIn(true);
  return status;
}
