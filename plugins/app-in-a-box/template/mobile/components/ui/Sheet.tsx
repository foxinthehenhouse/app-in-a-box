/**
 * Sheet pattern: sheets are Expo Router routes presented as a native formSheet
 * (see app/_layout.tsx and app/edit-name.tsx), not a JS bottom-sheet library.
 * Native sheets get the system grabber, detents, swipe-to-dismiss, VoiceOver
 * modality and Liquid Glass for free.
 *
 * Rules learned the hard way:
 * - Register sheet routes ONCE, on the root Stack. Registering one inside the
 *   tabs too lets "back" pop the previous TAB instead of closing the sheet.
 * - Close with `closeSheet()` below (dismiss, falling back to back), and always
 *   give the sheet a visible Close button: swipe-down isn't discoverable.
 * - Toasts render under a native sheet on iOS: close the sheet, then toast.
 */
import { router } from "expo-router";
import { View } from "react-native";

import { useT } from "../../lib/i18n";
import { makeStyles } from "../../lib/theme";
import { IconButton } from "./Button";
import { Text } from "./Text";

export function closeSheet(): void {
  if (router.canDismiss()) router.dismiss();
  else if (router.canGoBack()) router.back();
}

export function SheetHeader({ title, onClose = closeSheet, testID }: { title: string; onClose?: () => void; testID?: string }) {
  const s = useStyles();
  const t = useT();
  return (
    <View style={s.header}>
      <Text variant="heading" style={s.title}>
        {title}
      </Text>
      <IconButton sf="xmark" md="close" accessibilityLabel={t("common.close")} onPress={onClose} tone="filled" testID={testID} />
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  header: { flexDirection: "row", alignItems: "center", gap: t.space.md },
  title: { flex: 1 },
}));
