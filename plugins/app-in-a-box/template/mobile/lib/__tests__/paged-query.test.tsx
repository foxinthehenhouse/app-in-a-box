/**
 * usePagedQuery (lib/query.ts): a keyset-paged list as an infinite query. The first
 * page asks with no cursor, each next page passes the previous `nextCursor` back
 * verbatim, and a null cursor ends the list.
 */
import type { ReactNode } from "react";
import { QueryClientProvider, onlineManager } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";

import type { Page } from "../api";
import { makeQueryClient, pageItems, usePagedQuery } from "../query";

jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn(), currentUserId: jest.fn(async () => "u1") }));
jest.mock("../analytics", () => ({ analytics: { apiFailed: jest.fn(), profileUpdated: jest.fn() }, startTimer: () => () => 1 }));

const PAGES: Record<string, Page<string>> = {
  first: { items: ["a", "b"], nextCursor: "c1" },
  c1: { items: ["c", "d"], nextCursor: "c2" },
  c2: { items: ["e"], nextCursor: null },
};

beforeEach(() => onlineManager.setOnline(true));

it("walks the pages by cursor and stops at a null cursor", async () => {
  const client = makeQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const fetchPage = jest.fn(async (cursor: string | null) => PAGES[cursor ?? "first"] as Page<string>);
  const { result } = await renderHook(() => usePagedQuery(["things"], fetchPage), { wrapper });

  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(pageItems(result.current.data)).toEqual(["a", "b"]);
  expect(result.current.hasNextPage).toBe(true);

  await act(async () => {
    await result.current.fetchNextPage();
  });
  await waitFor(() => expect(pageItems(result.current.data)).toHaveLength(4));
  await act(async () => {
    await result.current.fetchNextPage();
  });
  await waitFor(() => expect(pageItems(result.current.data)).toEqual(["a", "b", "c", "d", "e"]));
  expect(result.current.hasNextPage).toBe(false);
  expect(fetchPage.mock.calls.map((c) => c[0])).toEqual([null, "c1", "c2"]);
});

it("pageItems is empty before anything loads", () => {
  expect(pageItems(undefined)).toEqual([]);
});
