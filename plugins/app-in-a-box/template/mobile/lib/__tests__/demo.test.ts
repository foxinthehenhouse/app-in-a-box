/**
 * Demo mode goes through the REAL lib/api.ts path (adapters, ApiError, 401
 * handling), so these tests pin both the fake and the error contract.
 */
jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn() }));
jest.mock("../analytics", () => ({ analytics: { apiFailed: jest.fn() }, startTimer: () => () => 0 }));

type Api = typeof import("../api");
type Demo = typeof import("../demo");

function load(demo: "1" | undefined, { dev = true }: { dev?: boolean } = {}): { api: Api; demo: Demo } {
  const prev = process.env.EXPO_PUBLIC_DEMO;
  const g = globalThis as unknown as { __DEV__: boolean };
  const prevDev = g.__DEV__;
  process.env.EXPO_PUBLIC_DEMO = demo;
  g.__DEV__ = dev;
  let mods: { api: Api; demo: Demo } | undefined;
  try {
    jest.isolateModules(() => {
      mods = { api: require("../api") as Api, demo: require("../demo") as Demo };
    });
  } finally {
    process.env.EXPO_PUBLIC_DEMO = prev;
    g.__DEV__ = prevDev;
  }
  if (!mods) throw new Error("modules not loaded");
  return mods;
}

describe("demo mode", () => {
  it("is off unless EXPO_PUBLIC_DEMO is exactly 1", () => {
    expect(load(undefined).demo.DEMO).toBe(false);
    expect(load("1").demo.DEMO).toBe(true);
  });

  it("is off in a release build even if EXPO_PUBLIC_DEMO=1 leaked in (eas env store, a stray .env)", () => {
    expect(load("1", { dev: false }).demo.DEMO).toBe(false);
  });

  it("refuses API calls until signed in, like the real server", async () => {
    const { api } = load("1");
    await expect(api.getMe()).rejects.toMatchObject({ name: "ApiError", status: 401 });
  });

  it("rejects a malformed code, then signs in with any 6 digits and serves the seed", async () => {
    const { api, demo } = load("1");
    expect(demo.demoAuth.verify("a@b.co", "12").error).toMatch(/6-digit/);
    expect(demo.demoAuth.verify("a@b.co", "123456").error).toBeNull();
    await expect(api.getMe()).resolves.toEqual({ id: "demo-user", displayName: "Sam", onboarded: true });
  });

  it("persists a PATCH in memory and adapts it through toProfile", async () => {
    const { api, demo } = load("1");
    demo.demoAuth.verify("a@b.co", "123456");
    await api.updateMe({ displayName: "Riley" });
    await expect(api.getMe()).resolves.toMatchObject({ displayName: "Riley" });
  });

  it("404s an endpoint with no demo handler instead of inventing data", async () => {
    const { api, demo } = load("1");
    demo.demoAuth.verify("a@b.co", "123456");
    await expect(api.apiFetch("/api/v1/nope")).rejects.toMatchObject({ status: 404 });
  });

  it("notifies auth listeners on sign-in and sign-out", () => {
    const { demo } = load("1");
    const seen: (string | null)[] = [];
    const off = demo.demoAuth.subscribe((u) => seen.push(u?.email ?? null));
    demo.demoAuth.verify("a@b.co", "000000");
    demo.demoAuth.signOut();
    off();
    demo.demoAuth.verify("a@b.co", "000000");
    expect(seen).toEqual(["a@b.co", null]);
  });
});

describe("matchDemoRoute (path params + query strings)", () => {
  const keys = ["GET /api/v1/things", "GET /api/v1/things/:id", "POST /api/v1/things/:id/done", "GET /api/v1/things/new"];

  it("prefers an exact key over a pattern", () => {
    const { demo } = load("1");
    expect(demo.matchDemoRoute(keys, "GET", "/api/v1/things/new")?.key).toBe("GET /api/v1/things/new");
  });

  it("fills :params and parses the query string", () => {
    const { demo } = load("1");
    expect(demo.matchDemoRoute(keys, "POST", "/api/v1/things/a%20b/done?on=2026-09-30&x=1+2")).toEqual({
      key: "POST /api/v1/things/:id/done",
      params: { id: "a b" },
      query: { on: "2026-09-30", x: "1 2" },
    });
    expect(demo.matchDemoRoute(keys, "GET", "/api/v1/things?on=2026-09-30")).toMatchObject({
      key: "GET /api/v1/things",
      query: { on: "2026-09-30" },
    });
  });

  it("matches method, segment count and empty segments strictly", () => {
    const { demo } = load("1");
    expect(demo.matchDemoRoute(keys, "DELETE", "/api/v1/things/1")).toBeNull();
    expect(demo.matchDemoRoute(keys, "GET", "/api/v1/things/1/2")).toBeNull();
    expect(demo.matchDemoRoute(keys, "GET", "/api/v1/things/")).toBeNull();
  });
});
