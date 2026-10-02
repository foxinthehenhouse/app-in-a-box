/** The root ErrorBoundary is themed, translated, reported, and recoverable. */
import { fireEvent, render, screen } from "@testing-library/react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { ErrorBoundary } from "../app/_layout";
import { en } from "../locales/en";

jest.mock("../lib/monitoring", () => ({ initMonitoring: jest.fn(), reportError: jest.fn(), wrapRoot: (c: unknown) => c }));
const { reportError } = jest.requireMock("../lib/monitoring") as { reportError: jest.Mock };

it("shows a way forward and reports the error", async () => {
  const retry = jest.fn(async () => undefined);
  const error = new Error("render exploded");
  await render(
    <SafeAreaProvider initialMetrics={{ frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } }}>
      <ErrorBoundary error={error} retry={retry} />
    </SafeAreaProvider>,
  );
  expect(await screen.findByText(en.errorBoundary.title)).toBeTruthy();
  expect(reportError).toHaveBeenCalledWith(error, { boundary: "root" });
  await fireEvent.press(screen.getByTestId("root-error-retry-button"));
  expect(retry).toHaveBeenCalled();
});
