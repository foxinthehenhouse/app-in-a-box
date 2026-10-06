/**
 * An edit queued offline survives a restart WITH its behaviour, not just its request:
 * the persisted mutation is rebuilt from `setMutationDefaults`, so when it replays
 * against a refusing server it still rolls the optimistic value back and still fires
 * the failure event. (A default of only `mutationFn` replays silently: no rollback, no
 * event; that is the bug this pins.)
 */
import type { ReactNode } from "react";
import { QueryClientProvider, dehydrate, hydrate, onlineManager } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react-native";

import { ApiError, type Profile } from "../api";
import { makeQueryClient, mutationKeys, queryClient, queryKeys, useUpdateMe } from "../query";

jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn(), currentUserId: jest.fn(async () => "u1") }));
jest.mock("../analytics", () => ({
  analytics: { apiFailed: jest.fn(), profileUpdated: jest.fn() },
  startTimer: () => () => 9,
}));
jest.mock("../api", () => ({ ...jest.requireActual("../api"), getMe: jest.fn(), updateMe: jest.fn() }));

const api = jest.requireMock("../api") as { getMe: jest.Mock; updateMe: jest.Mock };
const { analytics } = jest.requireMock("../analytics") as { analytics: { profileUpdated: jest.Mock } };
const SAM: Profile = { id: "u1", displayName: "Sam", onboarded: true };

beforeEach(() => {
  jest.clearAllMocks();
  onlineManager.setOnline(true);
  api.getMe.mockResolvedValue(SAM);
});

it("the MODULE-LEVEL client (the one the app uses) carries the full option set, not just mutationFn", () => {
  // `queryClient` is built at import time; a default declared after it would arrive as
  // undefined with no error. Asserting on a fresh makeQueryClient() cannot see that.
  const d = queryClient.getMutationDefaults(mutationKeys.updateMe);
  for (const k of ["mutationFn", "onMutate", "onError", "onSuccess", "onSettled"] as const) expect(typeof d[k]).toBe("function");
  expect(d.scope).toEqual({ id: "me" });
});

