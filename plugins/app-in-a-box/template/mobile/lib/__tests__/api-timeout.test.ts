/**
 * A request on a bad network must give up, not spin forever: after DEFAULT_TIMEOUT_MS
 * (or the call's own `timeoutMs`) it fails as offline, which every screen already
 * shows with Retry and the query client retries. The timer covers the body too.
 */
jest.mock("../supabase", () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: { access_token: "tok" } } }) } },
  signOutThisDevice: jest.fn(),
  currentUserId: jest.fn(async () => undefined),
}));
jest.mock("../analytics", () => ({ analytics: { apiFailed: jest.fn() }, startTimer: () => () => 15_000 }));

type Api = typeof import("../api");
const { analytics } = jest.requireMock("../analytics") as { analytics: { apiFailed: jest.Mock } };

function loadApi(): Api {
  process.env.EXPO_PUBLIC_API_URL = "https://api.test";
  let api: Api | undefined;
  jest.isolateModules(() => {
    api = require("../api") as Api;
  });
  if (!api) throw new Error("api not loaded");
  return api;
}

/** A fetch that never answers, and rejects like the real one when its signal aborts. */
function hangingFetch(init?: RequestInit): Promise<never> {
  return new Promise((_, reject) => {
    init?.signal?.addEventListener("abort", () => reject(Object.assign(new Error("Aborted"), { name: "AbortError" })));
  });
}

const fetchMock = jest.fn();
beforeEach(() => {
  jest.useFakeTimers();
  fetchMock.mockReset();
  analytics.apiFailed.mockClear();
  (globalThis as unknown as { fetch: typeof fetchMock }).fetch = fetchMock;
});
afterEach(() => {
  jest.useRealTimers();
});

/** Start a call and record how it settles, without awaiting it. */
function track<T>(p: Promise<T>) {
  const state: { done: boolean; error?: unknown } = { done: false };
  p.then(
    () => (state.done = true),
    (e: unknown) => Object.assign(state, { done: true, error: e }),
  );
  return state;
}

it("fails a hung request as offline after 15 seconds, with reason 'timeout'", async () => {
  const api = loadApi();
  expect(api.DEFAULT_TIMEOUT_MS).toBe(15_000);
  fetchMock.mockImplementation((_url: string, init?: RequestInit) => hangingFetch(init));
  const call = track(api.getMe());

  await jest.advanceTimersByTimeAsync(14_900);
  expect(call.done).toBe(false);
  await jest.advanceTimersByTimeAsync(200);

  expect(call.done).toBe(true);
  const err = call.error as InstanceType<Api["ApiError"]>;
  expect(err).toBeInstanceOf(api.ApiError);
  expect(err.status).toBe(0);
  expect(err.reason).toBe("timeout");
  expect(err.message).toBe("Request timed out after 15s");
  expect(api.errorMessage(err)).toBe("You're offline or the server is unreachable.");
  expect(analytics.apiFailed).toHaveBeenCalledWith({ path: "/api/v1/me", status: 0, duration_ms: 15_000 });
});

it("honours a per-call timeoutMs", async () => {
  const api = loadApi();
  fetchMock.mockImplementation((_url: string, init?: RequestInit) => hangingFetch(init));
  const call = track(api.apiFetch("/api/v1/slow", { timeoutMs: 1_000 }));
  await jest.advanceTimersByTimeAsync(1_000);
  expect((call.error as InstanceType<Api["ApiError"]>).reason).toBe("timeout");
  expect(fetchMock.mock.calls[0]?.[1]).not.toHaveProperty("timeoutMs"); // never sent to fetch
});

it("times out a response whose body stalls after the headers", async () => {
  const api = loadApi();
  fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => ({
    status: 200,
    headers: { get: () => null },
    json: () => hangingFetch(init),
  }));
  const call = track(api.getMe());
  await jest.advanceTimersByTimeAsync(15_000);
  expect((call.error as InstanceType<Api["ApiError"]>).reason).toBe("timeout");
});

it("a caller's own abort still aborts, and isn't reported as a timeout", async () => {
  const api = loadApi();
  fetchMock.mockImplementation((_url: string, init?: RequestInit) => hangingFetch(init));
  const controller = new AbortController();
  const call = track(api.apiFetch("/api/v1/x", { signal: controller.signal }));
  await jest.advanceTimersByTimeAsync(10);
  controller.abort();
  await jest.advanceTimersByTimeAsync(0);
  const err = call.error as InstanceType<Api["ApiError"]>;
  expect(err.status).toBe(0);
  expect(err.reason).toBeUndefined();
});

it("clears its timer once the response arrives", async () => {
  const api = loadApi();
  fetchMock.mockResolvedValue({
    status: 200,
    headers: { get: () => null },
    json: async () => ({ id: "u1", displayName: "Sam", onboarded: true }),
  });
  await expect(api.getMe()).resolves.toEqual({ id: "u1", displayName: "Sam", onboarded: true });
  expect(jest.getTimerCount()).toBe(0);
});
