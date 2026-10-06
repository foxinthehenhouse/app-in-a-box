/**
 * Location, coarse by default (the `location` guardrail pack, docs/privacy/GUARDRAILS.md).
 *
 * A precise position, stored or sent, says where someone sleeps, works and worships.
 * Most features need far less: "near you" works at a kilometre. So every position the
 * app reads goes through coarsen() before it is shown to anyone else, stored or sent,
 * and scripts/check_guardrails.py fails CI on a file that reads a position
 * (expo-location's getCurrentPositionAsync and friends) without calling it. A feature
 * that truly needs the exact point (turn-by-turn directions on the user's own screen)
 * says so on that line: `// guardrail-ok(location): <why>`.
 *
 * Pure and dependency-free on purpose: the app installs expo-location only when a
 * feature needs it, and this file costs nothing until something imports it.
 */

export interface Coords {
  latitude: number;
  longitude: number;
}

/**
 * How finely to keep a position, as decimal places of a degree. Latitude spacing is
 * ~111 km per degree, so: city ~11 km, coarse ~1.1 km (the default), block ~110 m.
 */
export const PRECISION = { city: 1, coarse: 2, block: 3 } as const;
export type Precision = keyof typeof PRECISION;

function round(value: number, places: number): number {
  const f = 10 ** places;
  return Math.round(value * f) / f;
}

/**
 * The position rounded to `precision` (default "coarse", about a kilometre). Accuracy,
 * altitude, heading and speed are dropped: they say more than the feature needs.
 */
export function coarsen(coords: Coords, precision: Precision = "coarse"): Coords {
  const places = PRECISION[precision];
  return { latitude: round(coords.latitude, places), longitude: round(coords.longitude, places) };
}

/** Roughly how far (metres) a coarsened position can be from the real one. */
export function uncertaintyMeters(precision: Precision = "coarse"): number {
  // Half a grid step on each axis, at the equator (the worst case for longitude).
  const halfStep = 0.5 / 10 ** PRECISION[precision];
  return Math.round(Math.hypot(halfStep, halfStep) * 111_320);
}