it("a paused edit replayed after a restart rolls back and reports when the server refuses", async () => {
  // Session 1: offline edit, paused.
  const before = makeQueryClient();
  before.setQueryData(queryKeys.me, SAM);
  onlineManager.setOnline(false);
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={before}>{children}</QueryClientProvider>;
  const { result } = await renderHook(() => useUpdateMe(), { wrapper });
  await act(async () => {
    result.current.mutate({ displayName: "Riley" });
  });
  await waitFor(() => expect(result.current.isPaused).toBe(true));

  // The app is killed: what the persister wrote is JSON (functions are gone).
  const onDisk = JSON.parse(JSON.stringify(dehydrate(before))) as ReturnType<typeof dehydrate>;
  before.getMutationCache().clear(); // this process is "dead"
  expect(onDisk.mutations).toHaveLength(1);
  expect(onDisk.mutations[0]?.scope).toEqual({ id: "me" });

  // Session 2: restore, come back online, and the server says no.
  const after = makeQueryClient();
  hydrate(after, onDisk);
  expect(after.getQueryData<Profile>(queryKeys.me)?.displayName).toBe("Riley"); // the optimistic value was persisted
  api.updateMe.mockRejectedValue(new ApiError("too long", 422));
  onlineManager.setOnline(true);
  await act(async () => {
    await after.resumePausedMutations();
  });

  // The replay carries the Idempotency-Key minted when the user saved, from disk.
  const persisted = onDisk.mutations[0]?.state.variables as { idempotencyKey: string };
  expect(persisted.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
  expect(api.updateMe).toHaveBeenCalledWith({ displayName: "Riley" }, { idempotencyKey: persisted.idempotencyKey });
  expect(after.getQueryData<Profile>(queryKeys.me)?.displayName).toBe("Sam"); // rolled back
  expect(analytics.profileUpdated).toHaveBeenCalledWith({ success: false, error_code: "http_422", duration_ms: 0 });
});

it("a paused edit replayed after a restart that succeeds records success", async () => {
  const before = makeQueryClient();
  before.setQueryData(queryKeys.me, SAM);
  onlineManager.setOnline(false);
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={before}>{children}</QueryClientProvider>;
  const { result } = await renderHook(() => useUpdateMe(), { wrapper });
  await act(async () => {
    result.current.mutate({ displayName: "Riley" });
  });
  await waitFor(() => expect(result.current.isPaused).toBe(true));
  const onDisk = JSON.parse(JSON.stringify(dehydrate(before))) as ReturnType<typeof dehydrate>;
  before.getMutationCache().clear();

  const after = makeQueryClient();
  hydrate(after, onDisk);
  api.updateMe.mockResolvedValue({ ...SAM, displayName: "Riley" });
  api.getMe.mockResolvedValue({ ...SAM, displayName: "Riley" });
  onlineManager.setOnline(true);
  await act(async () => {
    await after.resumePausedMutations();
  });
  expect(after.getQueryData<Profile>(queryKeys.me)?.displayName).toBe("Riley");
  expect(analytics.profileUpdated).toHaveBeenCalledWith({ success: true, error_code: null, duration_ms: 0 });
});

it("a replay that runs again after the app died mid-request sends the SAME key (the server answers it once)", async () => {
  // The worst case the key exists for: the replay reached the server and committed, and
  // the app died before the response, so the paused mutation is still on disk.
  const before = makeQueryClient();
  before.setQueryData(queryKeys.me, SAM);
  onlineManager.setOnline(false);
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={before}>{children}</QueryClientProvider>;
  const { result } = await renderHook(() => useUpdateMe(), { wrapper });
  await act(async () => {
    result.current.mutate({ displayName: "Riley" });
  });
  await waitFor(() => expect(result.current.isPaused).toBe(true));
  const onDisk = JSON.parse(JSON.stringify(dehydrate(before))) as ReturnType<typeof dehydrate>;
  before.getMutationCache().clear();

  api.updateMe.mockResolvedValue({ ...SAM, displayName: "Riley" });
  for (let restart = 0; restart < 2; restart++) {
    const after = makeQueryClient();
    hydrate(after, onDisk);
    onlineManager.setOnline(true);
    await act(async () => {
      await after.resumePausedMutations();
    });
  }
  const keys = api.updateMe.mock.calls.map((c) => (c[1] as { idempotencyKey: string }).idempotencyKey);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});

it("two saves are two intents: each gets its own key", async () => {
  const client = makeQueryClient();
  client.setQueryData(queryKeys.me, SAM);
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  api.updateMe.mockResolvedValue(SAM);
  const { result, unmount } = await renderHook(() => useUpdateMe(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ displayName: "A" });
    await result.current.mutateAsync({ displayName: "B" });
  });
  await act(async () => unmount()); // no late cache notifications after the test
  const [a, b] = api.updateMe.mock.calls.map((c) => (c[1] as { idempotencyKey: string }).idempotencyKey);
  expect(a).toBeTruthy();
  expect(a).not.toBe(b);
});

it("a write queued by a build from before keys still replays (as its bare patch, without a key)", async () => {
  const before = makeQueryClient();
  before.setQueryData(queryKeys.me, SAM);
  onlineManager.setOnline(false);
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={before}>{children}</QueryClientProvider>;
  const { result } = await renderHook(() => useUpdateMe(), { wrapper });
  await act(async () => {
    result.current.mutate({ displayName: "Riley" });
  });
  await waitFor(() => expect(result.current.isPaused).toBe(true));
  const onDisk = JSON.parse(JSON.stringify(dehydrate(before))) as ReturnType<typeof dehydrate>;
  before.getMutationCache().clear();
  // What the previous build persisted: the patch itself as the variables.
  (onDisk.mutations[0] as { state: { variables: unknown } }).state.variables = { displayName: "Riley" };

  const after = makeQueryClient();
  hydrate(after, onDisk);
  api.updateMe.mockResolvedValue({ ...SAM, displayName: "Riley" });
  onlineManager.setOnline(true);
  await act(async () => {
    await after.resumePausedMutations();
  });
  expect(api.updateMe).toHaveBeenCalledWith({ displayName: "Riley" }, { idempotencyKey: undefined });
});
