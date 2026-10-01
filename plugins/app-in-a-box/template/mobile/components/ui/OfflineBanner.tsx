/**
 * OfflineBanner: a calm, non-blocking "you're offline" strip, driven by TanStack
 * Query's onlineManager (NetInfo, wired in lib/query.ts). Mounted once in
 * app/_layout.tsx. It never blocks taps (pointerEvents none): offline, screens
 * still show cached data and edits queue, so the app stays usable.
 *
 * Announced once when it appears; icon + text, never colour alone.
 */
import { useEffect } from "react";
import { AccessibilityInfo, StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { fadeIn, fadeOut } from "../../lib/motion";
import { useT } from "../../lib/i18n";
import { useOnline } from "../../lib/query";
import { makeStyles } from "../../lib/theme";
import { Icon } from "./Icon";
import { Text } from "./Text";

export function OfflineBanner({ online: forced }: { online?: boolean }) {
  const live = useOnline();
  const online = forced ?? live;
  const t = useT();
  const s = useStyles();
  const insets = useSafeAreaInsets();
  const message = t("offline.banner");

  useEffect(() => {
    if (!online) AccessibilityInfo.announceForAccessibility(message);
  }, [online, message]);

  if (online) return null;
  return (
    <View pointerEvents="none" style={[s.host, { top: insets.top + 4 }]} testID="offline-banner-host">
      <Animated.View
        entering={fadeIn}
        exiting={fadeOut}
        style={s.banner}
        accessible
        accessibilityRole="alert"
        accessibilityLabel={message}
        testID="offline-banner"
      >
        <Icon sf="wifi.slash" md="wifi_off" size={16} color="warning" />
        <Text variant="secondary" style={s.text} numberOfLines={2}>
          {message}
        </Text>
      </Animated.View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  host: { position: "absolute", left: t.space.md, right: t.space.md, zIndex: 900, alignItems: "center" },
  banner: {
    flexDirection: "row",
    alignItems: "center",
    gap: t.space.sm,
    paddingHorizontal: t.space.md,
    paddingVertical: t.space.sm,
    borderRadius: t.radius.pill,
    backgroundColor: t.color.surfaceRaised,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.color.border,
    ...t.elevation.raised,
  },
  text: { flexShrink: 1 },
}));
