/**
 * The kill-push kill switch (lib/flags.ts): when it's on, Settings says notifications
 * are paused and the toggle can't be used. With it off (the default), nothing changes.
 * Demo mode, real routes.
 */
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { pressWhenEnabled } from "./support/press";

process.env.EXPO_PUBLIC_DEMO = "1";
process.env.EXPO_PUBLIC_POSTHOG_API_KEY = "phc_test"; // so lib/analytics.ts builds a client

const listeners: (() => void)[] = [];
const mockFlags = { killed: false };
const mockPosthog = {
  optedOut: false,
  ready: jest.fn(async () => undefined),
  capture: jest.fn(),
  identify: jest.fn(),
  reset: jest.fn(),
  getFeatureFlag: jest.fn((key: string): boolean | undefined => (key === "kill-push" ? mockFlags.killed : undefined)),
  onFeatureFlags: jest.fn((cb: () => void) => {
    listeners.push(cb);
    return () => undefined;
  }),
};
jest.mock("posthog-react-native", () => ({ __esModule: true, default: jest.fn(() => mockPosthog) }));

async function openSettings() {
  await renderRouter("./app", { initialUrl: "/" });
  await fireEvent.changeText(await screen.findByTestId("signin-email-input"), "sam@example.com");
  await pressWhenEnabled("signin-send-button");
  await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
  await pressWhenEnabled("signin-verify-button");
  await screen.findByTestId("home-screen");
  await act(async () => router.navigate("/settings"));
  return screen.findByTestId("settings-push-switch");
}

it("pauses the notifications toggle when PostHog turns kill-push on", async () => {
  mockFlags.killed = false;
  await openSettings();
  expect(screen.queryByText(/paused for everyone/)).toBeNull();
  mockFlags.killed = true;
  await act(async () => listeners.forEach((cb) => cb()));
  await screen.findByText(/paused for everyone/);
  // getBy, not findBy, inside waitFor: a findBy nested in waitFor leaves its own polling
  // behind after the test, which kept a jest worker's event loop spinning.
  await waitFor(() => expect(screen.getByTestId("settings-push-switch").props.disabled).toBe(true));
}, 30000);
