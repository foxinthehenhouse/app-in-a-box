/**
 * The search screen in demo mode, through the real routes: idle until there's enough
 * to search, results for a match, a no-results state that names the query, and an
 * error with a retry when the server fails. Each state has its own testID.
 */
import { router } from "expo-router";
import { act, fireEvent, renderRouter, screen, waitFor } from "expo-router/testing-library";

import { pressWhenEnabled } from "./support/press";

process.env.EXPO_PUBLIC_DEMO = "1";
const api = require("../lib/api") as typeof import("../lib/api");
const demo = require("../lib/demo") as typeof import("../lib/demo");
const { queryClient } = require("../lib/query") as typeof import("../lib/query");

async function signInAndOpenSearch() {
  await renderRouter("./app", { initialUrl: "/" });
  await fireEvent.changeText(await screen.findByTestId("signin-email-input"), "sam@example.com");
  await pressWhenEnabled("signin-send-button");
  await fireEvent.changeText(await screen.findByTestId("signin-code-input"), "123456");
  await pressWhenEnabled("signin-verify-button");
  await screen.findByTestId("home-screen");
  await act(async () => router.navigate("/search"));
  await screen.findByTestId("search-screen");
}

afterEach(() => {
  jest.restoreAllMocks();
  demo.demoAuth.signOut();
  demo.resetDemo();
  queryClient.clear(); // the next test's search must reach the API, not this one's cache
});

it("goes idle -> results -> no results -> idle as the query changes", async () => {
  await signInAndOpenSearch();
  expect(screen.getByTestId("search-idle")).toBeTruthy();

  await fireEvent.changeText(screen.getByTestId("search-input"), "g");
  expect(screen.getByTestId("search-idle")).toBeTruthy(); // one character is not a search

  await fireEvent.changeText(screen.getByTestId("search-input"), "garden");
  await screen.findByTestId("search-results", {}, { timeout: 3000 });
  expect(screen.getByText("Garden plan")).toBeTruthy();
  expect(screen.getByText("Ideas")).toBeTruthy();
  expect(screen.queryByText("Shopping")).toBeNull();

  await fireEvent.changeText(screen.getByTestId("search-input"), "zzqx");
  await screen.findByTestId("search-empty", {}, { timeout: 3000 });

  await fireEvent.changeText(screen.getByTestId("search-input"), "");
  await screen.findByTestId("search-idle");
}, 30000);

it("shows the error with a retry when the search fails, and recovers", async () => {
  await signInAndOpenSearch();
  // 429 (the route's rate limit): a 4xx, so the query client doesn't retry it away.
  const spy = jest.spyOn(api, "searchItems").mockRejectedValue(new api.ApiError("Request failed (429)", 429));
  await fireEvent.changeText(screen.getByTestId("search-input"), "garden");
  await screen.findByTestId("search-error", {}, { timeout: 3000 });

  spy.mockRestore();
  await pressWhenEnabled("search-error-retry-button");
  await waitFor(() => expect(screen.getByTestId("search-results")).toBeTruthy(), { timeout: 3000 });
}, 30000);
