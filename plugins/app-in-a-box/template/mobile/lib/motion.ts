/**
 * Motion system: design/tokens.json `motion` -> Reanimated presets, plus haptics.
 *
 * Rules (the gallery shows each one):
 * - Never hand-roll `withTiming(v, { duration: 300 })`. Use `animateTo(v, "fast")`
 *   or `springTo(v, "snappy")`, so a token change reaches every call site.
 * - Reduce motion is honoured everywhere: every preset carries
 *   `ReduceMotion.System` (the animation jumps to its end state), and decorative
 *   loops/entrances check `useReducedMotion()` and render static instead.
 *   Press feedback that communicates state (tint) still runs.
 * - Loops (skeleton shimmer) use the symmetric `loop` curve; one-shots never do.
 * - Haptics are an accessibility aid, NOT motion, so reduce-motion doesn't mute
 *   them. Grade them by commitment (below), fire on press-in, never in a loop.
 */
import { useEffect, useState } from "react";
import { AccessibilityInfo, Platform } from "react-native";
import * as Haptics from "expo-haptics";
import {
  Easing,
  FadeIn,
  FadeInDown,
  FadeOut,
  ReduceMotion,
  withSpring,
  withTiming,
  type WithSpringConfig,
  type WithTimingConfig,
} from "react-native-reanimated";

import { motion } from "./tokens";

/**
 * The OS "Reduce Motion" setting, reactive: flipping it in Settings re-renders.
 * (Reanimated's hook of the same name reads it once at startup.)
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((v) => alive && setReduced(v))
      .catch(() => undefined);
    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", setReduced);
    return () => {
      alive = false;
      sub.remove();
    };
  }, []);
  return reduced;
}
export type Duration = keyof typeof motion.duration;
export type Curve = keyof typeof motion.easing;
export type SpringName = keyof typeof motion.spring;

export function curve(name: Curve) {
  const [x1, y1, x2, y2] = motion.easing[name];
  return Easing.bezier(x1, y1, x2, y2);
}

export function timing(duration: Duration = "standard", easing: Curve = "standard"): WithTimingConfig {
  return { duration: motion.duration[duration], easing: curve(easing), reduceMotion: ReduceMotion.System };
}

export function spring(name: SpringName = "snappy"): WithSpringConfig {
  return { ...motion.spring[name], reduceMotion: ReduceMotion.System };
}

export function animateTo(value: number, duration: Duration = "standard", easing: Curve = "standard"): number {
  return withTiming(value, timing(duration, easing));
}

export function springTo(value: number, name: SpringName = "snappy"): number {
  return withSpring(value, spring(name));
}

/** Staggered content entrance (fade + rise). Undefined under reduce motion. */
export function entrance(index = 0, reduced = false, step = 45) {
  if (reduced) return undefined;
  return FadeInDown.duration(motion.duration.deliberate)
    .easing(curve("enter"))
    .delay(index * step)
    .reduceMotion(ReduceMotion.System);
}

/** Quick fades for overlays that appear/disappear (toast, celebration). */
export const fadeIn = FadeIn.duration(motion.duration.fast).reduceMotion(ReduceMotion.Never);
export const fadeOut = FadeOut.duration(motion.duration.fast).reduceMotion(ReduceMotion.Never);

/**
 * What a decorative animation should do given the reduce-motion setting.
 * Pure, so behaviour is testable without a native runtime.
 */
export function motionPlan(reduced: boolean): {
  shimmer: boolean;
  confetti: boolean;
  countUp: boolean;
  entrance: boolean;
  pressScale: number;
} {
  return reduced
    ? { shimmer: false, confetti: false, countUp: false, entrance: false, pressScale: 1 }
    : { shimmer: true, confetti: true, countUp: true, entrance: true, pressScale: motion.pressScale };
}

// ---------- Haptics ----------
// The commitment ladder: how much did the user just spend?
//   selection  no commitment     chips, segments, toggles, tab switches
//   light      a navigation step row taps, secondary buttons, sheet open
//   medium     an earned action  primary buttons (Save, Log, Send)
//   success    a completed arc   the core loop's payoff moment, celebration
//   warning    soft caution      destructive confirm
//   error      failure           validation, failed mutation

function safe(fn: () => Promise<unknown>): void {
  if (Platform.OS === "web") return;
  try {
    fn().catch(() => undefined);
  } catch {
    // unsupported hardware: haptics must never crash the app
  }
}

export const haptic = {
  selection: () => safe(() => Haptics.selectionAsync()),
  light: () => safe(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)),
  medium: () => safe(() => Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)),
  success: () => safe(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success)),
  warning: () => safe(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning)),
  error: () => safe(() => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error)),
} as const;

export type HapticKind = keyof typeof haptic;
