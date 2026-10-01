/**
 * AnimatedNumber: counts to `value` on mount and on change (the "your streak
 * went up" moment). JS-driven with requestAnimationFrame, so it works the same
 * on iOS, Android and web; ~30 short re-renders is cheap for a number.
 * Reduce motion: renders the final value immediately. Screen readers get the
 * final value, never the in-between frames.
 */
import { useEffect, useRef, useState } from "react";

import { motionPlan, useReducedMotion, type Duration } from "../../lib/motion";
import { motion } from "../../lib/theme";
import { Text, type TextProps } from "./Text";

/** easeOutCubic: fast start, gentle landing. Pure for tests. */
export function countFrame(from: number, to: number, progress: number): number {
  const p = Math.min(1, Math.max(0, progress));
  return from + (to - from) * (1 - Math.pow(1 - p, 3));
}

export interface AnimatedNumberProps extends Omit<TextProps, "children"> {
  value: number;
  format?: (n: number) => string;
  duration?: Duration;
}

export function AnimatedNumber({
  value,
  format = (n) => Math.round(n).toLocaleString(),
  duration = "deliberate",
  variant = "display",
  ...rest
}: AnimatedNumberProps) {
  const { countUp } = motionPlan(useReducedMotion());
  const [shown, setShown] = useState(countUp ? 0 : value);
  const from = useRef(countUp ? 0 : value);

  useEffect(() => {
    const start = from.current;
    if (!countUp || start === value) {
      from.current = value;
      const id = requestAnimationFrame(() => setShown(value));
      return () => cancelAnimationFrame(id);
    }
    const ms = motion.duration[duration];
    let raf = 0;
    let t0: number | null = null;
    const tick = (now: number) => {
      t0 ??= now;
      const p = (now - t0) / ms;
      setShown(countFrame(start, value, p));
      if (p < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, countUp, duration]);

  return (
    <Text variant={variant} accessibilityLabel={format(value)} {...rest} style={[{ fontVariant: ["tabular-nums"] }, rest.style]}>
      {format(shown)}
    </Text>
  );
}
