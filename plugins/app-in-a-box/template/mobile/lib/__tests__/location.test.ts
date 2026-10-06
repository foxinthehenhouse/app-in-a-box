/**
 * Location is coarse unless a feature asks for more: coarsen() rounds to about a
 * kilometre by default and drops everything but the two coordinates.
 */
import { PRECISION, coarsen, uncertaintyMeters } from "../location";

const home = { latitude: 51.501364, longitude: -0.14189 };

it("rounds to about a kilometre by default", () => {
  expect(coarsen(home)).toEqual({ latitude: 51.5, longitude: -0.14 });
});

it("rounds to the asked precision, coarser or finer", () => {
  expect(coarsen(home, "city")).toEqual({ latitude: 51.5, longitude: -0.1 });
  expect(coarsen(home, "block")).toEqual({ latitude: 51.501, longitude: -0.142 });
});

it("keeps only the coordinates (no accuracy, altitude, heading or speed)", () => {
  const reading = { ...home, accuracy: 3, altitude: 20, heading: 90, speed: 1.2 };
  expect(Object.keys(coarsen(reading))).toEqual(["latitude", "longitude"]);
});

it("says how far off a coarsened position can be", () => {
  expect(uncertaintyMeters()).toBeGreaterThan(500);
  expect(uncertaintyMeters()).toBeLessThan(1000);
  expect(uncertaintyMeters("city")).toBeGreaterThan(uncertaintyMeters("block"));
  expect(Object.keys(PRECISION)).toEqual(["city", "coarse", "block"]);
});
