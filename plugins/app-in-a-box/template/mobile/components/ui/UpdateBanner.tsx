/**
 * UpdateBanner: "An update is ready · Restart / Later", shown when an OTA update
 * has downloaded (lib/updates.ts `useUpdatePrompt`). Mounted once in
 * app/_layout.tsx. Never forces a restart mid-task: Later hides it until the next
 * launch, which applies the update anyway.
 */
import { StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { entrance, useReducedMotion } from "../../lib/motion";
import { useT } from "../../lib/i18n";
import { makeStyles } from "../../lib/theme";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { Text } from "./Text";

export interface UpdateBannerProps {
  visible: boolean;
  onRestart: () => void;
  onLater: () => void;
}

export function UpdateBanner({ visible, onRestart, onLater }: UpdateBannerProps) {
  const t = useT();
  const s = useStyles();
  const reduced = useReducedMotion();
  const insets = useSafeAreaInsets();
  if (!visible) return null;
  return (
    <View pointerEvents="box-none" style={[s.host, { bottom: insets.bottom + 72 }]}>
      <Animated.View entering={entrance(0, reduced)} style={s.card} accessibilityRole="alert" testID="update-banner">
        <View style={s.row}>
          <Icon sf="arrow.down.circle.fill" md="system_update" size={22} color="accent" />
          <View style={s.text}>
            <Text variant="body">{t("update.title")}</Text>
            <Text variant="secondary">{t("update.body")}</Text>
          </View>
        </View>
        <View style={s.row}>
          <View style={s.flex}>
            <Button label={t("update.later")} variant="ghost" onPress={onLater} testID="update-later-button" />
          </View>
          <View style={s.flex}>
            <Button
              label={t("update.restart")}
              accessibilityLabel={t("update.restartLabel")}
              onPress={onRestart}
              testID="update-restart-button"
            />
          </View>
        </View>
      </Animated.View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  host: { position: "absolute", left: t.space.md, right: t.space.md, zIndex: 950 },
  card: {
    gap: t.space.md,
    padding: t.space.md,
    borderRadius: t.radius.lg,
    backgroundColor: t.color.surfaceRaised,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.color.border,
    ...t.elevation.overlay,
  },
  row: { flexDirection: "row", alignItems: "center", gap: t.space.sm },
  text: { flex: 1, gap: t.space.xs },
  flex: { flex: 1 },
}));
