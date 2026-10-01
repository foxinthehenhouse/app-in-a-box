/**
 * Deep links: every URL the OS (or a push payload) hands us goes through ONE pure
 * resolver. A linkable route opens; anything else maps to null (callers go home).
 */
import { redirectSystemPath } from "../../app/+native-intent";
import { LINKABLE_ROUTES, SCHEME, resolveDeepLink } from "../links";

jest.mock("../analytics", () => ({ analytics: { deepLinkOpened: jest.fn() } }));
const { analytics } = jest.requireMock("../analytics") as { analytics: { deepLinkOpened: jest.Mock } };

const DOMAIN = "links.example.com";

describe("resolveDeepLink", () => {
  it.each([
    [`${SCHEME}://settings`, "/settings"],
    [`${SCHEME}:///settings`, "/settings"],
    [`${SCHEME}://`, "/"],
    [`${SCHEME}://edit-name?from=push`, "/edit-name?from=push"],
    [`https://${DOMAIN}/settings`, "/settings"],
    [`https://LINKS.example.com/settings#top`, "/settings"],
    [`https://${DOMAIN}`, "/"],
    ["exp://192.168.1.5:8081/--/settings", "/settings"],
    ["/settings", "/settings"],
    ["/(app)/settings", "/settings"],
    ["/(app)/index", "/"],
    ["/settings?tab=push&ref=email_1", "/settings?tab=push&ref=email_1"],
    ["/settings?next=javascript:alert(1)", "/settings"],
    ["/settings?a=1&b=%3Cscript%3E&c=ok", "/settings?a=1&c=ok"],
    ["/settings?=x&bad key=1", "/settings"],
    ["/settings?%E0%A4%A=1", "/settings"],
  ])("maps %s -> %s", (input, want) => {
    expect(resolveDeepLink(input, DOMAIN)).toBe(want);
  });

  it.each([
    ["https://evil.example.com/settings", "a foreign host"],
    [`https://${DOMAIN}.evil.com/settings`, "a lookalike host"],
    ["javascript:alert(1)", "javascript:"],
    ["otherapp://settings", "another app's scheme"],
    ["//evil.example.com/settings", "a protocol-relative URL"],
    ["/gallery", "a route that isn't linkable (dev-only)"],
    ["/delete-account", "a destructive screen"],
    [`${SCHEME}://delete-account`, "a destructive screen via the scheme"],
    ["/settings/../gallery", "path traversal"],
    ["/%E0%A4%A", "malformed percent-encoding"],
    ["settings", "a bare word"],
    ["", "empty"],
  ])("rejects %s (%s)", (input) => {
    expect(resolveDeepLink(input, DOMAIN)).toBeNull();
  });

  it("rejects https links until a domain is configured", () => {
    expect(resolveDeepLink(`https://${DOMAIN}/settings`, "")).toBeNull();
    expect(resolveDeepLink(`${SCHEME}://settings`, "")).toBe("/settings");
  });

  it("matches :param segments to one safe path segment", () => {
    const routes = LINKABLE_ROUTES as string[];
    routes.push("/items/:id");
    try {
      expect(resolveDeepLink("/items/abc-123", DOMAIN)).toBe("/items/abc-123");
      expect(resolveDeepLink("/items/a%20b", DOMAIN)).toBeNull();
      expect(resolveDeepLink("/items/1/2", DOMAIN)).toBeNull();
    } finally {
      routes.pop();
    }
  });
});

describe("+native-intent redirectSystemPath", () => {
  beforeEach(() => analytics.deepLinkOpened.mockClear());

  it("opens a linkable route and records it", () => {
    expect(redirectSystemPath({ path: `${SCHEME}://settings`, initial: true })).toBe("/settings");
    expect(analytics.deepLinkOpened).toHaveBeenCalledWith({ route: "/settings", matched: true });
  });

  it("sends anything else home instead of a 404", () => {
    expect(redirectSystemPath({ path: "https://evil.example.com/x", initial: false })).toBe("/");
    expect(analytics.deepLinkOpened).toHaveBeenCalledWith({ route: "/", matched: false });
  });
});
