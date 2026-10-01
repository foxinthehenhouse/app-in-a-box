/**
 * A 401 from the backend ends the session with the SAME cleanup as signing out
 * (forget the push token, clear the cache, sign out this device), not a bare
 * sign-out that leaves the device-wide push token for the next user.
 */
jest.mock("../supabase", () => ({
  supabase: { auth: { getSession: jest.fn(async () => ({ data: { session: { access_token: "tok" } } })) } },
  signOutThisDevice: jest.fn(async () => undefined),
  currentUserId: jest.fn(async () => "user-a"),
}));
jest.mock("../analytics", () => ({ analytics: { apiFailed: jest.fn() }, startTimer: () => () => 0 }));
jest.mock("../session", () => ({ endSession: jest.fn(async () => undefined) }));

type Api = typeof import("../api");

const session = jest.requireMock("../session") as { endSession: jest.Mock };

function loadApi(): Api {
  process.env.EXPO_PUBLIC_API_URL = "https://api.example.com";
  let api: Api | undefined;
  jest.isolateModules(() => {
    api = require("../api") as Api;
  });
  if (!api) throw new Error("api not loaded");
  return api;
}

const realFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = realFetch;
});

it("a 401 runs the end-of-session cleanup (no push unregister: it would 401 too), then throws", async () => {
  const api = loadApi();
  globalThis.fetch = jest.fn(async () => ({
    status: 401,
    headers: { get: () => null },
    json: async () => ({ detail: "expired" }),
  })) as unknown as typeof fetch;
  await expect(api.getMe()).rejects.toMatchObject({ name: "ApiError", status: 401 });
  expect(session.endSession).toHaveBeenCalledWith({ unregisterPush: false });
});

it("a failing cleanup still surfaces the 401 to the caller", async () => {
  const api = loadApi();
  session.endSession.mockRejectedValueOnce(new Error("storage"));
  globalThis.fetch = jest.fn(async () => ({
    status: 401,
    headers: { get: () => null },
    json: async () => ({}),
  })) as unknown as typeof fetch;
  await expect(api.getMe()).rejects.toMatchObject({ status: 401 });
});

describe("a late 401 only ends the session it was sent under", () => {
  const supa = jest.requireMock("../supabase") as {
    supabase: { auth: { getSession: jest.Mock } };
    currentUserId: jest.Mock;
  };
  const as = (id: string) => ({ data: { session: { access_token: `tok-${id}`, user: { id } } } });
  const unauthorized = () =>
    jest.fn(async () => ({ status: 401, headers: { get: () => null }, json: async () => ({}) })) as unknown as typeof fetch;

  beforeEach(() => session.endSession.mockClear());

  it("A's request 401s after B signed in: B stays signed in", async () => {
    const api = loadApi();
    supa.supabase.auth.getSession.mockResolvedValueOnce(as("user-a")); // the request carries A's token
    supa.currentUserId.mockResolvedValueOnce("user-b"); // …but B is signed in when it answers
    globalThis.fetch = unauthorized();
    await expect(api.getMe()).rejects.toMatchObject({ status: 401 });
    expect(session.endSession).not.toHaveBeenCalled();
  });

  it("the signed-in user's own request 401s: their session ends", async () => {
    const api = loadApi();
    supa.supabase.auth.getSession.mockResolvedValueOnce(as("user-a"));
    supa.currentUserId.mockResolvedValueOnce("user-a");
    globalThis.fetch = unauthorized();
    await expect(api.getMe()).rejects.toMatchObject({ status: 401 });
    expect(session.endSession).toHaveBeenCalledWith({ unregisterPush: false });
  });
});
