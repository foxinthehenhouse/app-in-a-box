/**
 * The Settings analytics toggle shows the choice that is actually in force: seeded from
 * the SDK's persisted opt-out flag, not from a hardcoded `true`. Demo mode, real routes.
 */
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { pressWhenEnabled } from "./support/press";

process.env.EXPO_PUBLIC_DEMO = "1";
process.env.EXPO_PUBLIC_POSTHOG_API_KEY = "phc_test"; // so lib/analytics.ts builds a client

const mockPosthog = { optedOut: true, ready: jest.fn(async () => undefined), optIn: jest.fn(async () => undefined), optOut: jest.fn(async () => undefined), capture: jest.fn(), identify: jest.fn(), reset: jest.fn() };
jest.mock("posthog-react-native", () => ({ __esModule: true, default: jest.fn(() => mockPosthog) }));

it("renders the toggle OFF when the user had opted out", async () => {
  await renderRouter("./app", { initialUrl: "/" });
  await fireEvent.changeText(await screen.findByTestId("signin-email-input"), "sam@example.com");
  await pressWhenEnabled("signin-send-button");
  await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
  await pressWhenEnabled("signin-verify-button");
  await screen.findByTestId("home-screen");
  await act(async () => router.navigate("/settings"));
  const toggle = await screen.findByTestId("settings-analytics-switch");
  await waitFor(() => expect(toggle.props.disabled).toBeFalsy()); // the SDK flag has been read
  expect(toggle.props.value).toBe(false);
  expect(mockPosthog.ready).toHaveBeenCalled();
}, 30000);
