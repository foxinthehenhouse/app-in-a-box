/**
 * Button and IconButton. 48px minimum, a purpose label, press feedback and a
 * haptic graded by commitment: primary = "medium" (an earned action), the rest
 * "light". While `loading`, the button is busy + disabled so a mutation can't
 * double-fire.
 */
import { ActivityIndicator, StyleSheet, View } from "react-native";
import type { AndroidSymbol, SFSymbol } from "expo-symbols";

import { makeStyles, useTheme, type Palette } from "../../lib/theme";
import { Icon } from "./Icon";
import { PressableScale } from "./PressableScale";
import { Text } from "./Text";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps {
  label: string;
  onPress: () => void;
  /** Defaults to `label`. State the purpose: "Save profile", not "Save button". */
  accessibilityLabel?: string;
  variant?: ButtonVariant;
  icon?: { sf: SFSymbol; md: AndroidSymbol };
  loading?: boolean;
  disabled?: boolean;
  /** Full width (default) or hug the label. */
  block?: boolean;
  testID?: string;
}

const INK: Record<ButtonVariant, keyof Palette> = {
  primary: "onAccent",
  secondary: "ink",
  ghost: "accent",
  danger: "danger",
};

export function Button({
  label,
  onPress,
  accessibilityLabel,
  variant = "primary",
  icon,
  loading = false,
  disabled = false,
  block = true,
  testID,
}: ButtonProps) {
  const t = useTheme();
  const s = useStyles();
  const inactive = disabled || loading;
  const ink = INK[variant];
  return (
    <PressableScale
      onPress={onPress}
      disabled={inactive}
      haptic={variant === "primary" ? "medium" : "light"}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: inactive, busy: loading }}
      testID={testID}
      style={[s.base, s[variant], block ? null : s.hug, inactive ? s.inactive : null]}
    >
      {loading ? (
        <ActivityIndicator color={t.color[ink]} accessibilityElementsHidden />
      ) : (
        <View style={s.row}>
          {icon ? <Icon sf={icon.sf} md={icon.md} size={18} color={ink} /> : null}
          <Text variant="body" style={[s.label, { color: t.color[ink] }]} numberOfLines={1}>
            {label}
          </Text>
        </View>
      )}
    </PressableScale>
  );
}

export interface IconButtonProps {
  sf: SFSymbol;
  md: AndroidSymbol;
  /** Required: an icon has no text for a screen reader to read. */
  accessibilityLabel: string;
  onPress: () => void;
  tone?: "plain" | "filled";
  disabled?: boolean;
  testID?: string;
}

export function IconButton({ sf, md, accessibilityLabel, onPress, tone = "plain", disabled, testID }: IconButtonProps) {
  const s = useStyles();
  return (
    <PressableScale
      onPress={onPress}
      disabled={disabled}
      haptic="light"
      scaleTo={0.9}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ disabled: !!disabled }}
      hitSlop={4}
      testID={testID}
      style={[s.icon, tone === "filled" ? s.iconFilled : null, disabled ? s.inactive : null]}
    >
      <Icon sf={sf} md={md} size={20} color={tone === "filled" ? "ink" : "inkDim"} />
    </PressableScale>
  );
}

const useStyles = makeStyles((t) => ({
  base: {
    minHeight: t.minTapTarget,
    borderRadius: t.radius.md,
    paddingHorizontal: t.space.lg,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  hug: { alignSelf: "flex-start" },
  row: { flexDirection: "row", alignItems: "center", gap: t.space.sm },
  label: { fontWeight: "600" },
  primary: { backgroundColor: t.color.accent },
  secondary: {
    backgroundColor: t.color.control,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.color.border,
  },
  ghost: { backgroundColor: "transparent" },
  danger: {
    backgroundColor: "transparent",
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.color.danger,
  },
  inactive: { opacity: t.opacity.disabled },
  icon: {
    width: t.minTapTarget,
    height: t.minTapTarget,
    borderRadius: t.radius.pill,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  iconFilled: { backgroundColor: t.color.control },
}));
