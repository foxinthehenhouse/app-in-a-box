/**
 * Request ids: every call carries an X-Request-ID, a failure's ApiError carries the
 * id the server logged it under, and the UI shows a short, copyable reference.
 */
jest.mock("../supabase", () => ({
  supabase: { auth: { getSession: async () => ({ data: { session: { access_token: "tok" } } }) } },
  signOutThisDevice: jest.fn(),
}));
jest.mock("../analytics", () => ({ analytics: { apiFailed: jest.fn() }, startTimer: () => () => 7 }));

type Api = typeof import("../api");

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function loadApi(): Api {
  process.env.EXPO_PUBLIC_API_URL = "https://api.test/";
  let api: Api | undefined;
  jest.isolateModules(() => {
    api = require("../api") as Api;
  });
  if (!api) throw new Error("api not loaded");
  return api;
}

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  const lower = Object.fromEntries(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  return {
    status,
    headers: { get: (k: string) => lower[k.toLowerCase()] ?? null },
    json: async () => body,
  };
}

const fetchMock = jest.fn();
beforeEach(() => {
  fetchMock.mockReset();
  (globalThis as unknown as { fetch: typeof fetchMock }).fetch = fetchMock;
});

function sentHeaders(call = 0): Record<string, string> {
  return (fetchMock.mock.calls[call]?.[1] as { headers: Record<string, string> }).headers;
}

it("sends a fresh v4-shaped X-Request-ID on every call, with the bearer token", async () => {
  const api = loadApi();
  fetchMock.mockResolvedValue(respond(200, { id: "u1", displayName: "Sam", onboarded: true }));
  await api.getMe();
  await api.getMe();
  const [a, b] = [sentHeaders(0), sentHeaders(1)];
  expect(fetchMock.mock.calls[0]?.[0]).toBe("https://api.test/api/v1/me");
  expect(a["X-Request-ID"]).toMatch(UUID);
  expect(b["X-Request-ID"]).toMatch(UUID);
  expect(a["X-Request-ID"]).not.toBe(b["X-Request-ID"]);
  expect(a.Authorization).toBe("Bearer tok");
});

it("a caller can't override the request id", async () => {
  const api = loadApi();
  fetchMock.mockResolvedValue(respond(204, undefined));
  await api.apiFetch("/api/v1/x", { method: "POST", headers: { "X-Request-ID": "mine" }, body: "{}" });
  expect(sentHeaders()["X-Request-ID"]).toMatch(UUID);
});

it("puts the server's echoed id on the ApiError", async () => {
  const api = loadApi();
  fetchMock.mockResolvedValue(respond(422, { detail: "nope" }, { "X-Request-ID": "srv-abcdef123456" }));
  const err = await api.getMe().catch((e: unknown) => e);
  expect(err).toBeInstanceOf(api.ApiError);
  expect((err as InstanceType<Api["ApiError"]>).requestId).toBe("srv-abcdef123456");
  expect(api.errorReference(err)).toBe("srvabcde");
});

it("falls back to the id we sent when the server doesn't echo one", async () => {
  const api = loadApi();
  fetchMock.mockResolvedValue(respond(503, null));
  const err = (await api.getMe().catch((e: unknown) => e)) as InstanceType<Api["ApiError"]>;
  expect(err.requestId).toBe(sentHeaders()["X-Request-ID"]);
  expect(api.errorReference(err)).toBe(err.requestId?.replace(/-/g, "").slice(0, 8));
});

it("prefers the 500's error_id (what Sentry is tagged with) for the reference", async () => {
  const api = loadApi();
  fetchMock.mockResolvedValue(
    respond(500, { error_id: "e1e2e3e4-0000-4000-8000-000000000000", request_id: "r1r2r3r4r5" }),
  );
  const err = (await api.getMe().catch((e: unknown) => e)) as InstanceType<Api["ApiError"]>;
  expect(err.errorId).toBe("e1e2e3e4-0000-4000-8000-000000000000");
  expect(err.requestId).toBe("r1r2r3r4r5");
  expect(api.errorReference(err)).toBe("e1e2e3e4");
});

it("has no reference to show when offline (nothing reached the server)", async () => {
  const api = loadApi();
  fetchMock.mockRejectedValue(new TypeError("Network request failed"));
  const err = (await api.getMe().catch((e: unknown) => e)) as InstanceType<Api["ApiError"]>;
  expect(err.status).toBe(0);
  expect(err.requestId).toMatch(UUID);
  expect(api.errorReference(err)).toBeNull();
  expect(api.errorReference(new Error("x"))).toBeNull();
});

// ---- W3C trace context ------------------------------------------------------

const TRACEPARENT = /^00-([0-9a-f]{32})-([0-9a-f]{16})-00$/;

it("sends a W3C traceparent whose trace id is the request id, unsampled", async () => {
  const api = loadApi();
  fetchMock.mockResolvedValue(respond(200, { id: "u1", displayName: "Sam", onboarded: true }));
  await api.getMe();
  const h = sentHeaders();
  const m = TRACEPARENT.exec(h.traceparent ?? "");
  expect(m).not.toBeNull();
  expect(m?.[1]).toBe(h["X-Request-ID"]?.replace(/-/g, ""));
  expect(m?.[2]).not.toBe("0000000000000000");
  // The same ids in the form Sentry's Python SDK continues, with no sampling decision.
  expect(h["sentry-trace"]).toBe(`${m?.[1]}-${m?.[2]}`);
});

it("a fresh span per request, and a caller can't override the trace", async () => {
  const api = loadApi();
  fetchMock.mockResolvedValue(respond(204, undefined));
  await api.apiFetch("/api/v1/x", { method: "POST", headers: { traceparent: "00-mine-mine-01" }, body: "{}" });
  await api.apiFetch("/api/v1/x", { method: "POST", body: "{}" });
  const [a, b] = [sentHeaders(0).traceparent, sentHeaders(1).traceparent];
  expect(a).toMatch(TRACEPARENT);
  expect(b).toMatch(TRACEPARENT);
  expect(a).not.toBe(b);
});

it("traceHeaders never sends an invalid trace id, even for an odd request id", () => {
  const api = loadApi();
  for (const rid of ["not-a-uuid", "00000000-0000-4000-8000-000000000000".replace(/[48]/g, "0")]) {
    expect(api.traceHeaders(rid).traceparent).toMatch(TRACEPARENT);
    expect(api.traceHeaders(rid).traceparent).not.toContain("0".repeat(32));
  }
});
