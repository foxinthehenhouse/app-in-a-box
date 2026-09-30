import { ReduceMotion } from "react-native-reanimated";

import { entrance, motionPlan, spring, timing } from "../motion";
import { motion } from "../tokens";

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

  it("drops the entrance animation entirely under reduce motion", () => {
    expect(entrance(0, true)).toBeUndefined();
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
