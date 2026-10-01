import { render, screen } from "@testing-library/react-native";

import { confettiPieces } from "../ui/Celebration";
import { countFrame } from "../ui/AnimatedNumber";
import { initials } from "../ui/Feedback";
import { Field } from "../ui/Field";

jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);

describe("Field", () => {
  // The "captured at mount" bug: an input that copies `value` into its own state
  // renders blank when the parent's data arrives after mount, and Save writes the
  // blank back. Assert the rendered value, not just that the testID exists.
  it("shows a value that arrives after mount", async () => {
    const { rerender } = await render(<Field label="Name" value="" onChangeText={() => undefined} testID="f" />);
    expect(screen.getByTestId("f").props.value).toBe("");
    await rerender(<Field label="Name" value="Sam" onChangeText={() => undefined} testID="f" />);
    expect(screen.getByTestId("f").props.value).toBe("Sam");
  });

  it("labels the input and announces an error", async () => {
    await render(<Field label="Email" value="x" onChangeText={() => undefined} error="Enter a valid email" testID="e" />);
    expect(screen.getByTestId("e").props.accessibilityLabel).toBe("Email");
    expect(screen.getByRole("alert")).toBeTruthy();
  });
});

describe("pure helpers", () => {
  it("counts up with an ease-out and lands exactly on the target", () => {
    expect(countFrame(0, 100, 0)).toBe(0);
    expect(countFrame(0, 100, 0.5)).toBeGreaterThan(50);
    expect(countFrame(0, 100, 1)).toBe(100);
    expect(countFrame(0, 100, 7)).toBe(100);
  });

  it("generates the same confetti for the same seed (render stays pure)", () => {
    expect(confettiPieces(10, 3)).toEqual(confettiPieces(10, 3));
    expect(confettiPieces(10, 3)).not.toEqual(confettiPieces(10, 4));
    for (const p of confettiPieces(50)) {
      expect(Math.abs(p.dx)).toBeLessThanOrEqual(1);
      expect(p.lift).toBeGreaterThanOrEqual(0.6);
    }
  });

  it("builds initials from a name", () => {
    expect(initials("Sam Rivera")).toBe("SR");
    expect(initials("  cher ")).toBe("C");
    expect(initials("")).toBe("?");
  });
});
