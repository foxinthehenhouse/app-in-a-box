/**
 * PressableScale: the one tappable primitive. Every button, row, chip and card
 * press goes through it, so press feedback is consistent everywhere:
 *   1. a sub-100ms scale-down (skipped under reduce motion),
 *   2. a tint overlay (kept under reduce motion: it's state feedback, not motion),
 *   3. a haptic on press-IN, connected to the finger, never on the resolved press.
 *
 * Styles are OBJECT styles, never `style={({ pressed }) => ...}` with a
 * backgroundColor: function styles that paint a fill get dropped in some Release
 * builds (NativeWind interop) and the button renders invisible, a bug that never
 * shows in dev. The tint is a separate animated overlay for the same reason.
 */
import type { ReactNode } from "react";
import { Pressable, StyleSheet, type PressableProps, type StyleProp, type ViewStyle } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue } from "react-native-reanimated";

import { animateTo, haptic as haptics, motionPlan, useReducedMotion, type HapticKind } from "../../lib/motion";
import { useTheme, withAlpha } from "../../lib/theme";

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export interface PressableScaleProps extends Omit<PressableProps, "style" | "children"> {
  children: ReactNode;
  /** Haptic on press-in. null to disable. Default "light". */
  haptic?: HapticKind | null;
  /** Override the token press scale (smaller for icon buttons, e.g. 0.92). */
  scaleTo?: number;
  pressTint?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function PressableScale({
  children,
  haptic = "light",
  scaleTo,
  pressTint = true,
  style,
  disabled,
  onPressIn,
  onPressOut,
  ...rest
}: PressableScaleProps) {
  const t = useTheme();
  const reduced = useReducedMotion();
  const target = motionPlan(reduced).pressScale === 1 ? 1 : (scaleTo ?? t.motion.pressScale);
  const scale = useSharedValue(1);
  const tint = useSharedValue(0);

  const scaleStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.get() }] }));
  const tintStyle = useAnimatedStyle(() => ({ opacity: tint.get() }));

  return (
    <AnimatedPressable
      {...rest}
      disabled={disabled}
      onPressIn={(e) => {
        if (!disabled) {
          scale.set(animateTo(target, "instant", "standard"));
          tint.set(animateTo(1, "instant", "standard"));
          if (haptic) haptics[haptic]();
        }
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        scale.set(animateTo(1, "fast", "enter"));
        tint.set(animateTo(0, "standard", "standard"));
        onPressOut?.(e);
      }}
      style={[style, scaleStyle]}
    >
      {children}
      {pressTint ? (
        <Animated.View
          pointerEvents="none"
          style={[
            StyleSheet.absoluteFill,
            { backgroundColor: withAlpha(t.color.ink, t.opacity.pressed), borderRadius: flatRadius(style) },
            tintStyle,
          ]}
        />
      ) : null}
    </AnimatedPressable>
  );
}

function flatRadius(style: StyleProp<ViewStyle>): number | undefined {
  const r = StyleSheet.flatten(style)?.borderRadius;
  return typeof r === "number" ? r : undefined;
}
