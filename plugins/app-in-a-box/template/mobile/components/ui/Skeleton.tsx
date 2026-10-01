/**
 * Skeleton: the loading state for content (spinners are only for a button's own
 * busy state). Shaped like the content it stands in for, with a slow shimmer on
 * the symmetric `loop` curve. Reduce motion: a static block, no shimmer.
 * The group is one "Loading" element for screen readers; pass `announce` for a
 * screen-replacing load.
 */
import { useEffect } from "react";
import { AccessibilityInfo, StyleSheet, View, type DimensionValue, type StyleProp, type ViewStyle } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withRepeat, withTiming } from "react-native-reanimated";

import { useT } from "../../lib/i18n";
import { motionPlan, timing, useReducedMotion } from "../../lib/motion";
import { makeStyles, useTheme } from "../../lib/theme";

export interface SkeletonProps {
  width?: DimensionValue;
  height?: number;
  radius?: number;
  circle?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function Skeleton({ width = "100%", height = 14, radius, circle = false, style }: SkeletonProps) {
  const t = useTheme();
  const s = useStyles();
  const { shimmer } = motionPlan(useReducedMotion());
  const pulse = useSharedValue(0);

  useEffect(() => {
    if (!shimmer) return;
    pulse.set(withRepeat(withTiming(1, timing("ambient", "loop")), -1, true));
  }, [shimmer, pulse]);

  const sweep = useAnimatedStyle(() => ({ opacity: 0.25 + pulse.get() * 0.5 }));
  const size = circle ? { width: height, height, borderRadius: height / 2 } : { width, height, borderRadius: radius ?? t.radius.sm };
  return (
    <View style={[s.block, size, style]} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
      {shimmer ? <Animated.View pointerEvents="none" style={[StyleSheet.absoluteFill, s.sheen, sweep]} /> : null}
    </View>
  );
}

/** A labelled group of skeleton lines in the shape of a card. */
export function SkeletonCard({ lines = 3, announce, testID }: { lines?: number; announce?: string; testID?: string }) {
  const s = useStyles();
  const t = useT();
  useEffect(() => {
    if (announce) AccessibilityInfo.announceForAccessibility(announce);
  }, [announce]);
  return (
    <View style={s.card} accessible accessibilityLabel={announce ?? t("common.loading")} accessibilityState={{ busy: true }} testID={testID}>
      <View style={s.row}>
        <Skeleton circle height={40} />
        <View style={s.flex}>
          <Skeleton width="55%" height={16} />
          <Skeleton width="35%" height={12} style={s.gapTop} />
        </View>
      </View>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} width={i === lines - 1 ? "70%" : "100%"} />
      ))}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  block: { backgroundColor: t.color.control, overflow: "hidden" },
  sheen: { backgroundColor: t.color.border },
  card: { backgroundColor: t.color.surfaceRaised, borderRadius: t.radius.lg, padding: t.space.lg, gap: t.space.md },
  row: { flexDirection: "row", alignItems: "center", gap: t.space.md },
  flex: { flex: 1 },
  gapTop: { marginTop: t.space.sm },
}));
