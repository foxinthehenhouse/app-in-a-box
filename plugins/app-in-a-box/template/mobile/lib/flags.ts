/**
 * Typed feature flags and kill switches, on PostHog. This is the ONLY place flags are
 * defined; read one with `flag("name")` or, in a component, `useFlag("name")`.
 *
 * - Every flag has a safe `default`. The PostHog client is bootstrapped with them
 *   (lib/analytics.ts), so the first render already has an answer, and with no
 *   PostHog key (dev, demo, an app without analytics) every flag simply IS its default.
 * - Every flag has an `owner` and an `expires` date. `scripts/check_flags.py` fails CI
 *   without them, and the `next` skill surfaces flags past their date: remove the flag
 *   then, or extend it (at most a year out).
 * - Kill switches are named `kill-<feature>` and default to `false`. Turning the
 *   PostHog flag ON turns the feature OFF; a flag that is missing, deleted or
 *   unreachable leaves the feature running.
 *
 * The API reads the same PostHog flags (backend/flags.py): keep a flag both sides read
 * identical in both registries (the guard checks the default and kill-switch match).
 */
import { useEffect, useState } from "react";

import type * as AnalyticsModule from "./analytics";

export interface FlagSpec {
  /** What every user gets until PostHog answers, and forever without a key. */
  default: boolean | string;
  /** Who decides when it goes. */
  owner: `@${string}`;
  /** YYYY-MM-DD: remove the flag by then, or extend it. */
  expires: `${number}-${number}-${number}`;
  /** A kill switch: on = feature off. Named `kill-*`, default false. */
  killSwitch?: true;
  description: string;
}

export const FLAGS = {
  "kill-push": {
    default: false,
    owner: "@__OWNER__",
    expires: "2027-09-30",
    killSwitch: true,
    description: "Pauses the notifications toggle while the API stops sending (backend/flags.py).",
  },
} as const satisfies Record<string, FlagSpec>;

export type FlagName = keyof typeof FLAGS;
export type FlagValue<K extends FlagName> = (typeof FLAGS)[K]["default"] extends boolean ? boolean : string;

/** The defaults, in the shape PostHog's `bootstrap.featureFlags` takes. */
export function flagDefaults(): Record<string, boolean | string> {
  return Object.fromEntries(Object.entries(FLAGS).map(([name, spec]) => [name, spec.default]));
}

/**
 * The PostHog client, required lazily: lib/analytics.ts imports flagDefaults() from
 * here to bootstrap the client, so a static import back would be a cycle.
 */
function client(): (typeof AnalyticsModule)["posthog"] {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy, breaks an import cycle (see above)
    return (require("./analytics") as typeof AnalyticsModule).posthog;
  } catch {
    return null;
  }
}

/** A PostHog answer in the flag's own type; anything else falls back to the default. */
function coerce<K extends FlagName>(name: K, raw: unknown): FlagValue<K> {
  const fallback = FLAGS[name].default;
  if (typeof fallback === "boolean") {
    if (typeof raw === "boolean") return raw as FlagValue<K>;
    // A multivariate flag answering with a variant counts as on.
    if (typeof raw === "string" && raw !== "") return true as FlagValue<K>;
    return fallback as FlagValue<K>;
  }
  return (typeof raw === "string" && raw !== "" ? raw : fallback) as FlagValue<K>;
}

/** The flag's current value: PostHog's when it has one, else the default. Never throws. */
export function flag<K extends FlagName>(name: K): FlagValue<K> {
  let raw: unknown;
  try {
    raw = client()?.getFeatureFlag(name);
  } catch {
    raw = undefined; // flags must never crash the app
  }
  return coerce(name, raw);
}

/** `flag()` that re-renders when PostHog loads new flag values. */
export function useFlag<K extends FlagName>(name: K): FlagValue<K> {
  const [value, setValue] = useState(() => flag(name));
  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    try {
      unsubscribe = client()?.onFeatureFlags(() => setValue(flag(name)));
    } catch {
      unsubscribe = undefined;
    }
    return () => unsubscribe?.();
  }, [name]);
  return value;
}
