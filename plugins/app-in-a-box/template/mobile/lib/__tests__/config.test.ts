/**
 * lib/config says which shipping-build settings are MISSING, so a half-provisioned build
 * reports "misconfigured" instead of pretending the network is down. The module reads
 * process.env at import time, so each case re-requires it under a fresh environment.
 */
const VARS = ["EXPO_PUBLIC_API_URL", "EXPO_PUBLIC_SUPABASE_URL", "EXPO_PUBLIC_SUPABASE_ANON_KEY"];

function load(env: Record<string, string | undefined>) {
  jest.resetModules();
  const saved: Record<string, string | undefined> = {};
  for (const k of [...VARS, "EXPO_PUBLIC_DEMO"]) {
    saved[k] = process.env[k];
    if (env[k] === undefined) delete process.env[k];
    else process.env[k] = env[k];
  }
  try {
    return require("../config") as typeof import("../config");
  } finally {
    for (const k of Object.keys(saved)) {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    }
  }
}

describe("lib/config", () => {
  it("is configured when every shipping setting is present", () => {
    const c = load({
      EXPO_PUBLIC_API_URL: "https://api.example.com",
      EXPO_PUBLIC_SUPABASE_URL: "https://x.supabase.co",
      EXPO_PUBLIC_SUPABASE_ANON_KEY: "anon",
    });
    expect(c.MISSING_CONFIG).toEqual([]);
    expect(c.configured).toBe(true);
  });

  it("names exactly the settings a build is missing", () => {
    const c = load({ EXPO_PUBLIC_SUPABASE_URL: "https://x.supabase.co" });
    expect(c.MISSING_CONFIG).toEqual(["EXPO_PUBLIC_API_URL", "EXPO_PUBLIC_SUPABASE_ANON_KEY"]);
    expect(c.configured).toBe(false);
  });

  it("reports nothing missing in demo mode, which needs no backend", () => {
    const c = load({ EXPO_PUBLIC_DEMO: "1" });
    expect(c.MISSING_CONFIG).toEqual([]);
    expect(c.configured).toBe(true);
  });
});
