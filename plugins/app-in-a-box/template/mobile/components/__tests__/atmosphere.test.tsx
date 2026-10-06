import { render, screen } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { atmosphereGradient } from "../../lib/atmosphere";
import { ThemeScope } from "../../lib/theme";
import { Screen } from "../ui/Screen";
import { ScreenAtmosphere } from "../ui/ScreenAtmosphere";
import { SheetHeader } from "../ui/Sheet";
import { Body } from "../ui/Text";

jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);
jest.mock("expo-router", () => ({ router: { canDismiss: () => false, canGoBack: () => false } }));
const mockGlass = { on: false };
jest.mock("../../lib/atmosphere", () => ({
  ...jest.requireActual("../../lib/atmosphere"),
  useGlassChrome: () => mockGlass.on,
}));
jest.mock("expo-glass-effect", () => {
  const { View } = require("react-native");
  return { GlassView: (p: object) => <View testID="glass" {...p} />, isLiquidGlassAvailable: () => true };
});

describe("ScreenAtmosphere", () => {
  it("paints the frozen lights behind a screen, out of reach of touch and screen readers", async () => {
    await render(
      <ThemeScope scheme="dark">
        <Screen testID="home">
          <Body>Hello</Body>
        </Screen>
      </ThemeScope>,
    );
    const layer = screen.getByTestId("home-atmosphere", { includeHiddenElements: true });
    const style = StyleSheet.flatten(layer.props.style);
    expect(style.experimental_backgroundImage).toBe(atmosphereGradient("dark"));
    expect(style.pointerEvents).toBe("none");
    expect(layer.props.importantForAccessibility).toBe("no-hide-descendants");
    expect(screen.getByText("Hello")).toBeTruthy();
  });

  it("leaves sheets on their plain surface", async () => {
    await render(
      <Screen testID="sheet" sheet>
        <Body>Edit</Body>
      </Screen>,
    );
    expect(screen.queryByTestId("sheet-atmosphere", { includeHiddenElements: true })).toBeNull();
  });

  it("renders in both modes from the tokens alone", async () => {
    for (const scheme of ["light", "dark"] as const) {
      await render(
        <ThemeScope scheme={scheme}>
          <ScreenAtmosphere testID={`atmo-${scheme}`} />
        </ThemeScope>,
      );
      if (atmosphereGradient(scheme)) expect(screen.getByTestId(`atmo-${scheme}`, { includeHiddenElements: true })).toBeTruthy();
    }
  });
});

describe("SheetHeader glass", () => {
  it("is solid unless glass chrome is allowed", async () => {
    mockGlass.on = false;
    await render(<SheetHeader title="Edit name" />);
    expect(screen.queryByTestId("glass")).toBeNull();
    mockGlass.on = true;
    await render(<SheetHeader title="Edit name" />);
    expect(screen.getByTestId("glass")).toBeTruthy();
    expect(screen.getByText("Edit name")).toBeTruthy();
  });
});
