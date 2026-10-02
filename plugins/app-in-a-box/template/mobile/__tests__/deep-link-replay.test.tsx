/**
 * A deep link opened while signed out (cold start) is not lost: the auth guard
 * sends the user to sign-in, and once they're in, the app opens the linked
 * screen. Demo mode, the real routes and guard.
 */
import { fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { pressWhenEnabled } from "./support/press";

// Set before the routes (and lib/demo.ts) are required by renderRouter.
process.env.EXPO_PUBLIC_DEMO = "1";
// Required (not imported) so they load AFTER the line above: imports are hoisted.
const intent = require("../app/+native-intent") as typeof import("../app/+native-intent");
const links = require("../lib/links") as typeof import("../lib/links");

it("replays a signed-out cold-start link after sign-in", async () => {
  // The OS hands the app a link before anyone has signed in.
  expect(intent.redirectSystemPath({ path: `${links.SCHEME}://settings`, initial: true })).toBe("/settings");

  // Not awaited directly: the path helpers are attached to the returned object itself.
  const app = renderRouter("./app", { initialUrl: "/" });
  await app;
  expect(await screen.findByTestId("signin-screen")).toBeTruthy();
  await fireEvent.changeText(screen.getByTestId("signin-email-input"), "sam@example.com");
  await pressWhenEnabled("signin-send-button");
  await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
  await pressWhenEnabled("signin-verify-button");

  // Both tabs are mounted (native tabs), so assert WHERE we are, not what exists.
  expect(await screen.findByTestId("home-screen")).toBeTruthy();
  await waitFor(() => expect(app.getPathname()).toBe("/settings"));
}, 30000);
