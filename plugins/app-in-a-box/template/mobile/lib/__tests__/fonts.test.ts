import { BUILT_IN_FONTS, fontAssets, fontFace } from "../fonts";
import { font, typeRoles } from "../tokens";

// A face named by the tokens but never loaded falls back to the system font (or a
// faked bold) without an error, so the shipped app quietly stops matching the
// frozen prototype. This is the check that makes that loud.
describe("fonts", () => {
  it("loads every family + weight the type roles use", () => {
    const missing = new Set<string>();
    for (const spec of Object.values(typeRoles) as { font: string; weight: string }[]) {
      const family = font[spec.font as keyof typeof font];
      if (!BUILT_IN_FONTS.has(family) && !(`${family}_${spec.weight}` in fontAssets)) {
        missing.add(`${family}_${spec.weight}`);
      }
    }
    expect([...missing]).toEqual([]);
  });

  it("resolves a registered weight to its own face, and anything else to none", () => {
    const assets = { Fraunces_700: 1 };
    expect(fontFace("Fraunces", "700", assets)).toBe("Fraunces_700");
    expect(fontFace("Fraunces", "400", assets)).toBeUndefined();
  });
});
