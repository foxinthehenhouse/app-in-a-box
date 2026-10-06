/**
 * The minors pack's age gate: a neutral birth month + year, only the outcome kept,
 * analytics off until an of-age answer and for good after an under-age one. And with
 * the pack off it costs nothing: no read, no gate, analytics untouched.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";

import { en } from "../../locales/en";

process.env.EXPO_PUBLIC_POSTHOG_API_KEY = "phc_test";

let mockMinors = true;
jest.mock("../packs", () => ({
  get PACKS() {
    return mockMinors ? ["baseline", "minors"] : ["baseline"];
  },
  packOn: (id: string) => id === "baseline" || (mockMinors && id === "minors"),
}));

const mockPosthog = { capture: jest.fn(), identify: jest.fn(), optIn: jest.fn(), optOut: jest.fn(), reset: jest.fn() };
const mockPostHogCtor = jest.fn((..._args: unknown[]) => mockPosthog);
/** The options the analytics module built PostHog with on its last load. */
const defaultOptIn = () => (mockPostHogCtor.mock.calls.at(-1)?.[1] as { defaultOptIn: boolean }).defaultOptIn;
jest.mock("posthog-react-native", () => ({ __esModule: true, default: mockPostHogCtor }));

type Mods = {
  age: typeof import("../age");
  analytics: typeof import("../analytics");
  store: { getItem: jest.Mock; setItemAsync: jest.Mock; deleteItemAsync: jest.Mock };
};

/** Fresh modules with the minors pack on or off, and the stored answer set (or not). */
function load(minors: boolean, stored: string | null): Mods {
  let mods: Mods | undefined;
  mockMinors = minors;
  jest.isolateModules(() => {
    const store = require("expo-secure-store") as Mods["store"];
    store.getItem.mockImplementation(() => stored);
    mods = {
      store,
      analytics: require("../analytics") as Mods["analytics"],
      age: require("../age") as Mods["age"],
    };
  });
  if (!mods) throw new Error("not loaded");
  return mods;
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("pack off", () => {
  it("costs nothing: no storage read, of age, analytics flows and starts opted in", () => {
    const { age, analytics, store } = load(false, null);
    expect(store.getItem).not.toHaveBeenCalled();
    expect(age.currentAgeStatus()).toBe("ofAge");
    expect(analytics.analyticsSuppressed()).toBe(false);
    expect(defaultOptIn()).toBe(true);
    analytics.analytics.updatePrompted();
    expect(mockPosthog.capture).toHaveBeenCalledWith("update_prompted", {});
  });
});

describe("pack on", () => {
  it("collects nothing before an answer: SDK starts opted out, events and identify dropped", () => {
    const { age, analytics } = load(true, null);
    expect(age.currentAgeStatus()).toBe("unknown");
    expect(defaultOptIn()).toBe(false);
    analytics.analytics.updatePrompted();
    analytics.identifyUser("u1");
    expect(mockPosthog.capture).not.toHaveBeenCalled();
    expect(mockPosthog.identify).not.toHaveBeenCalled();
  });

  it("an under-age answer is kept (not the date) and switches analytics off for good", async () => {
    const { age, analytics, store } = load(true, null);
    const today = new Date(2026, 5, 15);
    expect(await age.recordAge(2016, 3, today)).toBe("underAge");
    expect(store.setItemAsync).toHaveBeenCalledWith("age_policy", "underAge");
    expect(JSON.stringify(store.setItemAsync.mock.calls)).not.toContain("2016");
    expect(mockPosthog.optOut).toHaveBeenCalled();
    await analytics.setAnalyticsOptIn(true); // e.g. the Settings toggle
    expect(mockPosthog.optIn).not.toHaveBeenCalled();
    analytics.analytics.updatePrompted();
    expect(mockPosthog.capture).not.toHaveBeenCalled();
  });

  it("an of-age answer opts in once and lets events through", async () => {
    const { age, analytics } = load(true, null);
    expect(await age.recordAge(1990, 7, new Date(2026, 5, 15))).toBe("ofAge");
    expect(mockPosthog.optIn).toHaveBeenCalledTimes(1);
    analytics.analytics.updatePrompted();
    expect(mockPosthog.capture).toHaveBeenCalledWith("update_prompted", {});
  });

  it("remembers the answer across launches, so a child can't pick an older year", () => {
    expect(load(true, "underAge").age.currentAgeStatus()).toBe("underAge");
    expect(load(true, "underAge").analytics.analyticsSuppressed()).toBe(true);
    expect(load(true, "ofAge").analytics.analyticsSuppressed()).toBe(false);
    expect(load(true, "garbage").age.currentAgeStatus()).toBe("unknown");
  });
});

it("works out whole years from a month and year, and rejects impossible dates", () => {
  const { age } = load(false, null);
  const today = new Date(2026, 5, 15); // June 2026
  expect(age.ageFrom(2013, 6, today)).toBe(13);
  expect(age.ageFrom(2013, 7, today)).toBe(12);
  expect(age.validBirth(2013, 13, today)).toBe(false);
  expect(age.validBirth(2030, 1, today)).toBe(false);
  expect(age.validBirth(1890, 1, today)).toBe(false);
  expect(age.validBirth(Number(""), 4, today)).toBe(false);
  expect(age.validBirth(1990, 4, today)).toBe(true);
});

describe("AgeGate", () => {
  // Required here, not imported: imports are hoisted above the mocks' setup above.
  const { AgeGate } = require("../../components/ui/AgeGate") as typeof import("../../components/ui/AgeGate");

  it("asks neutrally, refuses an impossible date, and reports an adult's answer", async () => {
    const onDone = jest.fn();
    await render(<AgeGate status="unknown" onDone={onDone} />);
    expect(screen.getByText(en.age.title)).toBeTruthy();
    expect(screen.queryByText(/13/)).toBeNull(); // no hint of the "right" answer
    await fireEvent.press(screen.getByTestId("age-gate-continue-button"));
    expect(await screen.findByTestId("age-gate-error")).toBeTruthy();
    await fireEvent.changeText(screen.getByTestId("age-gate-month-input"), "7");
    await fireEvent.changeText(screen.getByTestId("age-gate-year-input"), "1990");
    await fireEvent.press(screen.getByTestId("age-gate-continue-button"));
    await waitFor(() => expect(onDone).toHaveBeenCalledWith("ofAge"));
  });

  it("shows an under-age user a calm 'ask a parent' screen with no way back", async () => {
    await render(<AgeGate status="underAge" onDone={jest.fn()} />);
    expect(screen.getByText(en.age.underAgeTitle)).toBeTruthy();
    expect(screen.queryByTestId("age-gate-continue-button")).toBeNull();
  });
});
