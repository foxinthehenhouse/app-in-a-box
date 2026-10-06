import { useCallback, useEffect, useState } from "react";
import { router, useFocusEffect } from "expo-router";
import Constants from "expo-constants";

import { Button, Card, ListRow, Meta, Screen, Section, SegmentedControl, Skeleton, Title, Toggle, useToast } from "../../components/ui";
import { analytics } from "../../lib/analytics";
import { changeAnalyticsOptIn, readAnalyticsOptIn } from "../../lib/analytics-optin";
import { APP } from "../../lib/app";
import { downloadMyData } from "../../lib/export";
import { useFlag } from "../../lib/flags";
import { useT } from "../../lib/i18n";
import { type PushStatus, usePushSetting } from "../../lib/push";
import { useMe } from "../../lib/query";
import { signOut } from "../../lib/session";
import { canSwitchScheme, useThemePreference, type ThemePreference } from "../../lib/theme";
import { useLoaded } from "../../lib/use-load";

// Why the push row can't simply be switched on, most specific first.
function pushSubtitleKey(paused: boolean, status: PushStatus | null) {
  if (paused) return "settings.pushPaused";
  if (status === "unsupported") return "settings.pushUnsupported";
  if (status === "denied") return "settings.pushDenied";
  return "settings.pushSubtitle";
}

export default function Settings() {
  const t = useT();
  const toast = useToast();
  // states: a settings list always has rows. The profile row shows a skeleton while it loads and
  // "Not set" if the load fails or is empty; pull to refresh retries. Every other row is local.
  const me = useLoaded(useMe());
  const push = usePushSetting();
  // The kill-push kill switch (lib/flags.ts): the API has stopped sending, so say so.
  const pushPaused = useFlag("kill-push");
  const { preference, setPreference } = useThemePreference();
  // null until the SDK's persisted choice has been read; the toggle is disabled until then.
  const [optIn, setOptIn] = useState<boolean | null>(null);
  const [exporting, setExporting] = useState(false);

  const appearance: readonly { value: ThemePreference; label: string }[] = [
    { value: "system", label: t("settings.system") },
    { value: "light", label: t("settings.light") },
    { value: "dark", label: t("settings.dark") },
  ];

  // On focus, not on mount: native tabs mount every tab at launch (see index.tsx).
  useFocusEffect(
    useCallback(() => {
      analytics.screenViewed("settings");
    }, []),
  );

  useEffect(() => {
    let alive = true;
    readAnalyticsOptIn().then((v) => alive && setOptIn(v));
    return () => {
      alive = false;
    };
  }, []);

  async function toggleAnalytics(next: boolean) {
    setOptIn(next);
    await changeAnalyticsOptIn(next); // orders the capture around the SDK flag so it isn't dropped
    toast.info(next ? t("settings.analyticsOn") : t("settings.analyticsOff"));
  }

  async function togglePush(next: boolean) {
    const outcome = await push.setEnabled(next);
    if (outcome === "enabled") toast.success(t("settings.pushOn"));
    else if (outcome === "disabled") toast.info(t("settings.pushOff"));
    else if (outcome === "denied") toast.error(t("settings.pushDenied"));
    else if (outcome === "unsupported") toast.info(t("settings.pushUnsupported"));
    else toast.error(t("settings.pushFailed"));
  }

  async function exportData() {
    setExporting(true);
    try {
      await downloadMyData(APP.slug);
      toast.success(t("settings.exportReady"));
    } catch {
      toast.error(t("settings.exportFailed"));
    } finally {
      setExporting(false);
    }
  }

  function changeTheme(next: ThemePreference) {
    analytics.themeChanged(next);
    setPreference(next);
  }

  const displayName = me.data?.displayName || t("common.notSet");
  const pushSubtitle = t(pushSubtitleKey(pushPaused, push.status));
  const pushLocked = pushPaused || push.busy || push.status === null || push.status === "unsupported";

  return (
    <Screen testID="settings-screen" refreshing={me.refreshing} onRefresh={me.refresh}>
      <Title>{t("settings.title")}</Title>

      <Section title={t("settings.profile")}>
        <Card>
          {me.loading ? (
            <Skeleton height={20} width="60%" />
          ) : (
            <ListRow
              title={t("settings.displayName")}
              value={displayName}
              icon={{ sf: "person.crop.circle", md: "account_circle" }}
              onPress={() => router.push("/edit-name")}
              accessibilityLabel={t("settings.editNameLabel", { name: displayName })}
              testID="settings-name-row"
            />
          )}
        </Card>
      </Section>

      {canSwitchScheme ? (
        <Section title={t("settings.appearance")}>
          <SegmentedControl
            options={appearance}
            value={preference}
            onChange={changeTheme}
            accessibilityLabel={t("settings.appearance")}
            testID="settings-appearance"
          />
        </Section>
      ) : null}

      <Section title={t("settings.notifications")}>
        <Card>
          <ListRow
            title={t("settings.push")}
            subtitle={pushSubtitle}
            trailing={
              <Toggle
                value={push.status === "enabled"}
                onValueChange={togglePush}
                disabled={pushLocked}
                accessibilityLabel={t("settings.push")}
                testID="settings-push-switch"
              />
            }
          />
        </Card>
      </Section>

      <Section title={t("settings.privacy")}>
        <Card>
          <ListRow
            title={t("settings.analytics")}
            subtitle={t("settings.analyticsSubtitle")}
            trailing={
              <Toggle
                value={optIn ?? true}
                onValueChange={toggleAnalytics}
                disabled={optIn === null}
                accessibilityLabel={t("settings.analytics")}
                testID="settings-analytics-switch"
              />
            }
          />
          <ListRow
            title={t("settings.export")}
            subtitle={exporting ? t("settings.exportPreparing") : t("settings.exportSubtitle")}
            icon={{ sf: "square.and.arrow.down", md: "download" }}
            // Busy: the row stops being a button (no double export) and says so.
            onPress={exporting ? undefined : exportData}
            testID="settings-export-row"
          />
        </Card>
      </Section>

      <Section title={t("settings.account")}>
        <Card>
          <ListRow
            title={t("settings.deleteAccount")}
            subtitle={t("settings.deleteAccountSubtitle")}
            icon={{ sf: "trash", md: "delete" }}
            onPress={() => router.push("/delete-account")}
            testID="settings-delete-account-row"
          />
        </Card>
      </Section>

      {__DEV__ ? (
        <Section title={t("settings.developer")}>
          <Card>
            <ListRow
              title={t("settings.gallery")}
              subtitle={t("settings.gallerySubtitle")}
              icon={{ sf: "square.grid.2x2", md: "grid_view" }}
              onPress={() => router.push("/gallery")}
              testID="settings-gallery-row"
            />
          </Card>
        </Section>
      ) : null}

      <Button label={t("settings.signOut")} variant="danger" onPress={signOut} testID="settings-signout-button" />
      <Meta>{t("settings.version", { version: Constants.expoConfig?.version ?? "0" })}</Meta>
    </Screen>
  );
}
