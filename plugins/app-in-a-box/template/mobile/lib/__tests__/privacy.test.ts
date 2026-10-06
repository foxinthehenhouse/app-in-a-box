/**
 * The runtime scrubbers behind the privacy lints: a PostHog payload or Sentry event that
 * carries personal data loses it before it leaves the phone, whichever packs are on.
 */
process.env.EXPO_PUBLIC_POSTHOG_API_KEY = "phc_test";
process.env.EXPO_PUBLIC_SENTRY_DSN = "https://key@o1.ingest.sentry.io/1";

const mockPosthog = { capture: jest.fn(), identify: jest.fn(), optIn: jest.fn(), optOut: jest.fn(), reset: jest.fn() };
jest.mock("posthog-react-native", () => ({ __esModule: true, default: jest.fn(() => mockPosthog) }));
const mockSentry = { init: jest.fn(), withScope: jest.fn(), captureException: jest.fn(), wrap: (c: unknown) => c };
jest.mock("@sentry/react-native", () => mockSentry);
jest.mock("expo-application", () => ({ applicationId: "com.example.app", nativeApplicationVersion: "1.0.0", nativeBuildVersion: "1" }));
jest.mock("expo-updates", () => ({ isEmbeddedLaunch: true, updateId: null, manifest: null }));
// Scrubbing is pack-independent; pin the packs so the minors age gate (which holds
// analytics until an answer) doesn't hide what this file checks.
jest.mock("../packs", () => ({ PACKS: ["baseline"], packOn: (id: string) => id === "baseline" }));

// Required after the env is set: the modules read it at load.
const { analytics } = require("../analytics") as typeof import("../analytics");
const { initMonitoring, reportError } = require("../monitoring") as typeof import("../monitoring");
const { isSensitiveKey, scrubProps, scrubSentryEvent } = require("../privacy") as typeof import("../privacy");

it.each([
  "email",
  "userEmail",
  "phone_number",
  "full_name",
  "displayName",
  "street",
  "lat",
  "longitude",
  "message",
  "searchTerm",
  "password",
  "date_of_birth",
  "heartRate",
  "blood_pressure",
  "balance",
  "card_number",
  "fingerprint",
  "faceEmbedding",
])("treats %s as sensitive", (key) => {
  expect(isSensitiveKey(key)).toBe(true);
});

it.each(["name", "query_length", "noteCount", "has_email", "screen", "route", "duration_ms", "error_code", "success", "page", "sheet", "method", "opt_in", "rename_count"])(
  "leaves %s alone",
  (key) => {
    expect(isSensitiveKey(key)).toBe(false);
  },
);

it("drops sensitive keys and keeps the rest, without touching the input", () => {
  const props = { screen: "home", email: "a@b.co", heart_rate: 72, success: true };
  expect(scrubProps(props)).toEqual({ screen: "home", success: true });
  expect(props.email).toBe("a@b.co");
});

it("strips a PostHog payload on its way out of analytics.*", () => {
  analytics.screenViewed("home", { email: "a@b.co", latitude: 51.5, tab: "today" });
  expect(mockPosthog.capture).toHaveBeenCalledWith("screen_viewed", { screen: "home", tab: "today" });
});

it("strips a Sentry event: no user, no request, no sensitive keys or crumb messages", () => {
  const event = scrubSentryEvent({
    user: { id: "u1", email: "a@b.co" },
    request: { data: "email=a@b.co" },
    extra: { email: "a@b.co", attempt: 2 },
    tags: { request_id: "r1", phone: "555" },
    contexts: { glucose: { value: 5.4 }, app: { version: "1" } },
    breadcrumbs: [{ message: "signed in as a@b.co", data: { query: "x", status: 200 } }],
  });
  expect(event).toEqual({
    extra: { attempt: 2 },
    tags: { request_id: "r1" },
    contexts: { app: { version: "1" } },
    breadcrumbs: [{ data: { status: 200 } }],
  });
});

it("wires the scrubber into Sentry and filters reportError's tags", () => {
  const g = globalThis as unknown as { __DEV__: boolean };
  const prev = g.__DEV__;
  g.__DEV__ = false;
  try {
    initMonitoring();
    expect(mockSentry.init.mock.calls[0][0].beforeSend).toBe(scrubSentryEvent);
    const scope = { setTag: jest.fn() };
    mockSentry.withScope.mockImplementation((fn: (s: typeof scope) => void) => fn(scope));
    reportError(new Error("x"), { boundary: "root", email: "a@b.co" });
    expect(scope.setTag.mock.calls).toEqual([["boundary", "root"]]);
  } finally {
    g.__DEV__ = prev;
  }
});
