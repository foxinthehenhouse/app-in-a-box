/**
 * Sign-in (demo mode, the real route): the email is locked once a code is sent
 * (the code belongs to THAT address) with an explicit way back, and auth errors
 * are shown as translated copy, never Supabase's raw English.
 */
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { pressWhenEnabled } from "./support/press";

import { en } from "../locales/en";

// Set before the routes (and lib/demo.ts) are required by renderRouter.
process.env.EXPO_PUBLIC_DEMO = "1";
// Required (not imported) so it loads AFTER the line above: imports are hoisted.
const demo = require("../lib/demo") as typeof import("../lib/demo");
const auth = require("../lib/auth") as typeof import("../lib/auth");

async function sendCode(email = "sam@example.com") {
  await renderRouter("./app", { initialUrl: "/" });
  await fireEvent.changeText(await screen.findByTestId("signin-email-input"), email);
  await pressWhenEnabled("signin-send-button");
  await screen.findByTestId("signin-code-input");
}

afterEach(() => {
  jest.restoreAllMocks();
  demo.demoAuth.signOut();
  demo.resetDemo();
});

it("locks the email once the code is sent, with a way to use a different one", async () => {
  await sendCode();
  expect(screen.getByTestId("signin-email-input").props.editable).toBe(false);

  await fireEvent.press(screen.getByTestId("signin-change-email-button"));
  expect(screen.queryByTestId("signin-code-input")).toBeNull();
  expect(screen.getByTestId("signin-email-input").props.editable).not.toBe(false);
  expect(screen.getByTestId("signin-send-button")).toBeTruthy();
});

it("shows a translated message for an auth error, never the raw server text", async () => {
  const raw = "Token has expired or is invalid";
  jest.spyOn(demo.demoAuth, "verify").mockReturnValue({ error: raw });
  await sendCode();
  await fireEvent.changeText(screen.getByTestId("signin-code-input"), "123456");
  await pressWhenEnabled("signin-verify-button");
  await waitFor(() => expect(demo.demoAuth.verify).toHaveBeenCalled());
  await act(async () => undefined); // let the error render
  // ErrorText prefixes a warning glyph, hence exact: false.
  expect(screen.queryByText(raw, { exact: false })).toBeNull();
  expect(await screen.findByText(en.auth.errors.expired, { exact: false })).toBeTruthy();
});

describe("authErrorCode", () => {
  it.each([
    [{ code: "otp_expired", status: 403, message: "Token has expired or is invalid" }, "expired"],
    [{ code: "over_email_send_rate_limit", status: 429, message: "email rate limit exceeded" }, "rateLimited"],
    [{ status: 429, message: "Too many requests" }, "rateLimited"],
    [{ code: "email_address_invalid", status: 400, message: "Email address is invalid" }, "invalidEmail"],
    [{ name: "AuthRetryableFetchError", status: 0, message: "Failed to fetch" }, "network"],
    [{ message: "something new" }, "generic"],
  ])("maps %j -> %s", (err, want) => {
    expect(auth.authErrorCode(err)).toBe(want);
  });

  it("uses the caller's fallback for an unknown verify error, and null for none", () => {
    expect(auth.authErrorCode({ message: "nope" }, "invalidCode")).toBe("invalidCode");
    expect(auth.authErrorCode(null)).toBeNull();
  });
});
