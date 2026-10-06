/**
 * Signed-in tabs: NATIVE tabs (UITabBarController on iOS, with Liquid Glass on
 * iOS 26; Material 3 bottom navigation on Android; a tab list on web).
 * Icons: SF Symbols on iOS (`sf`), Material Symbols on Android (`md`).
 * Keep it to 2-4 tabs. Sheets are NOT registered here (see app/_layout.tsx).
 * The bar is Liquid Glass only when the theme chose glass surfaces and the phone
 * allows it (`useGlassChrome`); otherwise it is solid `surface`, the prototype's
 * "solid" choice, on every platform.
 */
import { NativeTabs } from "expo-router/unstable-native-tabs";

import { useGlassChrome } from "../../lib/atmosphere";
import { useT } from "../../lib/i18n";
import { useTheme } from "../../lib/theme";

export default function AppTabs() {
  const t = useTheme();
  const tr = useT();
  const glass = useGlassChrome();
  return (
    <NativeTabs
      tintColor={t.color.accent}
      iconColor={t.color.inkFaint}
      indicatorColor={t.color.control}
      backgroundColor={glass ? undefined : t.color.surface}
      blurEffect={glass ? undefined : "none"}
      disableTransparentOnScrollEdge={!glass}
    >
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
