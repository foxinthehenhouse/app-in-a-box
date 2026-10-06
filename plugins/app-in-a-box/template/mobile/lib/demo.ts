/**
 * Demo mode: EXPO_PUBLIC_DEMO=1 swaps the backend and auth for an in-memory fake
 * with seeded data, so `npx expo start --web` (or Expo Go) works with zero
 * accounts. It is a DEV tool: never set it in eas.json. It's allowlisted in
 * scripts/check-eas-shipping-env.js because its absence (real backend) is the
 * safe default for shipping builds.
 *
 * It is also gated on `__DEV__`: a release build ignores EXPO_PUBLIC_DEMO even if
 * it leaks in (a value in the EAS env store via `eas env:create`, or a stray
 * .env uploaded with the build), so a store build can never ship the fake backend.
 *
 * Keep it honest: the fake answers through the same ApiError path as the real
 * server (lib/api.ts), with realistic latency so loading states show. When you
 * add an endpoint, add its handler to ROUTES below, or demo mode returns a 404
 * for it, exactly like a server that doesn't have it yet. Keys take `:param`
 * segments and handlers get `{ params, query }`, so `GET /api/v1/things/:id` and
 * `GET /api/v1/today?on=...` need no hand-rolled URL parsing.
 */
import type { ProfileWire } from "./api"; // type-only: erased at runtime, no cycle

export const DEMO = __DEV__ && process.env.EXPO_PUBLIC_DEMO === "1";

export interface DemoUser {
  id: string;
  email: string;
}

/** Seeded data. Edit it to make the demo tell your app's story. */
export const DEMO_SEED: { profile: ProfileWire } = {
  profile: { id: "demo-user", displayName: "Sam", onboarded: true },
};

export const DEMO_LATENCY_MS = process.env.NODE_ENV === "test" ? 0 : 450;

type Listener = (user: DemoUser | null) => void;

interface DemoState {
  user: DemoUser | null;
  profile: ProfileWire;
  /** Expo push tokens registered for the demo user (POST/DELETE /api/v1/me/push-token). */
  pushTokens: { token: string; platform: string | null }[];
  listeners: Set<Listener>;
}

function freshState(): DemoState {
  return { user: null, profile: { ...DEMO_SEED.profile }, pushTokens: [], listeners: new Set() };
}

const state: DemoState = freshState();

/** Reset between tests: every field back to its seed, except the auth listeners. Adding
 * demo state? Add it to DemoState and freshState() only; this picks it up.
 * @public Tests reach it through `require()` (after setting the demo env), which knip can't follow. */
export function resetDemo(): void {
  Object.assign(state, freshState(), { listeners: state.listeners });
}

/** Read-only view for tests and the gallery.
 * @public Tests reach it through `require()`, which knip can't follow. */
export function demoSnapshot(): { profile: ProfileWire; pushTokens: { token: string; platform: string | null }[] } {
  return { profile: { ...state.profile }, pushTokens: state.pushTokens.map((t) => ({ ...t })) };
}

export const demoAuth = {
  current: (): DemoUser | null => state.user,
  /** Any email works; the code must be 6 digits (so the UI's validation is exercised). */
  verify(email: string, code: string): { error: string | null } {
    if (!/^\d{6}$/.test(code)) return { error: "Enter the 6-digit code. In demo mode any 6 digits work." };
    state.user = { id: state.profile.id, email };
    state.listeners.forEach((l) => l(state.user));
    return { error: null };
  },
  signOut(): void {
    state.user = null;
    state.listeners.forEach((l) => l(null));
  },
  subscribe(listener: Listener): () => void {
    state.listeners.add(listener);
    return () => {
      state.listeners.delete(listener);
    };
  },
};

export interface DemoResponse {
  status: number;
  body: unknown;
}

/**
 * What a handler gets besides the body: `params` from `:name` segments in its route
 * key (`"GET /api/v1/things/:id"` -> `params.id`) and the parsed query string
 * (`?on=2026-09-30` -> `query.on`). Mirrors FastAPI path + query parameters.
 */
export interface DemoRequest {
  params: Record<string, string>;
  query: Record<string, string>;
}

type Handler = (body: unknown, req: DemoRequest) => DemoResponse;

