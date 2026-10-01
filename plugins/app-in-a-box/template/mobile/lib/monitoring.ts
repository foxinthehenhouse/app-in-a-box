/**
 * Crash + error monitoring (Sentry). No-op without EXPO_PUBLIC_SENTRY_DSN or in
 * dev builds. Privacy defaults: no PII, no screenshots, no view hierarchy.
 */
import * as Sentry from "@sentry/react-native";

const DSN = process.env.EXPO_PUBLIC_SENTRY_DSN ?? "";

export function initMonitoring(): void {
  if (!DSN || __DEV__) return;
  Sentry.init({
    dsn: DSN,
    sendDefaultPii: false,
    attachScreenshot: false,
    attachViewHierarchy: false,
    tracesSampleRate: 0,
  });
}

export function reportError(error: unknown, context: Record<string, string> = {}): void {
  if (!DSN || __DEV__) return;
  Sentry.withScope((scope) => {
    for (const [k, v] of Object.entries(context)) scope.setTag(k, v);
    Sentry.captureException(error);
  });
}

export const wrapRoot = Sentry.wrap;
