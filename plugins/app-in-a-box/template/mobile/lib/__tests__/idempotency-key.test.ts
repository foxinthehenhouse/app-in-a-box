/**
 * Idempotency-Key on the wire (lib/api.ts): a write that passes a key sends it, a call
 * without one sends none, and the key a replay carries is exactly the one it was given.
 * (lib/__tests__/query-resume.test.tsx proves the key survives a restart and is reused.)
 */
jest.mock("../supabase", () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: { access_token: "tok" } } }) } },
  signOutThisDevice: jest.fn(),
}));
jest.mock("../analytics", () => ({ analytics: { apiFailed: jest.fn() }, startTimer: () => () => 7 }));

type Api = typeof import("../api");

function loadApi(): Api {
  process.env.EXPO_PUBLIC_API_URL = "https://api.test/";
  let api: Api | undefined;
  jest.isolateModules(() => {
    api = require("../api") as Api;
  });
  if (!api) throw new Error("api not loaded");
  return api;
}

const fetchMock = jest.fn();
beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({
    status: 200,
    headers: { get: () => null },
    json: async () => ({ id: "u1", displayName: "Sam", onboarded: true }),
  });
  (globalThis as unknown as { fetch: typeof fetchMock }).fetch = fetchMock;
});

function sent(call = 0): { headers: Record<string, string>; body?: string; idempotencyKey?: unknown } {
  return fetchMock.mock.calls[call]?.[1] as { headers: Record<string, string>; body?: string };
}

it("a write with a key sends it as Idempotency-Key, and only as a header", async () => {
  const api = loadApi();
  await api.updateMe({ displayName: "Riley" }, { idempotencyKey: "key-0001-abcd" });
  expect(sent().headers["Idempotency-Key"]).toBe("key-0001-abcd");
  expect(sent().idempotencyKey).toBeUndefined(); // not leaked into fetch's init
  expect(JSON.parse(sent().body ?? "{}")).toEqual({ displayName: "Riley" }); // never in the body (422)
});

it("a call without a key sends none", async () => {
  const api = loadApi();
  await api.updateMe({ displayName: "Riley" });
  await api.getMe();
  expect(sent(0).headers).not.toHaveProperty("Idempotency-Key");
  expect(sent(1).headers).not.toHaveProperty("Idempotency-Key");
});

it("mints keys the backend accepts, a fresh one each time", () => {
  const api = loadApi();
  const a = api.newIdempotencyKey();
  expect(a).toMatch(/^[A-Za-z0-9._:-]{8,128}$/);
  expect(api.newIdempotencyKey()).not.toBe(a);
});

it("pages: toPage adapts items, pagePath adds only what is set", () => {
  const api = loadApi();
  const page = api.toPage({ items: [{ n: 1 }, { n: 2 }], nextCursor: "abc" }, (w: { n: number }) => w.n * 10);
  expect(page).toEqual({ items: [10, 20], nextCursor: "abc" });
  expect(api.toPage({ items: [], nextCursor: null }, (w: unknown) => w).nextCursor).toBeNull();
  expect(api.pagePath("/api/v1/things", null)).toBe("/api/v1/things");
  expect(api.pagePath("/api/v1/things", "a+b/c=", 20)).toBe("/api/v1/things?cursor=a%2Bb%2Fc%3D&limit=20");
  expect(api.pagePath("/api/v1/things?tag=x", null, 5)).toBe("/api/v1/things?tag=x&limit=5");
});
