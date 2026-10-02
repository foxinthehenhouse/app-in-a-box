/**
 * Native tabs mount every tab at launch, so "viewed" must mean FOCUSED: landing on home
 * logs exactly one screen_viewed (home), none for settings; switching to settings logs
 * settings once. Demo mode, the real routes and guard.
 */
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { pressWhenEnabled } from "./support/press";

process.env.EXPO_PUBLIC_DEMO = "1";
const { analytics } = require("../lib/analytics") as typeof import("../lib/analytics");

it("logs a tab view when the tab is shown, not when it is mounted", async () => {
  const viewed = jest.spyOn(analytics, "screenViewed");
  await renderRouter("./app", { initialUrl: "/" });
  await fireEvent.changeText(await screen.findByTestId("signin-email-input"), "sam@example.com");
  await pressWhenEnabled("signin-send-button");
  await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
  await pressWhenEnabled("signin-verify-button");
  await screen.findByTestId("home-screen");
  await screen.findByTestId("settings-screen"); // both tabs ARE mounted...

  const screens = () => viewed.mock.calls.map(([name]) => name);
  await waitFor(() => expect(screens()).toContain("home"));
  expect(screens().filter((s) => s === "home")).toHaveLength(1);
  expect(screens()).not.toContain("settings"); // ...but only the focused one was viewed

  await act(async () => router.navigate("/settings"));
  await waitFor(() => expect(screens().filter((s) => s === "settings")).toHaveLength(1));
}, 30000);
