/**
 * Deep links + universal links -> internal routes. ONE pure function every entry
 * point goes through: app/+native-intent.tsx (cold/warm opens from the OS),
 * notification taps (lib/push.ts) and anything else that turns a URL into a
 * route. Unit-tested in lib/__tests__/links.test.ts.
 *
 * Accepted:
 *   __SCHEME__://settings                     custom scheme (app.json "scheme")
 *   https://<appDomain>/settings              universal / app link (see below)
 *   /settings                                 an internal path (push payload `url`)
 * Anything else (another host, javascript:, a path we don't route) -> null, and
 * callers fall back to home. Never navigate to a URL taken straight from a
 * payload: that's how a push or a link opens an unexpected screen.
 *
 * Query strings are validated param by param (simple keys, plain values); anything
 * else is dropped, so a link can't smuggle a URL or markup into a screen's params.
 * Destructive screens (delete account) are never linkable: a link must not be one
 * tap away from an irreversible action.
 *
 * Signed out, a link can't open its screen (the auth guard shows sign-in). It is
 * remembered (`rememberPendingLink`, 10 min) and opened once the user signs in
 * (`usePendingLinkReplay`, mounted in app/_layout.tsx).
 *
 * Universal links (https) need a domain you control. Run
 *   node scripts/set-app-domain.js links.example.com --team-id ABCDE12345 --sha256 <fingerprint>
 * which writes `expo.extra.appDomain`, `ios.associatedDomains` and Android
 * `intentFilters` (autoVerify) into app.json and prints the two files to host at
 * https://<domain>/.well-known/ (apple-app-site-association, assetlinks.json).
 * Until then only the custom scheme works, which is fine for development.
 */
import { useEffect, useRef } from "react";
import Constants from "expo-constants";
import { router, type Href } from "expo-router";

export const SCHEME = "__SCHEME__";

/** Set by scripts/set-app-domain.js (app.json expo.extra.appDomain). Empty = no universal links yet. */
export function appDomain(): string {
  const d = (Constants.expoConfig?.extra as { appDomain?: unknown } | undefined)?.appDomain;
  return typeof d === "string" ? d.toLowerCase() : "";
}

/**
 * Every externally linkable route, as a pattern. Add a line when a screen should
 * be reachable from a link or a push. `:param` segments match one path segment.
 * Routes NOT listed here can't be opened from outside the app. Never list a
 * destructive screen (like /delete-account): a link must not start one.
 */
export const LINKABLE_ROUTES: readonly string[] = ["/", "/settings", "/edit-name"];

const PARAM_KEY = /^[A-Za-z0-9_]{1,32}$/;
const PARAM_VALUE = /^[A-Za-z0-9._~-]{0,128}$/;

/** Keep only well-formed `key=value` params (simple keys, plain values); drop the rest. */
function safeQuery(query: string): string {
  const kept: string[] = [];
  for (const pair of query.replace(/^\?/, "").split("&")) {
    if (!pair) continue;
    const eq = pair.indexOf("=");
    const rawKey = eq === -1 ? pair : pair.slice(0, eq);
    const rawValue = eq === -1 ? "" : pair.slice(eq + 1);
    let key: string;
    let value: string;
    try {
      key = decodeURIComponent(rawKey);
      value = decodeURIComponent(rawValue.replace(/\+/g, " "));
    } catch {
      continue; // malformed %-encoding
    }
    if (PARAM_KEY.test(key) && PARAM_VALUE.test(value)) kept.push(`${key}=${value}`);
  }
  return kept.length ? `?${kept.join("&")}` : "";
}

function matches(pattern: string, path: string): boolean {
  const a = pattern.split("/").filter(Boolean);
  const b = path.split("/").filter(Boolean);
  if (a.length !== b.length) return false;
  return a.every((seg, i) => seg.startsWith(":") ? /^[A-Za-z0-9_-]+$/.test(b[i] ?? "") : seg === b[i]);
}

