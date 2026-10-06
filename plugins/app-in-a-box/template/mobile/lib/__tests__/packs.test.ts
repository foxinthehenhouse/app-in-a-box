/**
 * lib/packs.ts is generated from privacy/data-map.yaml (scripts/check_guardrails.py
 * --write). Whatever is enabled, baseline is on and packOn agrees with PACKS.
 */
import { PACKS, packOn } from "../packs";

it("always has baseline, and packOn reads PACKS", () => {
  expect(PACKS).toContain("baseline");
  for (const id of ["baseline", "location", "minors", "health", "ugc", "financial", "biometric"] as const) {
    expect(packOn(id)).toBe(PACKS.includes(id));
  }
});
