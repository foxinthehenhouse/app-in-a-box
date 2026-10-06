/**
 * Search (lib/search.ts): typing is debounced before it reaches the API, short input
 * never does, and every first page leaves a success or failure event that carries
 * counts, never the query text.
 */
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider, onlineManager } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";

import { ApiError, type SearchPage } from "../api";
import { SEARCH_DEBOUNCE_MS, fetchSearchPage, normaliseQuery, useDebouncedValue, useSearch } from "../search";

jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn() }));
jest.mock("../analytics", () => ({
  analytics: { apiFailed: jest.fn(), searchPerformed: jest.fn(), searchFailed: jest.fn() },
  startTimer: () => () => 7,
}));
jest.mock("../api", () => ({ ...jest.requireActual("../api"), searchItems: jest.fn() }));

const api = jest.requireMock("../api") as { searchItems: jest.Mock };
const { analytics } = jest.requireMock("../analytics") as {
  analytics: { searchPerformed: jest.Mock; searchFailed: jest.Mock };
};

const PAGE: SearchPage = {
  items: [{ id: "a1", title: "Garden plan", snippet: "tomatoes by the fence" }],
  nextCursor: "c1",
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  jest.clearAllMocks();
  onlineManager.setOnline(true);
  api.searchItems.mockResolvedValue(PAGE);
});

afterEach(() => {
  jest.useRealTimers();
});

it("normalises the query and drops input too short to send", () => {
  expect(normaliseQuery("  tomato   paste ")).toBe("tomato paste");
  expect(normaliseQuery(" t ")).toBe("");
  expect(normaliseQuery("")).toBe("");
});

it("settles on the last value once typing pauses", async () => {
  jest.useFakeTimers();
  const { result, rerender } = await renderHook(({ v }: { v: string }) => useDebouncedValue(v, 300), {
    initialProps: { v: "t" },
  });
  await rerender({ v: "to" });
  await rerender({ v: "tom" });
  expect(result.current).toBe("t");
  await act(async () => {
    jest.advanceTimersByTime(299);
  });
  expect(result.current).toBe("t");
  await act(async () => {
    jest.advanceTimersByTime(1);
  });
  expect(result.current).toBe("tom");
});

it("sends one request for a burst of typing, and none for a single character", async () => {
  jest.useFakeTimers();
  const { result, rerender } = await renderHook(({ q }: { q: string }) => useSearch(q), {
    initialProps: { q: "g" },
    wrapper,
  });
  await act(async () => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
  });
  expect(api.searchItems).not.toHaveBeenCalled();
  expect(result.current.query).toBe("");

  for (const q of ["ga", "gar", "gard", "garden"]) await rerender({ q });
  expect(result.current.settling).toBe(true);
  await act(async () => {
    jest.advanceTimersByTime(SEARCH_DEBOUNCE_MS);
  });
  await act(async () => {
    await jest.runOnlyPendingTimersAsync();
  });
  await waitFor(() => expect(result.current.items).toEqual(PAGE.items));
  expect(api.searchItems).toHaveBeenCalledTimes(1);
  expect(api.searchItems).toHaveBeenCalledWith("garden", null);
  expect(result.current.hasNextPage).toBe(true);
});

it("fires search_performed for a first page, with counts and no query text", async () => {
  await fetchSearchPage("garden", null);
  expect(analytics.searchPerformed).toHaveBeenCalledWith({
    query_length: 6,
    results: 1,
    has_more: true,
    success: true,
    duration_ms: 7,
  });
  expect(JSON.stringify(analytics.searchPerformed.mock.calls)).not.toContain("garden");
});

it("does not count a next page as another search", async () => {
  await fetchSearchPage("garden", "c1");
  expect(api.searchItems).toHaveBeenCalledWith("garden", "c1");
  expect(analytics.searchPerformed).not.toHaveBeenCalled();
});

it("fires search_failed with the error code, and still throws for the screen", async () => {
  api.searchItems.mockRejectedValueOnce(new ApiError("Request failed (503)", 503));
  await expect(fetchSearchPage("garden", null)).rejects.toBeInstanceOf(ApiError);
  expect(analytics.searchFailed).toHaveBeenCalledWith({
    query_length: 6,
    page: "first",
    success: false,
    error_code: "http_503",
    duration_ms: 7,
  });

  api.searchItems.mockRejectedValueOnce(new ApiError("Network error", 0));
  await expect(fetchSearchPage("garden", "c1")).rejects.toBeInstanceOf(ApiError);
  expect(analytics.searchFailed).toHaveBeenLastCalledWith(
    expect.objectContaining({ page: "next", error_code: "offline" }),
  );
  expect(analytics.searchPerformed).not.toHaveBeenCalled();
});
