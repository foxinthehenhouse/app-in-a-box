import { act, render, screen } from "@testing-library/react-native";
import { AccessibilityInfo, Platform, Text } from "react-native";

import {
  GRAIN,
  atmosphere,
  atmosphereGradient,
  glassChrome,
  grainStyle,
  liquidGlassAvailable,
  useReducedTransparency,
  type Atmosphere,
} from "../atmosphere";
import { withAlpha } from "../theme";

jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);

const SCHEMES = ["light", "dark"] as const;
const lit: Atmosphere = {
  mode: "glow",
  intensity: "medium",
  grain: true,
  surface: "solid",
  lights: [
    [0.18, -0.06, 0.78, 0.44],
    [1.02, 0.74, 0.7, 0.4],
  ],
  // the generated colours, with a lit alpha even if this theme froze mode none
  color: { light: { ...atmosphere.color.light, alpha: 0.62 }, dark: { ...atmosphere.color.dark, alpha: 0.4 } },
};

describe("atmosphere parity with the prototype", () => {
  // The prototype draws `radial-gradient(rx% ry% at cx% cy%, light a%, ...)` from the
  // same geometry; the app must paint the frozen colours and capped alpha unchanged.
  it("paints the frozen geometry, colours and alpha as the prototype's radial gradients", () => {
    const { light1, light2 } = lit.color.dark;
    expect(atmosphereGradient("dark", lit)).toBe(
      `radial-gradient(78% 44% at 18% -6%, ${withAlpha(light1, 0.4)}, ${withAlpha(light1, 0)}), ` +
        `radial-gradient(70% 40% at 102% 74%, ${withAlpha(light2, 0.4)}, ${withAlpha(light2, 0)})`,
    );
    expect(withAlpha(light1, 0.4)).toMatch(/^rgba\(\d+, \d+, \d+, 0\.4\)$/);
  });

  it("passes the generated tokens through for both modes", () => {
    for (const scheme of SCHEMES) {
      const c = atmosphere.color[scheme];
      const g = atmosphereGradient(scheme);
      if (atmosphere.mode === "none" || c.alpha === 0) {
        expect(g).toBeNull();
        continue;
      }
      expect(g).toContain(withAlpha(c.light1, c.alpha));
      expect(g).toContain(withAlpha(c.light2, c.alpha));
      expect(g?.match(/radial-gradient\(/g)).toHaveLength(2);
    }
  });

  it("paints nothing for mode none or a palette with no headroom (alpha 0)", () => {
    expect(atmosphereGradient("light", { ...lit, mode: "none" })).toBeNull();
    expect(atmosphereGradient("dark", { ...lit, color: { ...lit.color, dark: { ...lit.color.dark, alpha: 0 } } })).toBeNull();
  });

  it("falls back to the glow for field mode (no shader dependency)", () => {
    expect(atmosphereGradient("light", { ...lit, mode: "field" })).toBe(atmosphereGradient("light", lit));
  });

  it("lays grain only when the knob is on, at the prototype's per-mode opacity", () => {
    expect(grainStyle("dark", lit)).toEqual(GRAIN.dark);
    expect(grainStyle("light", { ...lit, grain: false })).toBeNull();
    expect(GRAIN.light.opacity).toBeLessThan(0.1);
  });
});

describe("glass chrome", () => {
  it("is glass only when chosen, available and transparency is allowed", () => {
    expect(glassChrome("glass", true, false)).toBe(true);
    expect(glassChrome("glass", true, true)).toBe(false); // Reduce Transparency wins
    expect(glassChrome("glass", false, false)).toBe(false); // below iOS 26: solid
    expect(glassChrome("solid", true, false)).toBe(false);
  });

  it("never claims Liquid Glass off iOS", () => {
    const os = Platform.OS;
    Object.defineProperty(Platform, "OS", { value: "android", configurable: true });
    try {
      expect(liquidGlassAvailable()).toBe(false);
    } finally {
      Object.defineProperty(Platform, "OS", { value: os, configurable: true });
    }
  });
});

describe("useReducedTransparency", () => {
  function Probe() {
    return <Text testID="rt">{String(useReducedTransparency())}</Text>;
  }

  it("reads the OS setting and follows it when it flips", async () => {
    let listener: (v: boolean) => void = () => undefined;
    jest.spyOn(AccessibilityInfo, "isReduceTransparencyEnabled").mockResolvedValue(true);
    jest.spyOn(AccessibilityInfo, "addEventListener").mockImplementation(((_e: string, fn: (v: boolean) => void) => {
      listener = fn;
      return { remove: jest.fn() };
    }) as unknown as typeof AccessibilityInfo.addEventListener);
    await render(<Probe />);
    expect(await screen.findByText("true")).toBeTruthy();
    await act(async () => listener(false));
    expect(screen.getByTestId("rt").props.children).toBe("false");
  });
});
