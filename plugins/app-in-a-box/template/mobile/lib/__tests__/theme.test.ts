import { buildTheme, resolveScheme, withAlpha } from "../theme";
import { palettes, schemes, typeRoles } from "../tokens";

jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);

describe("resolveScheme", () => {
  const both = ["light", "dark"] as const;

  it("follows the OS when the user hasn't chosen", () => {
    expect(resolveScheme("light", "system", both, "dark")).toBe("light");
    expect(resolveScheme("dark", "system", both, "light")).toBe("dark");
  });

  it("lets an explicit choice beat the OS", () => {
    expect(resolveScheme("dark", "light", both, "dark")).toBe("light");
    expect(resolveScheme("light", "dark", both, "light")).toBe("dark");
  });

  it("falls back to the theme's default mode when the OS reports nothing", () => {
    expect(resolveScheme(null, "system", both, "dark")).toBe("dark");
    expect(resolveScheme("unspecified", "system", both, "light")).toBe("light");
  });

  it("locks a single-palette (v1) theme to its mode, whatever the OS or user says", () => {
    expect(resolveScheme("light", "light", ["dark"], "dark")).toBe("dark");
    expect(resolveScheme("dark", "system", ["light"], "light")).toBe("light");
  });
});

describe("buildTheme", () => {
  it("builds each mode from its own palette", () => {
    for (const scheme of schemes) {
      const t = buildTheme(scheme);
      expect(t.color).toBe(palettes[scheme]);
      expect(t.type.body.color).toBe(palettes[scheme].ink);
      expect(t.type.meta.color).toBe(palettes[scheme].inkFaint);
      expect(t.isDark).toBe(scheme === "dark");
    }
  });

  it("applies every type role's size, line height and Dynamic Type cap from tokens", () => {
    const t = buildTheme("dark");
    for (const role of Object.keys(typeRoles) as (keyof typeof typeRoles)[]) {
      expect(t.type[role].fontSize).toBe(typeRoles[role].size);
      expect(t.type[role].lineHeight).toBe(typeRoles[role].lineHeight);
      expect(t.typeScale[role]).toBe(typeRoles[role].maxScale);
      expect(t.typeScale[role]).toBeGreaterThanOrEqual(1);
    }
  });

  it("uses a hairline instead of a shadow for elevation in dark mode", () => {
    expect(buildTheme("dark").elevation.card).toHaveProperty("borderWidth");
    expect(buildTheme("light").elevation.card).toHaveProperty("boxShadow");
    expect(buildTheme("light").elevation.none).toEqual({});
  });
});

it("withAlpha converts a token hex to rgba", () => {
  const hex = palettes.dark.accent;
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  expect(withAlpha(hex, 0.5)).toBe(`rgba(${r}, ${g}, ${b}, 0.5)`);
});
