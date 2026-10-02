/**
 * Opt-in/out is recorded in the only order that leaves a trail: an opt-in is captured
 * AFTER posthog.optIn() (captured before, the SDK drops it as opted out); an opt-out is
 * captured BEFORE posthog.optOut(). And the read comes from the SDK's flag, after ready().
 */
process.env.EXPO_PUBLIC_POSTHOG_API_KEY = "phc_test";

const calls: string[] = [];
const mockPosthog = {
  optedOut: false,
  ready: jest.fn(async () => {
    calls.push("ready");
  }),
  optIn: jest.fn(async () => {
    calls.push("optIn");
    mockPosthog.optedOut = false;
  }),
  optOut: jest.fn(async () => {
    calls.push("optOut");
    mockPosthog.optedOut = true;
  }),
  capture: jest.fn((event: string, props: Record<string, unknown>) => {
    calls.push(`capture:${event}:${String(props.opt_in)}`);
  }),
};
jest.mock("posthog-react-native", () => ({ __esModule: true, default: jest.fn(() => mockPosthog) }));

const { changeAnalyticsOptIn, readAnalyticsOptIn } = require("../analytics-optin") as typeof import("../analytics-optin");

beforeEach(() => {
  calls.length = 0;
});

it("reads the SDK flag after it has loaded", async () => {
  mockPosthog.optedOut = true;
  expect(await readAnalyticsOptIn()).toBe(false);
  mockPosthog.optedOut = false;
  expect(await readAnalyticsOptIn()).toBe(true);
  expect(calls[0]).toBe("ready");
});

it("records an opt-in AFTER opting in, so the SDK keeps the event", async () => {
  mockPosthog.optedOut = true;
  await changeAnalyticsOptIn(true);
  expect(calls).toEqual(["optIn", "capture:analytics_opt_changed:true"]);
});

it("records an opt-out BEFORE opting out, so the event is the last one sent", async () => {
  mockPosthog.optedOut = false;
  await changeAnalyticsOptIn(false);
  expect(calls).toEqual(["capture:analytics_opt_changed:false", "optOut"]);
});
