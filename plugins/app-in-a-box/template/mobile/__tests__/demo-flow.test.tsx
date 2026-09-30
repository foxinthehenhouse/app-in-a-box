/**
 * End-to-end-in-jest: the real routes, providers and auth guard, running in demo
 * mode. Proves a fresh scaffold boots with zero accounts: sign-in -> home (with
 * the seeded profile) -> settings -> sign out. Maestro covers the device side.
 */
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

// Set before the routes (and lib/demo.ts) are required by renderRouter.
process.env.EXPO_PUBLIC_DEMO = "1";

it("signs in with any 6-digit code and lands on home with seeded data", async () => {
  await renderRouter("./app", { initialUrl: "/" });

  // Signed out: the Stack.Protected guard shows sign-in, with the demo hint.
  expect(await screen.findByTestId("signin-screen")).toBeTruthy();
  expect(screen.getByTestId("signin-demo-badge")).toBeTruthy();

  await fireEvent.changeText(screen.getByTestId("signin-email-input"), "sam@example.com");
  await fireEvent.press(screen.getByTestId("signin-send-button"));
  await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
  await fireEvent.press(screen.getByTestId("signin-verify-button"));

  // Signed in: the guard swaps to the tabs, home loads the seeded profile.
  expect(await screen.findByTestId("home-screen")).toBeTruthy();
  await waitFor(() => expect(screen.getByText("Hi, Sam")).toBeTruthy());

  // The sheet opens seeded with the REAL name (not a blank captured at mount),
  // saves through the demo backend, closes, and confirms with a toast.
  await act(async () => router.push("/edit-name"));
  const input = await screen.findByTestId("edit-name-input");
  expect(input.props.value).toBe("Sam");
  await fireEvent.changeText(input, "Riley");
  await fireEvent.press(screen.getByTestId("edit-name-save-button"));
  expect(await screen.findByTestId("toast-success")).toBeTruthy();

  // Settings reflects the change on focus, then sign-out returns to sign-in.
  await act(async () => router.navigate("/settings"));
  expect(await screen.findByTestId("settings-screen")).toBeTruthy();
  await waitFor(() => expect(screen.getByTestId("settings-name-row").props.accessibilityLabel).toMatch(/Riley/));
  await fireEvent.press(screen.getByTestId("settings-signout-button"));
  expect(await screen.findByTestId("signin-screen")).toBeTruthy();
}, 30000);
