/**
 * Small status and identity pieces: EmptyState, Badge, Avatar, ProgressBar.
 */
import type { ReactNode } from "react";
import { useEffect } from "react";
import { Image, View } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue } from "react-native-reanimated";
import type { AndroidSymbol, SFSymbol } from "expo-symbols";

import { useT } from "../../lib/i18n";
import { animateTo, entrance, useReducedMotion } from "../../lib/motion";
import { makeStyles, useTheme, type Palette } from "../../lib/theme";
import { Icon } from "./Icon";
import { Text } from "./Text";

/** An honest empty state: what's missing, why it matters, and the one next step. */
export function EmptyState({
  icon,
  title,
  body,
  action,
  testID,
}: {
  icon: { sf: SFSymbol; md: AndroidSymbol };
  title: string;
  body: string;
  action?: ReactNode;
  testID?: string;
}) {
  const s = useStyles();
  const reduced = useReducedMotion();
  return (
    <Animated.View entering={entrance(0, reduced)} style={s.empty} testID={testID}>
      <View style={s.emptyIcon}>
        <Icon sf={icon.sf} md={icon.md} size={28} color="accent" />
      </View>
      <Text variant="heading" style={s.center}>
        {title}
      </Text>
      <Text variant="secondary" style={s.center}>
        {body}
      </Text>
      {action ? <View style={s.emptyAction}>{action}</View> : null}
    </Animated.View>
  );
}

export type BadgeTone = "neutral" | "accent" | "success" | "warning" | "danger";
const DOT: Record<BadgeTone, keyof Palette> = {
  neutral: "inkFaint",
  accent: "accent",
  success: "success",
  warning: "warning",
  danger: "danger",
};

/** A status label. The dot is colour; the text carries the meaning. */
export function Badge({ label, tone = "neutral", testID }: { label: string; tone?: BadgeTone; testID?: string }) {
  const t = useTheme();
  const s = useStyles();
  return (
    <View style={s.badge} testID={testID} accessible accessibilityLabel={label}>
      <View style={[s.dot, { backgroundColor: t.color[DOT[tone]] }]} />
      <Text variant="meta" tone="dim">
        {label}
      </Text>
    </View>
  );
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.length > 1 ? [parts[0], parts[parts.length - 1]] : parts;
  return letters.map((p) => (p ?? "").charAt(0).toUpperCase()).join("") || "?";
}

export function Avatar({ name, uri, size = 44, testID }: { name: string; uri?: string; size?: number; testID?: string }) {
  const s = useStyles();
  const t = useT();
  const box = { width: size, height: size, borderRadius: size / 2 };
  return (
    <View style={[s.avatar, box]} testID={testID} accessible accessibilityRole="image" accessibilityLabel={name || t("common.profile")}>
      {uri ? (
        <Image source={{ uri }} style={box} accessibilityIgnoresInvertColors />
      ) : (
        <Text variant="heading" tone="onAccent" style={{ fontSize: size * 0.4, lineHeight: size * 0.5 }} maxFontSizeMultiplier={1}>
          {initials(name)}
        </Text>
      )}
    </View>
  );
}

/** Determinate progress, 0..1. Announced as a percentage. */
export function ProgressBar({ value, label, testID }: { value: number; label: string; testID?: string }) {
  const s = useStyles();
  const clamped = Math.min(1, Math.max(0, value));
  const progress = useSharedValue(0);
  useEffect(() => {
    progress.set(animateTo(clamped, "deliberate", "enter"));
  }, [clamped, progress]);
  const fill = useAnimatedStyle(() => ({ width: `${progress.get() * 100}%` }));
  return (
    <View
      style={s.track}
      testID={testID}
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityValue={{ min: 0, max: 100, now: Math.round(clamped * 100) }}
    >
      <Animated.View style={[s.fill, fill]} />
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  empty: { alignItems: "center", gap: t.space.sm, paddingVertical: t.space.xl, paddingHorizontal: t.space.md },
  emptyIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: t.color.control,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: t.space.sm,
  },
  emptyAction: { marginTop: t.space.md, alignSelf: "stretch" },
  center: { textAlign: "center" },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    gap: t.space.xs,
    alignSelf: "flex-start",
    paddingHorizontal: t.space.sm,
    paddingVertical: t.space.xs,
    borderRadius: t.radius.pill,
    backgroundColor: t.color.control,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  avatar: { backgroundColor: t.color.accent, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  track: { height: 8, borderRadius: 4, backgroundColor: t.color.control, overflow: "hidden" },
  fill: { height: 8, borderRadius: 4, backgroundColor: t.color.accent },
}));
