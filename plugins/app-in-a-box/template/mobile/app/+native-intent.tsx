/**
 * Every URL the OS opens the app with (custom scheme, universal/app link, Expo Go
 * dev URL) passes through here BEFORE Expo Router resolves it. We map it with the
 * one pure resolver in lib/links.ts: a linkable route opens; anything else (a
 * foreign host, an unknown path, junk) lands on home instead of a 404 screen.
 * Signed-out users are still sent to sign-in by the Stack.Protected guard; the
 * route is remembered and opened after sign-in (lib/links.ts usePendingLinkReplay).
 */
import { analytics } from "../lib/analytics";
import { notePendingLink, resolveDeepLink } from "../lib/links";

export function redirectSystemPath({ path }: { path: string; initial: boolean }): string {
  const route = resolveDeepLink(path);
  analytics.deepLinkOpened({ route: route ?? "/", matched: route !== null });
  notePendingLink(route);
  return route ?? "/";
}
