/**
 * Crash + error monitoring (Sentry). No-op without EXPO_PUBLIC_SENTRY_DSN or in
 * dev builds. Privacy defaults: no PII, no screenshots, no view hierarchy, and every
 * event passes through scrubSentryEvent() (lib/privacy.ts): no user, no request, no
 * sensitive key in tags, extra, contexts or breadcrumbs.
 *
 * Every event says which JS it came from (`releaseInfo()`). An OTA update swaps the
 * bundle under the same store build, so the build number alone can't tell a crash in
 * yesterday's update from one in the JS the build shipped with:
 * - release: `<app id>@<version>+<build>` on the build's own bundle (the name Sentry's
 *   native SDK picks, so EAS Build's source maps and native crashes line up), and
 *   `<app id>@<version>+<update id>` while an OTA update runs. One release per update
 *   gives each its own crash-free sessions, which the staged rollout's promote step
 *   reads (docs/runbooks/release.md).
 * - dist: the build number, as Sentry's native SDK sets it.
 * - tags: the update id and group, runtime version, channel, and whether the embedded
 *   bundle is running (the tags docs.expo.dev/guides/using-sentry recommends).
 * The update's own source maps are uploaded by the EAS workflows' update jobs
 * (`upload_sentry_sourcemaps: true`).
 */
import * as Sentry from "@sentry/react-native";
import * as Application from "expo-application";
import * as Updates from "expo-updates";

import { isSensitiveKey, scrubSentryEvent } from "./privacy";

const DSN = process.env.EXPO_PUBLIC_SENTRY_DSN ?? "";

export interface ReleaseInfo {
  release?: string;
  dist?: string;
  tags: Record<string, string>;
}

/** The update group id, from the running manifest's metadata (EAS Update sets it). */
function updateGroupId(): string | undefined {
  const manifest: unknown = Updates.manifest;
  if (!manifest || typeof manifest !== "object" || !("metadata" in manifest)) return undefined;
  const metadata: unknown = manifest.metadata;
  if (!metadata || typeof metadata !== "object" || !("updateGroup" in metadata)) return undefined;
  return typeof metadata.updateGroup === "string" ? metadata.updateGroup : undefined;
}

/**
 * Sentry's release, dist and update tags for the running JS. A value the platform
 * doesn't report (web, Expo Go, updates off) is left out, never made up: without a
 * release Sentry falls back to its native default.
 */
export function releaseInfo(): ReleaseInfo {
  const appId = Application.applicationId;
  const version = Application.nativeApplicationVersion;
  const build = Application.nativeBuildVersion;
  const ota = !Updates.isEmbeddedLaunch && Updates.updateId ? Updates.updateId : null;

  const tags: Record<string, string> = { "expo-is-embedded-update": String(Updates.isEmbeddedLaunch) };
  if (Updates.updateId) tags["expo-update-id"] = Updates.updateId;
  const group = updateGroupId();
  if (group) tags["expo-update-group-id"] = group;
  if (Updates.runtimeVersion) tags["expo-runtime-version"] = Updates.runtimeVersion;
  if (Updates.channel) tags["expo-channel"] = Updates.channel;

  const suffix = ota ?? build;
  return {
    release: appId && version && suffix ? `${appId}@${version}+${suffix}` : undefined,
    dist: build ?? undefined,
    tags,
  };
}

export function initMonitoring(): void {
  if (!DSN || __DEV__) return;
  const { release, dist, tags } = releaseInfo();
  Sentry.init({
    dsn: DSN,
    ...(release ? { release } : null),
    ...(dist ? { dist } : null),
    initialScope: { tags },
    sendDefaultPii: false,
    attachScreenshot: false,
    attachViewHierarchy: false,
    tracesSampleRate: 0,
    beforeSend: scrubSentryEvent,
  });
}

export function reportError(error: unknown, context: Record<string, string> = {}): void {
  if (!DSN || __DEV__) return;
  Sentry.withScope((scope) => {
    for (const [k, v] of Object.entries(context)) if (!isSensitiveKey(k)) scope.setTag(k, v);
    Sentry.captureException(error);
  });
}

export const wrapRoot = Sentry.wrap;
