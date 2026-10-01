/**
 * Signed-in tabs: NATIVE tabs (UITabBarController on iOS, with Liquid Glass on
 * iOS 26; Material 3 bottom navigation on Android; a tab list on web).
 * Icons: SF Symbols on iOS (`sf`), Material Symbols on Android (`md`).
 * Keep it to 2-4 tabs. Sheets are NOT registered here (see app/_layout.tsx).
 */
import { NativeTabs } from "expo-router/unstable-native-tabs";

import { useT } from "../../lib/i18n";
import { useTheme } from "../../lib/theme";

export default function AppTabs() {
  const t = useTheme();
  const tr = useT();
  return (
    <NativeTabs tintColor={t.color.accent} iconColor={t.color.inkFaint} indicatorColor={t.color.control}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Icon sf={{ default: "house", selected: "house.fill" }} md="home" />
        <NativeTabs.Trigger.Label>{tr("tabs.home")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="settings">
        <NativeTabs.Trigger.Icon sf={{ default: "gearshape", selected: "gearshape.fill" }} md="settings" />
        <NativeTabs.Trigger.Label>{tr("tabs.settings")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
