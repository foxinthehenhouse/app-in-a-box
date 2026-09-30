/**
 * Celebration: the payoff moment of the core loop (a streak kept, a pair
 * reunited). Increment `trigger` to fire a confetti burst plus a success haptic,
 * and the message is announced to screen readers.
 *
 *   const [wins, setWins] = useState(0);
 *   <Celebration trigger={wins} message="Pair reunited!" />
 *
 * Reduce motion: no confetti; the message card fades in and out instead.
 * Use it sparingly: one moment per completed arc, never for routine saves.
 */
import { useEffect } from "react";
import { AccessibilityInfo, StyleSheet, View, useWindowDimensions } from "react-native";
import Animated, {
  Easing,
  ReduceMotion,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withSequence,
  withTiming,
} from "react-native-reanimated";

import { haptic, motionPlan, timing, useReducedMotion } from "../../lib/motion";
import { makeStyles, motion, useTheme, type Palette } from "../../lib/theme";
import { Icon } from "./Icon";
import { Text } from "./Text";

export interface ConfettiPiece {
  dx: number; // horizontal travel, -1..1 of half the screen width
  lift: number; // initial upward throw, 0.6..1
  spin: number; // degrees over the flight
  delay: number; // ms
  size: number; // px
  color: keyof Palette;
  round: boolean;
}

const COLORS: (keyof Palette)[] = ["accent", "success", "warning", "danger", "ink"];

/** Deterministic pieces (seeded PRNG): pure, so render stays pure and tests are stable. */
export function confettiPieces(count: number, seed = 7): ConfettiPiece[] {
  let x = seed >>> 0 || 1;
  const rand = () => {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    return ((x >>> 0) % 10000) / 10000;
  };
  return Array.from({ length: count }, (_, i) => ({
    dx: rand() * 2 - 1,
    lift: 0.6 + rand() * 0.4,
    spin: (rand() * 2 - 1) * 720,
    delay: Math.round(rand() * 120),
    size: 6 + Math.round(rand() * 6),
    color: COLORS[i % COLORS.length] ?? "accent",
    round: rand() > 0.6,
  }));
}

const PIECES = confettiPieces(36);

export function Celebration({ trigger, message, testID }: { trigger: number; message: string; testID?: string }) {
  const { confetti } = motionPlan(useReducedMotion());
  if (trigger <= 0) return null;
  // Keyed by trigger: each increment mounts a fresh burst that plays once.
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill} testID={testID}>
      {confetti ? <Burst key={`b${trigger}`} message={message} /> : <QuietCard key={`q${trigger}`} message={message} />}
    </View>
  );
}

function useAnnounce(message: string) {
  useEffect(() => {
    haptic.success();
    AccessibilityInfo.announceForAccessibility(message);
  }, [message]);
}

function Burst({ message }: { message: string }) {
  useAnnounce(message);
  const { width, height } = useWindowDimensions();
  return (
    <>
      {PIECES.map((p, i) => (
        <Piece key={i} piece={p} width={width} height={height} />
      ))}
      <QuietCard message={message} />
    </>
  );
}

function Piece({ piece, width, height }: { piece: ConfettiPiece; width: number; height: number }) {
  const t = useTheme();
  const progress = useSharedValue(0);
  useEffect(() => {
    progress.set(withDelay(piece.delay, withTiming(1, { duration: motion.duration.ambient, easing: Easing.linear, reduceMotion: ReduceMotion.System })));
  }, [progress, piece.delay]);
  const style = useAnimatedStyle(() => {
    const p = progress.get();
    const y = -height * 0.35 * piece.lift * p + height * 0.75 * p * p;
    return {
      opacity: p < 0.8 ? 1 : (1 - p) * 5,
      transform: [
        { translateX: piece.dx * width * 0.5 * p },
        { translateY: y },
        { rotate: `${piece.spin * p}deg` },
      ],
    };
  });
  return (
    <Animated.View
      style={[
        {
          position: "absolute",
          left: width / 2,
          top: height * 0.38,
          width: piece.size,
          height: piece.round ? piece.size : piece.size * 1.6,
          borderRadius: piece.round ? piece.size / 2 : 2,
          backgroundColor: t.color[piece.color],
        },
        style,
      ]}
    />
  );
}

function QuietCard({ message }: { message: string }) {
  const s = useStyles();
  const { confetti } = motionPlan(useReducedMotion());
  const opacity = useSharedValue(0);
  const scale = useSharedValue(confetti ? 0.8 : 1);
  useEffect(() => {
    opacity.set(withSequence(withTiming(1, timing("fast")), withDelay(1100, withTiming(0, timing("standard")))));
    scale.set(withTiming(1, timing("screen", "enter")));
  }, [opacity, scale]);
  const style = useAnimatedStyle(() => ({ opacity: opacity.get(), transform: [{ scale: scale.get() }] }));
  return (
    <View style={s.center}>
      <Animated.View style={[s.card, style]}>
        <Icon sf="party.popper.fill" md="celebration" size={28} color="accent" />
        <Text variant="heading">{message}</Text>
      </Animated.View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  center: { ...StyleSheet.absoluteFill, alignItems: "center", justifyContent: "center" },
  card: {
    alignItems: "center",
    gap: t.space.sm,
    paddingHorizontal: t.space.xl,
    paddingVertical: t.space.lg,
    borderRadius: t.radius.lg,
    backgroundColor: t.color.surfaceRaised,
    ...t.elevation.overlay,
  },
}));
