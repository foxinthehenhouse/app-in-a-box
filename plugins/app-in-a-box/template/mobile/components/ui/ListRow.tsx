/**
 * ListRow: one composite, labelled element (screen readers read the row once,
 * not five fragments). Leading icon/avatar, title, subtitle, trailing value,
 * chevron when it navigates, or any trailing control (a Switch).
 */
import type { ReactNode } from "react";
import { View } from "react-native";
import type { AndroidSymbol, SFSymbol } from "expo-symbols";

import { makeStyles } from "../../lib/theme";
import { Icon } from "./Icon";
import { PressableScale } from "./PressableScale";
import { Text } from "./Text";

export interface ListRowProps {
  title: string;
  subtitle?: string;
  value?: string;
  icon?: { sf: SFSymbol; md: AndroidSymbol };
  leading?: ReactNode;
  /** A control on the right (e.g. <Switch>). The row is then not pressable. */
  trailing?: ReactNode;
  onPress?: () => void;
  /** Defaults to "title, value". */
  accessibilityLabel?: string;
  testID?: string;
}

export function ListRow({ title, subtitle, value, icon, leading, trailing, onPress, accessibilityLabel, testID }: ListRowProps) {
  const s = useStyles();
  const label = accessibilityLabel ?? [title, value, subtitle].filter(Boolean).join(", ");
  const content = (
    <>
      {leading ?? (icon ? <View style={s.iconWell}><Icon sf={icon.sf} md={icon.md} size={18} color="accent" /></View> : null)}
      <View style={s.text}>
        <Text variant="body" numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text variant="secondary" numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {value ? (
        <Text variant="secondary" numberOfLines={1} style={s.value}>
          {value}
        </Text>
      ) : null}
      {trailing}
      {onPress && !trailing ? <Icon sf="chevron.right" md="chevron_right" size={14} color="inkFaint" /> : null}
    </>
  );
  if (onPress && !trailing) {
    return (
      <PressableScale onPress={onPress} accessibilityRole="button" accessibilityLabel={label} testID={testID} style={s.row}>
        {content}
      </PressableScale>
    );
  }
  return (
    <View style={s.row} testID={testID} accessible={!trailing} accessibilityLabel={trailing ? undefined : label}>
      {content}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  row: {
    minHeight: t.minTapTarget + t.space.sm,
    flexDirection: "row",
    alignItems: "center",
    gap: t.space.md,
    paddingVertical: t.space.sm,
    borderRadius: t.radius.md,
    overflow: "hidden",
  },
  iconWell: {
    width: 32,
    height: 32,
    borderRadius: t.radius.sm,
    backgroundColor: t.color.control,
    alignItems: "center",
    justifyContent: "center",
  },
  text: { flex: 1, gap: 2 },
  value: { maxWidth: "45%" },
}));
