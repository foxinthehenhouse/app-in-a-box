import { ReduceMotion } from "react-native-reanimated";

import { dampingRatio, entrance, haptic, hapticFor, motionPlan, screenEntrance, spring, timing } from "../motion";
import { motion, settle } from "../tokens";

describe("reduce motion", () => {
  it("turns every decorative animation off and press scale to 1", () => {
    expect(motionPlan(true)).toEqual({ shimmer: false, confetti: false, countUp: false, entrance: false, pressScale: 1 });
  });

  it("keeps them on otherwise, with the token press scale", () => {
    const plan = motionPlan(false);
    expect(plan.shimmer && plan.confetti && plan.countUp && plan.entrance).toBe(true);
    expect(plan.pressScale).toBe(motion.pressScale);
    expect(plan.pressScale).toBeLessThan(1);
  });

  it("drops the entrance animations entirely under reduce motion", () => {
    expect(entrance(0, true)).toBeUndefined();
    expect(screenEntrance(true)).toBeUndefined();
    expect(entrance(0, false)).toBeDefined();
    expect(screenEntrance(false)).toBeDefined();
  });

  it("makes every timing and spring preset respect the system setting", () => {
    expect(timing("fast").reduceMotion).toBe(ReduceMotion.System);
    expect(spring("bouncy").reduceMotion).toBe(ReduceMotion.System);
  });
});

describe("presets come from tokens", () => {
  it("uses the token duration and spring constants", () => {
    expect(timing("deliberate").duration).toBe(motion.duration.deliberate);
    expect(spring("snappy")).toMatchObject(motion.spring.snappy);
  });
});

describe("settle: screens and content arrive without passing the mark", () => {
  // The prototype's settle_spring(): `gentle`, damped to at least critical.
  it("is the gentle spring damped to at least critical", () => {
    const g = motion.spring.gentle;
    expect(settle.stiffness).toBe(g.stiffness);
    expect(settle.mass).toBe(g.mass);
    expect(settle.damping).toBeCloseTo(Math.max(g.damping, 2 * Math.sqrt(g.stiffness * g.mass)), 6);
    expect(dampingRatio(settle)).toBeGreaterThanOrEqual(1 - 1e-9);
  });

  it("is a spring preset that respects reduce motion", () => {
    expect(spring("settle")).toMatchObject(settle);
    expect(spring("settle").reduceMotion).toBe(ReduceMotion.System);
  });

  it("measures overshoot: a bouncy spring is under-damped, settle is not", () => {
    expect(dampingRatio({ damping: 12, stiffness: 220, mass: 1 })).toBeLessThan(1);
    expect(dampingRatio({ damping: 30, stiffness: 225, mass: 1 })).toBe(1);
  });
});

describe("haptic token map", () => {
  it("maps every control role to a real rung of the ladder", () => {
    for (const kind of Object.values(hapticFor)) expect(typeof haptic[kind]).toBe("function");
    expect(hapticFor.primary).toBe("medium");
    expect(hapticFor.chip).toBe("selection");
  });
});
