/**
 * Delete account, end to end in demo mode (the real routes, providers and auth
 * guard): Settings -> sheet -> type DELETE -> DELETE /api/v1/me -> signed out ->
 * toast. Plus the failure path: nothing is removed, the error shows a reference.
 */
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { pressWhenEnabled } from "./support/press";

import { analytics } from "../lib/analytics";
import { en } from "../locales/en";

// Set before the routes (and lib/demo.ts) are required by renderRouter.
process.env.EXPO_PUBLIC_DEMO = "1";
// Required (not imported) so it loads AFTER the line above: imports are hoisted.
const demo = require("../lib/demo") as typeof import("../lib/demo");
const session = require("../lib/session") as typeof import("../lib/session");

async function signIn() {
  await renderRouter("./app", { initialUrl: "/" });
  await fireEvent.changeText(await screen.findByTestId("signin-email-input"), "sam@example.com");
  await pressWhenEnabled("signin-send-button");
  await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
  await pressWhenEnabled("signin-verify-button");
  expect(await screen.findByTestId("home-screen")).toBeTruthy();
}

it("deletes the account only after DELETE is typed, then signs out with a toast", async () => {
  const deleted = jest.spyOn(analytics, "accountDeleted");
  await signIn();
  await act(async () => router.navigate("/settings"));
  await fireEvent.press(await screen.findByTestId("settings-delete-account-row"));
  expect(await screen.findByTestId("delete-account-sheet")).toBeTruthy();

  const submit = screen.getByTestId("delete-account-submit-button");
  expect(submit.props.accessibilityState?.disabled).toBe(true);
  await fireEvent.changeText(screen.getByTestId("delete-account-confirm-input"), "delete");
  expect(screen.getByTestId("delete-account-submit-button").props.accessibilityState?.disabled).toBe(true);

  await fireEvent.changeText(screen.getByTestId("delete-account-confirm-input"), "DELETE");
  await waitFor(() =>
    expect(screen.getByTestId("delete-account-submit-button").props.accessibilityState?.disabled).toBe(false),
  );
  await pressWhenEnabled("delete-account-submit-button");

  expect(await screen.findByTestId("signin-screen")).toBeTruthy();
  expect(await screen.findByText(en.deleteAccount.deleted)).toBeTruthy();
  expect(demo.demoSnapshot().profile.displayName).toBeNull();
  expect(deleted).toHaveBeenCalledWith(expect.objectContaining({ success: true, error_code: null }));
  deleted.mockRestore();
}, 30000);

it("a failed deletion keeps the account, shows why with a reference, and records the failure", async () => {
  const deleted = jest.spyOn(analytics, "accountDeleted");
  const fetchSpy = jest.spyOn(demo, "demoFetch");
  await signIn();
  await act(async () => router.push("/delete-account"));
  await fireEvent.changeText(await screen.findByTestId("delete-account-confirm-input"), "DELETE");
  await waitFor(() =>
    expect(screen.getByTestId("delete-account-submit-button").props.accessibilityState?.disabled).toBe(false),
  );
  fetchSpy.mockResolvedValueOnce({ status: 500, body: { error_id: "abcd1234-ffff-4fff-8fff-ffffffffffff" } });
  await pressWhenEnabled("delete-account-submit-button");

  expect(await screen.findByTestId("delete-account-error")).toBeTruthy();
  expect(screen.getByTestId("delete-account-error-reference")).toBeTruthy();
  expect(screen.getByText(en.errors.reference.replace("{{ref}}", "abcd1234"))).toBeTruthy();
  expect(screen.queryByTestId("signin-screen")).toBeNull();
  expect(deleted).toHaveBeenCalledWith(expect.objectContaining({ success: false, error_code: "http_500" }));
  fetchSpy.mockRestore();
  deleted.mockRestore();
}, 30000);

it("once the server deleted the account, a failing local sign-out still signs out and reports success only", async () => {
  const deleted = jest.spyOn(analytics, "accountDeleted");
  demo.demoAuth.signOut(); // the previous test left a signed-in session behind
  demo.resetDemo();
  const ending = jest.spyOn(session, "endSession").mockRejectedValueOnce(new Error("storage unavailable"));
  await signIn();
  await act(async () => router.push("/delete-account"));
  await fireEvent.changeText(await screen.findByTestId("delete-account-confirm-input"), "DELETE");
  await waitFor(() =>
    expect(screen.getByTestId("delete-account-submit-button").props.accessibilityState?.disabled).toBe(false),
  );
  await pressWhenEnabled("delete-account-submit-button");

  // The account IS gone: the user is signed out anyway and told so, never "Nothing was removed".
  expect(await screen.findByTestId("signin-screen")).toBeTruthy();
  expect(await screen.findByText(en.deleteAccount.deleted)).toBeTruthy();
  expect(screen.queryByTestId("delete-account-error")).toBeNull();
  expect(demo.demoSnapshot().profile.displayName).toBeNull();
  expect(deleted).toHaveBeenCalledTimes(1);
  expect(deleted).toHaveBeenCalledWith(expect.objectContaining({ success: true, error_code: null }));
  ending.mockRestore();
  deleted.mockRestore();
}, 30000);