/** Strip Expo Router group segments like "(app)" so "/(app)/settings" == "/settings". */
function normalise(path: string): string {
  const clean = path
    .split("/")
    .filter((s) => s && !/^\(.+\)$/.test(s))
    .join("/");
  return `/${clean}`.replace(/\/index$/, "/").replace(/^\/$/, "/");
}

/**
 * URL or path -> a safe internal route (with its query string), or null.
 * `domain` defaults to the configured app domain.
 */
export function resolveDeepLink(input: string, domain: string = appDomain()): string | null {
  const raw = (input ?? "").trim();
  if (!raw) return null;
  let path: string;
  let query = "";
  const scheme = raw.match(/^([a-z][a-z0-9+.-]*):\/\/(.*)$/i);
  if (scheme) {
    const proto = (scheme[1] ?? "").toLowerCase();
    const rest = scheme[2] ?? "";
    if (proto === "https" || proto === "http") {
      const slash = rest.indexOf("/");
      const host = (slash === -1 ? rest : rest.slice(0, slash)).toLowerCase();
      if (!domain || host !== domain) return null;
      path = slash === -1 ? "/" : rest.slice(slash);
    } else if ((proto === "exp" || proto === "exps") && rest.includes("/--/")) {
      // Expo Go / dev server: exp://192.168.1.5:8081/--/settings
      path = `/${rest.slice(rest.indexOf("/--/") + 4)}`;
    } else if (proto === SCHEME.toLowerCase()) {
      // scheme://settings -> host is the first path segment
      path = `/${rest.replace(/^\/+/, "")}`;
    } else {
      return null; // javascript:, another app's scheme, etc.
    }
  } else if (raw.startsWith("/") && !raw.startsWith("//")) {
    path = raw;
  } else {
    return null;
  }
  const q = path.search(/[?#]/);
  if (q !== -1) {
    query = path[q] === "?" ? path.slice(q).split("#")[0] ?? "" : "";
    path = path.slice(0, q);
  }
  let decoded: string;
  try {
    decoded = decodeURIComponent(path);
  } catch {
    return null; // malformed %-encoding
  }
  const route = normalise(decoded);
  return LINKABLE_ROUTES.some((p) => matches(p, route)) ? `${route}${safeQuery(query)}` : null;
}

// ---- Links opened while signed out ---------------------------------------------

export const PENDING_LINK_TTL_MS = 10 * 60 * 1000;

let pending: { route: string; at: number } | null = null;
/** null until auth has resolved once (cold start). */
let signedIn: boolean | null = null;

/** Remember a route to open after sign-in (the latest link wins). */
export function rememberPendingLink(route: string, now: number = Date.now()): void {
  pending = { route, at: now };
}

/** The remembered route, once (it's cleared), unless it's older than PENDING_LINK_TTL_MS. */
export function takePendingLink(now: number = Date.now()): string | null {
  const p = pending;
  pending = null;
  return p && now - p.at <= PENDING_LINK_TTL_MS ? p.route : null;
}

/**
 * app/+native-intent.tsx calls this for every resolved link. Signed in, the
 * router opens it directly; signed out (or not known yet, on a cold start) it's
 * remembered for after sign-in.
 */
export function notePendingLink(route: string | null): void {
  if (route && route !== "/" && signedIn !== true) rememberPendingLink(route);
}

/**
 * Open a link that arrived while signed out, once the user signs in. On a cold
 * start that resolves straight to signed in, the router already opened the link:
 * the remembered copy is dropped, not opened twice. `loading` = the root stack
 * isn't mounted yet (auth or theme still resolving).
 */
export function usePendingLinkReplay(isSignedIn: boolean, loading: boolean): void {
  const resolved = useRef(false);
  useEffect(() => {
    if (loading) return;
    const first = !resolved.current;
    resolved.current = true;
    signedIn = isSignedIn;
    if (!isSignedIn) return;
    const route = takePendingLink();
    if (first || !route) return;
    router.push(route as Href); // only ever a LINKABLE_ROUTES match (resolveDeepLink)
  }, [isSignedIn, loading]);
}
