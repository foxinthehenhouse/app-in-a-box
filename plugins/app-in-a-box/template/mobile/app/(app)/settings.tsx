import { useEffect, useState } from "react";
import { router } from "expo-router";
import Constants from "expo-constants";

import { Button, Card, ListRow, Meta, Screen, Section, SegmentedControl, Skeleton, Title, Toggle, useToast } from "../../components/ui";
import { analytics, setAnalyticsOptIn } from "../../lib/analytics";
import { APP } from "../../lib/app";
import { downloadMyData } from "../../lib/export";
import { useT } from "../../lib/i18n";
import { usePushSetting } from "../../lib/push";
import { useMe } from "../../lib/query";
import { signOut } from "../../lib/session";
import { canSwitchScheme, useThemePreference, type ThemePreference } from "../../lib/theme";
import { useLoaded } from "../../lib/use-load";

export default function Settings() {
  const t = useT();
  const toast = useToast();
  const me = useLoaded(useMe());
  const push = usePushSetting();
  const { preference, setPreference } = useThemePreference();
  const [optIn, setOptIn] = useState(true);
  const [exporting, setExporting] = useState(false);

  const appearance: readonly { value: ThemePreference; label: string }[] = [
    { value: "system", label: t("settings.system") },
    { value: "light", label: t("settings.light") },
    { value: "dark", label: t("settings.dark") },
  ];

  useEffect(() => {
    analytics.screenViewed("settings");
  }, []);

  async function toggleAnalytics(next: boolean) {
    analytics.analyticsOptChanged(next);
    setOptIn(next);
    await setAnalyticsOptIn(next);
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
  const pushSubtitle =
    push.status === "unsupported"
      ? t("settings.pushUnsupported")
      : push.status === "denied"
        ? t("settings.pushDenied")
        : t("settings.pushSubtitle");

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
                disabled={push.busy || push.status === null || push.status === "unsupported"}
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
                value={optIn}
                onValueChange={toggleAnalytics}
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
