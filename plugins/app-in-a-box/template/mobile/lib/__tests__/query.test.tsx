/**
 * Offline-first data (lib/query.ts): the optimistic profile edit shows at once,
 * rolls back when the server refuses (with a failure event), queues while offline
 * and replays on reconnect, and connectivity maps NetInfo states correctly.
 */
import type { ReactNode } from "react";
import { QueryClientProvider, onlineManager } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";

import { ApiError, type Profile } from "../api";
import { clearUserCache, isOnlineState, makeQueryClient, queryKeys, shouldRetry, useUpdateMe } from "../query";

jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn() }));
jest.mock("../analytics", () => ({
  analytics: { apiFailed: jest.fn(), profileUpdated: jest.fn() },
  startTimer: () => () => 9,
}));
jest.mock("../api", () => ({
  ...jest.requireActual("../api"),
  getMe: jest.fn(),
  updateMe: jest.fn(),
}));

const api = jest.requireMock("../api") as { getMe: jest.Mock; updateMe: jest.Mock };
const { analytics } = jest.requireMock("../analytics") as { analytics: { profileUpdated: jest.Mock } };

const SAM: Profile = { id: "u1", displayName: "Sam", onboarded: true };

function setup() {
  const client = makeQueryClient();
  client.setQueryData(queryKeys.me, SAM);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  jest.clearAllMocks();
  onlineManager.setOnline(true);
  api.getMe.mockImplementation(async () => SAM);
});

it("shows the new name immediately, then rolls back when the server refuses", async () => {
  const { client, wrapper } = setup();
  const pending = deferred<Profile>();
  api.updateMe.mockReturnValue(pending.promise);
  const { result } = await renderHook(() => useUpdateMe(), { wrapper });

  await act(async () => {
    result.current.mutate({ displayName: "Riley" });
  });
  await waitFor(() => expect(client.getQueryData<Profile>(queryKeys.me)?.displayName).toBe("Riley"));

  await act(async () => pending.reject(new ApiError("too long", 422)));
  await waitFor(() => expect(result.current.isError).toBe(true));
  expect(client.getQueryData<Profile>(queryKeys.me)?.displayName).toBe("Sam");
  expect(analytics.profileUpdated).toHaveBeenCalledWith({ success: false, error_code: "http_422", duration_ms: 9 });
  expect(analytics.profileUpdated).not.toHaveBeenCalledWith(expect.objectContaining({ success: true }));
});

it("keeps the server's version on success and records it", async () => {
  const { client, wrapper } = setup();
  api.updateMe.mockResolvedValue({ ...SAM, displayName: "Riley" });
  api.getMe.mockResolvedValue({ ...SAM, displayName: "Riley" });
  const { result } = await renderHook(() => useUpdateMe(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ displayName: "Riley" });
  });
  expect(client.getQueryData<Profile>(queryKeys.me)?.displayName).toBe("Riley");
  expect(analytics.profileUpdated).toHaveBeenCalledWith({ success: true, error_code: null, duration_ms: 9 });
});

it("offline: applies optimistically, queues, and replays on reconnect", async () => {
  const { client, wrapper } = setup();
  api.updateMe.mockResolvedValue({ ...SAM, displayName: "Riley" });
  onlineManager.setOnline(false);
  const { result } = await renderHook(() => useUpdateMe(), { wrapper });

  await act(async () => {
    result.current.mutate({ displayName: "Riley" });
  });
  await waitFor(() => expect(result.current.isPaused).toBe(true));
  expect(client.getQueryData<Profile>(queryKeys.me)?.displayName).toBe("Riley");
  expect(api.updateMe).not.toHaveBeenCalled();

  await act(async () => onlineManager.setOnline(true));
  await waitFor(() =>
    expect(api.updateMe).toHaveBeenCalledWith({ displayName: "Riley" }, { idempotencyKey: expect.any(String) }),
  );
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
});

it("sign-out forgets cached data and queued edits", async () => {
  const { client } = setup();
  onlineManager.setOnline(false);
  await clearUserCache(client);
  expect(client.getQueryData(queryKeys.me)).toBeUndefined();
  expect(client.getMutationCache().getAll()).toHaveLength(0);
});

describe("pure pieces", () => {
  it("maps NetInfo to online/offline (unknown reachability counts as online)", () => {
    expect(isOnlineState({ isConnected: true, isInternetReachable: true })).toBe(true);
    expect(isOnlineState({ isConnected: true, isInternetReachable: null })).toBe(true);
    expect(isOnlineState({ isConnected: null })).toBe(true);
    expect(isOnlineState({ isConnected: true, isInternetReachable: false })).toBe(false);
    expect(isOnlineState({ isConnected: false, isInternetReachable: null })).toBe(false);
  });

  it("never retries a 4xx, retries network/5xx twice", () => {
    expect(shouldRetry(0, new ApiError("x", 401))).toBe(false);
    expect(shouldRetry(0, new ApiError("x", 422))).toBe(false);
    expect(shouldRetry(0, new ApiError("x", 503))).toBe(true);
    expect(shouldRetry(1, new ApiError("x", 0))).toBe(true);
    expect(shouldRetry(2, new ApiError("x", 0))).toBe(false);
  });
});
