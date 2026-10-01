/**
 * Signed-in tabs on WEB. The native layout (_layout.tsx) uses NativeTabs, whose web
 * fallback floats a pill over the top of every screen and covers its title. Web
 * gets expo-router's headless tabs instead: the screen fills the page and a themed
 * bottom bar sits under it, like the app on a phone. Keep the triggers in step with
 * _layout.tsx (same routes, same labels).
 */
import { type ReactNode } from "react";
import { TabList, TabSlot, TabTrigger, Tabs, type TabTriggerSlotProps } from "expo-router/ui";
import type { AndroidSymbol } from "expo-symbols";

import { Icon, PressableScale, Text } from "../../components/ui";
import { useT } from "../../lib/i18n";
import { makeStyles } from "../../lib/theme";

export default function AppTabsWeb() {
  const s = useStyles();
  const tr = useT();
  return (
    <Tabs style={s.fill}>
      <TabSlot style={s.fill} />
      <TabList style={s.bar}>
        <TabTrigger name="index" href="/" asChild>
          <TabButton icon="home" label={tr("tabs.home")} testID="tab-home" />
        </TabTrigger>
        <TabTrigger name="settings" href="/settings" asChild>
          <TabButton icon="settings" label={tr("tabs.settings")} testID="tab-settings" />
        </TabTrigger>
      </TabList>
    </Tabs>
  );
}

interface TabButtonProps extends TabTriggerSlotProps {
  icon: AndroidSymbol;
  label: string;
  testID?: string;
}

function TabButton({ icon, label, isFocused = false, onPress, testID }: TabButtonProps): ReactNode {
  const s = useStyles();
  return (
    <PressableScale
      onPress={onPress ?? undefined}
      haptic="selection"
      pressTint={false}
      accessibilityRole="tab"
      accessibilityLabel={label}
      accessibilityState={{ selected: isFocused }}
      testID={testID}
      style={s.tab}
    >
      <Icon sf="circle" md={icon} size={22} color={isFocused ? "accent" : "inkFaint"} />
      <Text variant="meta" tone={isFocused ? "default" : "dim"}>
        {label}
      </Text>
    </PressableScale>
  );
}

const useStyles = makeStyles((t) => ({
  fill: { flex: 1 },
  bar: {
    flexDirection: "row",
    justifyContent: "space-around",
    borderTopWidth: 1,
    borderTopColor: t.color.border,
    backgroundColor: t.color.surface,
    paddingVertical: t.space.xs,
  },
  tab: {
    flex: 1,
    minHeight: t.minTapTarget,
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
  },
}));