const ROUTES: Record<string, Handler> = {
  "GET /api/v1/me": () => ({ status: 200, body: state.profile }),
  "PATCH /api/v1/me": (body) => {
    const patch = (body ?? {}) as Partial<ProfileWire>;
    if (typeof patch.displayName === "string" && patch.displayName.length > 80) {
      return { status: 422, body: { detail: "Display name is too long", error_id: "demo-422" } };
    }
    state.profile = {
      ...state.profile,
      ...(typeof patch.displayName === "string" ? { displayName: patch.displayName } : null),
      ...(typeof patch.onboarded === "boolean" ? { onboarded: patch.onboarded } : null),
    };
    return { status: 200, body: state.profile };
  },
  // Mirrors backend/routers/me.py delete_me: the literal confirm is required, then
  // everything the user owned is gone. Signing in again starts a brand-new account.
  "DELETE /api/v1/me": (body) => {
    if ((body as { confirm?: unknown } | undefined)?.confirm !== "DELETE") {
      return { status: 422, body: { detail: "confirm must be DELETE" } };
    }
    state.profile = { id: state.profile.id, displayName: null, onboarded: false };
    state.pushTokens = [];
    return { status: 204, body: undefined };
  },
  "POST /api/v1/me/push-token": (body) => {
    const b = (body ?? {}) as { token?: unknown; platform?: unknown };
    if (typeof b.token !== "string" || !/^Expo(nent)?PushToken\[.+\]$/.test(b.token)) {
      return { status: 422, body: { detail: "not an Expo push token" } };
    }
    const token = b.token;
    state.pushTokens = [
      ...state.pushTokens.filter((t) => t.token !== token),
      { token, platform: typeof b.platform === "string" ? b.platform : null },
    ];
    return { status: 204, body: undefined };
  },
  "DELETE /api/v1/me/push-token": (body) => {
    const token = (body as { token?: unknown } | undefined)?.token;
    state.pushTokens = state.pushTokens.filter((t) => t.token !== token);
    return { status: 204, body: undefined };
  },
  // Mirrors backend/routers/export.py: only this user's rows, per table.
  "GET /api/v1/me/export": () => ({
    status: 200,
    body: {
      formatVersion: 1,
      exportedAt: new Date().toISOString(),
      userId: state.profile.id,
      tables: {
        profiles: [{ id: state.profile.id, display_name: state.profile.displayName, onboarded: state.profile.onboarded }],
        push_tokens: state.pushTokens.map((t) => ({ token: t.token, platform: t.platform })),
      },
    },
  }),
};

export async function demoFetch(path: string, init: RequestInit = {}, latencyMs = DEMO_LATENCY_MS): Promise<DemoResponse> {
  if (latencyMs > 0) await new Promise((r) => setTimeout(r, latencyMs)); // no timer at 0: fake-timer safe
  if (!state.user) return { status: 401, body: { detail: "Not signed in" } };
  const method = (init.method ?? "GET").toUpperCase();
  const match = matchDemoRoute(Object.keys(ROUTES), method, path);
  const handler = match ? ROUTES[match.key] : undefined;
  if (!match || !handler) return { status: 404, body: { detail: `Demo mode has no handler for ${method} ${path}` } };
  const body = typeof init.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
  return handler(body, { params: match.params, query: match.query });
}

/**
 * `"METHOD /path/:param"` route keys -> the key that serves `method path`, with its
 * params and query. An exact key wins over a pattern; `:param` matches one segment.
 * Exported for tests. Like the real API (redirect_slashes=False), `/x/` is not `/x`.
 */
export function matchDemoRoute(
  keys: readonly string[],
  method: string,
  fullPath: string,
): { key: string; params: Record<string, string>; query: Record<string, string> } | null {
  const q = fullPath.indexOf("?");
  const path = q === -1 ? fullPath : fullPath.slice(0, q);
  const query: Record<string, string> = {};
  if (q !== -1) {
    for (const pair of fullPath.slice(q + 1).split("&")) {
      if (!pair) continue;
      const [k, v = ""] = pair.split("=");
      try {
        query[decodeURIComponent(k ?? "")] = decodeURIComponent(v.replace(/\+/g, " "));
      } catch {
        // malformed %-encoding: drop the pair, as a server would reject it
      }
    }
  }
  const exact = `${method} ${path}`;
  if (keys.includes(exact)) return { key: exact, params: {}, query };
  const segs = path.split("/");
  for (const key of keys) {
    const [m, pattern = ""] = key.split(" ");
    if (m !== method || !pattern.includes(":")) continue;
    const want = pattern.split("/");
    if (want.length !== segs.length) continue;
    const params: Record<string, string> = {};
    const ok = want.every((w, i) => {
      const got = segs[i] ?? "";
      if (w.startsWith(":")) {
        if (!got) return false;
        try {
          params[w.slice(1)] = decodeURIComponent(got);
        } catch {
          return false;
        }
        return true;
      }
      return w === got;
    });
    if (ok) return { key, params, query };
  }
  return null;
}
