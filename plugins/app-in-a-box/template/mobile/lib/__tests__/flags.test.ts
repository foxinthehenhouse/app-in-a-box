/**
 * Flags (lib/flags.ts): the PostHog client is bootstrapped with every flag's safe
 * default, a flag reads PostHog's answer in its own type, and anything odd (no key,
 * an unknown answer, a throwing SDK) falls back to the default instead of crashing.
 */
import { act, renderHook } from "@testing-library/react-native";

import { FLAGS, flag, flagDefaults, useFlag } from "../flags";

const listeners: (() => void)[] = [];
const mockFlags: { answer: unknown } = { answer: undefined };
const mockPosthog = {
  getFeatureFlag: jest.fn((_key: string): unknown => mockFlags.answer),
  onFeatureFlags: jest.fn((cb: () => void) => {
    listeners.push(cb);
    return () => listeners.splice(listeners.indexOf(cb), 1);
  }),
};
// The client lib/analytics.ts would export: null is "no PostHog key" (dev, demo).
const mockClient: { current: typeof mockPosthog | null } = { current: mockPosthog };
jest.mock("../analytics", () => ({
  get posthog() {
    return mockClient.current;
  },
}));
const MockPostHog = jest.fn((..._args: unknown[]) => mockPosthog);
jest.mock("posthog-react-native", () => ({ __esModule: true, default: MockPostHog }));

beforeEach(() => {
  mockFlags.answer = undefined;
  mockClient.current = mockPosthog;
  mockPosthog.getFeatureFlag.mockClear();
  listeners.length = 0;
});

it("every flag declares an owner, an expiry and a safe default; kill switches default off", () => {
  expect(Object.keys(FLAGS).length).toBeGreaterThan(0);
  for (const [name, spec] of Object.entries(FLAGS)) {
    expect(spec.owner).toMatch(/^@\S+$/);
    expect(spec.expires).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    if ("killSwitch" in spec) {
      expect(name.startsWith("kill-")).toBe(true);
      expect(spec.default).toBe(false);
    }
    expect(flagDefaults()[name]).toBe(spec.default);
  }
});

it("bootstraps the PostHog client with the defaults, so the first read has an answer", () => {
  process.env.EXPO_PUBLIC_POSTHOG_API_KEY = "phc_test";
  jest.isolateModules(() => {
    jest.requireActual("../analytics");
  });
  const options = MockPostHog.mock.calls[0]?.[1] as { bootstrap?: { featureFlags?: unknown } };
  expect(options.bootstrap?.featureFlags).toEqual(flagDefaults());
  delete process.env.EXPO_PUBLIC_POSTHOG_API_KEY;
});

it("with no PostHog client (no key: dev, demo), every flag is its default", () => {
  mockClient.current = null;
  expect(flag("kill-push")).toBe(false);
});

it("reads PostHog's answer in the flag's own type", () => {
  mockFlags.answer = true;
  expect(flag("kill-push")).toBe(true);
  expect(mockPosthog.getFeatureFlag).toHaveBeenCalledWith("kill-push");
  mockFlags.answer = "variant-b"; // a multivariate answer counts as on
  expect(flag("kill-push")).toBe(true);
  mockFlags.answer = false;
  expect(flag("kill-push")).toBe(false);
});

it("falls back to the default on no answer, a junk answer or a throwing SDK", () => {
  mockFlags.answer = undefined;
  expect(flag("kill-push")).toBe(false);
  mockFlags.answer = 42;
  expect(flag("kill-push")).toBe(false);
  mockPosthog.getFeatureFlag.mockImplementationOnce(() => {
    throw new Error("sdk down");
  });
  expect(flag("kill-push")).toBe(false);
});

it("useFlag re-renders when PostHog loads new flags, and unsubscribes on unmount", async () => {
  const { result, unmount } = await renderHook(() => useFlag("kill-push"));
  expect(result.current).toBe(false);
  mockFlags.answer = true;
  await act(async () => listeners.forEach((cb) => cb()));
  expect(result.current).toBe(true);
  await unmount();
  expect(listeners).toHaveLength(0);
});
