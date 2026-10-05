/**
 * A crash in an OTA update must be findable and readable: Sentry's release names the
 * update that was running (one release per update, so each has its own crash-free
 * sessions for the staged rollout's promote step), dist is the build, and the scope
 * carries the update id. The build's own bundle keeps Sentry's native release name.
 */
// One shared object per module (names start with `mock` so jest allows them in a
// factory): jest.isolateModules re-runs factories, and each run must see the same values.
const mockSentry = { init: jest.fn(), withScope: jest.fn(), captureException: jest.fn(), wrap: (c: unknown) => c };
const APP = { applicationId: "com.example.app", nativeApplicationVersion: "1.4.0", nativeBuildVersion: "42" };
const OTA = {
  isEmbeddedLaunch: false,
  updateId: "0f3c9a7e-1111-4222-8333-444455556666",
  runtimeVersion: "fp-abc123",
  channel: "production",
  manifest: { metadata: { updateGroup: "group-789" } },
};
const mockApplication: Record<string, unknown> = { ...APP };
const mockUpdates: Record<string, unknown> = { ...OTA };
jest.mock("@sentry/react-native", () => mockSentry);
jest.mock("expo-application", () => mockApplication);
jest.mock("expo-updates", () => mockUpdates);

type Monitoring = typeof import("../monitoring");

function load(dsn = "https://key@o1.ingest.sentry.io/1"): Monitoring {
  process.env.EXPO_PUBLIC_SENTRY_DSN = dsn;
  let m: Monitoring | undefined;
  jest.isolateModules(() => {
    m = require("../monitoring") as Monitoring;
  });
  if (!m) throw new Error("monitoring not loaded");
  return m;
}

const g = globalThis as unknown as { __DEV__: boolean };
const prevDev = g.__DEV__;
beforeEach(() => {
  mockSentry.init.mockReset();
  Object.assign(mockUpdates, OTA);
  Object.assign(mockApplication, APP);
  g.__DEV__ = false;
});
afterAll(() => {
  g.__DEV__ = prevDev;
  delete process.env.EXPO_PUBLIC_SENTRY_DSN;
});

it("names the running OTA update in the release and tags its id, group, runtime and channel", () => {
  load().initMonitoring();
  expect(mockSentry.init).toHaveBeenCalledTimes(1);
  const opts = mockSentry.init.mock.calls[0]?.[0] as Record<string, unknown>;
  expect(opts.release).toBe("com.example.app@1.4.0+0f3c9a7e-1111-4222-8333-444455556666");
  expect(opts.dist).toBe("42");
  expect(opts.initialScope).toEqual({
    tags: {
      "expo-update-id": "0f3c9a7e-1111-4222-8333-444455556666",
      "expo-update-group-id": "group-789",
      "expo-runtime-version": "fp-abc123",
      "expo-channel": "production",
      "expo-is-embedded-update": "false",
    },
  });
  // the privacy defaults survive
  expect(opts).toMatchObject({ sendDefaultPii: false, attachScreenshot: false, attachViewHierarchy: false });
});

it("keeps Sentry's native release name on the bundle the build shipped with", () => {
  Object.assign(mockUpdates, { isEmbeddedLaunch: true, updateId: "embedded-id", manifest: {} });
  const info = load().releaseInfo();
  expect(info.release).toBe("com.example.app@1.4.0+42");
  expect(info.dist).toBe("42");
  expect(info.tags["expo-is-embedded-update"]).toBe("true");
  expect(info.tags["expo-update-id"]).toBe("embedded-id");
  expect(info.tags["expo-update-group-id"]).toBeUndefined();
});

it("invents nothing where the platform reports nothing (web, updates off)", () => {
  Object.assign(mockApplication, { applicationId: null, nativeApplicationVersion: null, nativeBuildVersion: null });
  Object.assign(mockUpdates, { isEmbeddedLaunch: true, updateId: null, runtimeVersion: null, channel: null, manifest: {} });
  load().initMonitoring();
  const opts = mockSentry.init.mock.calls[0]?.[0] as Record<string, unknown>;
  expect(opts).not.toHaveProperty("release");
  expect(opts).not.toHaveProperty("dist");
  expect(opts.initialScope).toEqual({ tags: { "expo-is-embedded-update": "true" } });
});

it("is a no-op without a DSN and in dev builds", () => {
  load("").initMonitoring();
  g.__DEV__ = true;
  load().initMonitoring();
  expect(mockSentry.init).not.toHaveBeenCalled();
});
