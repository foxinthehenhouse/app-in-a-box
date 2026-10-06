/**
 * The ONLY way the app talks to the backend.
 *
 * - Adds the Supabase access token.
 * - Sends an `X-Request-ID` on every call. The backend echoes it on the response,
 *   stamps it on every log line and tags Sentry with it, so one id joins the
 *   client error, the server logs and the Sentry issue.
 * - Turns non-2xx responses into a typed ApiError carrying the server's error_id
 *   and the request id. `errorReference(e)` is the short code a screen shows
 *   (<ErrorNotice>) and support greps for.
 * - Gives up after DEFAULT_TIMEOUT_MS (15s; `timeoutMs` per call). A request that
 *   hangs on a bad network fails as offline (status 0, reason "timeout"), which every
 *   screen already shows with Retry, instead of spinning forever.
 * - Sends `Idempotency-Key` when a write passes `idempotencyKey`. lib/query.ts gives
 *   every queued write one key for life, so a replay after an offline spell (or a
 *   restart) that the server already ran gets the stored response back instead of
 *   running twice (backend/idempotency.py).
 * - Fires analytics for failures, so a silent failure still leaves a trail.
 * - In demo mode (EXPO_PUBLIC_DEMO=1) the same path answers from lib/demo.ts.
 *
 * A generic `apiFetch<T>()` ASSERTS a shape; it never checks one. When the wire
 * shape differs from what a screen wants, write an adapter function here
 * (`xxxWire` type -> UI type) with a test. Never pass raw responses into UI.
 */
import { analytics, startTimer } from "./analytics";
import { DEMO, demoFetch } from "./demo";
import { i18n } from "./i18n";
import type * as SessionModule from "./session";
import { currentUserId, supabase } from "./supabase";

const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? "").replace(/\/$/, "");

/** How long a request may take, headers and body, before it fails as offline. */
export const DEFAULT_TIMEOUT_MS = 15_000;

/**
 * RequestInit plus how long to wait before giving up (default DEFAULT_TIMEOUT_MS), and
 * the write's Idempotency-Key: the SAME key on every retry and replay of one write.
 */
export interface ApiInit extends RequestInit {
  timeoutMs?: number;
  idempotencyKey?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly errorId?: string,
    public readonly requestId?: string,
    /**
     * "misconfigured": the BUILD has no server address (lib/config.ts), not a network problem.
     * "timeout": no answer within the request's timeout; shown as offline, retried like it.
     */
    public readonly reason?: "misconfigured" | "timeout",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * A v4-shaped UUID for X-Request-ID. Correlation only, not a secret, so
 * Math.random is fine (and needs no native module). The backend accepts
 * `[A-Za-z0-9._-]{8,128}` and replaces anything else with its own id.
 */
export function newRequestId(): string {
  const hex = (n: number) =>
    Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join("");
  const variant = "89ab"[Math.floor(Math.random() * 4)];
  return `${hex(8)}-${hex(4)}-4${hex(3)}-${variant}${hex(3)}-${hex(12)}`;
}

/**
 * A fresh Idempotency-Key: one per write the user meant, reused by every replay of it.
 * Same shape as a request id (the backend accepts `[A-Za-z0-9._:-]{8,128}`). Math.random
 * is enough: a key only has to be unique among one user's writes in a day, and a
 * collision can't replay the wrong response (the server also matches the request body).
 */
export function newIdempotencyKey(): string {
  return newRequestId();
}

async function authHeader(): Promise<{ header: Record<string, string>; userId: string | undefined }> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiError("Not signed in", 401);
  return { header: { Authorization: `Bearer ${token}` }, userId: data.session?.user?.id };
}

function field(body: unknown, key: string): string | undefined {
  return body && typeof body === "object" && key in body ? String((body as Record<string, unknown>)[key]) : undefined;
}

export interface RawResponse {
  status: number;
  body: unknown;
  /** The id the server logged this request under (its echo, else the one we sent). */
  requestId: string;
  /** Whose token this request carried, so a late 401 can't end someone else's session. */
  sentAs?: string;
}

/** Thrown inside send() when the request's own timer fires (not the caller's signal). */
class TimeoutError extends Error {
  constructor(public readonly ms: number) {
    super(`Request timed out after ${ms / 1000}s`);
    this.name = "TimeoutError";
  }
}

/**
 * An abort signal that fires after `ms`, and also when the caller's own signal does.
 * Like `AbortSignal.timeout(ms)` (combined with the caller's signal via
 * `AbortSignal.any`), but built on a plain timer: React Native's AbortController is
 * the `abort-controller` polyfill, which has neither static, and a timer is what tests
 * can drive with fake time.
 */
function timeoutSignal(ms: number, outer: AbortSignal | null | undefined) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, ms);
  const forward = () => controller.abort();
  if (outer?.aborted) controller.abort();
  else outer?.addEventListener("abort", forward);
  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    done: () => {
      clearTimeout(timer);
      outer?.removeEventListener("abort", forward);
    },
  };
}

async function send(path: string, init: ApiInit, requestId: string): Promise<RawResponse> {
  if (DEMO) {
    const res = await demoFetch(path, init);
    return { ...res, requestId };
  }
  if (!API_URL) throw new ApiError("EXPO_PUBLIC_API_URL is not set", 0, undefined, requestId, "misconfigured");
  const auth = await authHeader();
  const { timeoutMs = DEFAULT_TIMEOUT_MS, idempotencyKey, ...request } = init;
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(request.body && !(request.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
    ...auth.header,
    ...((request.headers as Record<string, string>) ?? {}),
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
    "X-Request-ID": requestId,
  };
  // The timer covers the body too: a server that sends headers and then stalls is
  // as stuck as one that never answers.
  const deadline = timeoutSignal(timeoutMs, request.signal);
  try {
    const res = await fetch(`${API_URL}${path}`, { ...request, headers, signal: deadline.signal });
    const echoed = res.headers?.get?.("x-request-id") ?? requestId;
    const sentAs = auth.userId;
    if (res.status === 204) return { status: 204, body: undefined, requestId: echoed, sentAs };
    const body: unknown = await res.json().catch((e: unknown) => {
      if (deadline.timedOut()) throw e;
      return null;
    });
    return { status: res.status, body, requestId: echoed, sentAs };
  } catch (e) {
    throw deadline.timedOut() ? new TimeoutError(timeoutMs) : e;
  } finally {
    deadline.done();
  }
}

/**
 * The server says this session is over: run the SAME cleanup as signing out
 * (forget the push token, clear the cache, sign out this device) so nothing of
 * this user's is left for the next one. No push unregister: it would 401 too.
 * Required lazily: lib/session.ts -> lib/query.ts -> this module.
 */
async function expireSession(): Promise<void> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- lazy, breaks an import cycle (see above)
    const { endSession } = require("./session") as typeof SessionModule;
    await endSession({ unregisterPush: false });
  } catch {
    // best effort: the caller still gets the 401
  }
}

export async function apiFetch<T>(path: string, init: ApiInit = {}): Promise<T> {
  const elapsed = startTimer();
  const requestId = newRequestId();
  let res: RawResponse;
  try {
    res = await send(path, init, requestId);
  } catch (e) {
    if (e instanceof ApiError) throw e;
    analytics.apiFailed({ path, status: 0, duration_ms: elapsed() });
    if (e instanceof TimeoutError) throw new ApiError(e.message, 0, undefined, requestId, "timeout");
    throw new ApiError(e instanceof Error ? e.message : "Network error", 0, undefined, requestId);
  }
  if (res.status < 200 || res.status >= 300) {
    analytics.apiFailed({ path, status: res.status, duration_ms: elapsed() });
    // Only end the session this request was made under. A slow request from user A
    // can 401 after B has signed in on this device; that must not sign B out.
    if (res.status === 401 && (!res.sentAs || res.sentAs === (await currentUserId()))) {
      await expireSession();
    }
    throw new ApiError(
      `Request failed (${res.status})`,
      res.status,
      field(res.body, "error_id"),
      field(res.body, "request_id") ?? res.requestId,
    );
  }
  return res.body as T;
}

/** A short, human message for any error a screen catches. */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.reason === "misconfigured") return i18n.t("errors.misconfigured");
    if (e.status === 0) return i18n.t("errors.offline");
    if (e.status === 401) return i18n.t("errors.sessionEnded");
    return i18n.t("errors.status", { status: e.status });
  }
  return i18n.t("errors.generic");
}

/**
 * The short code a user can read out to support: the server's error_id when there
 * is one (a 500), else the request id. First 8 characters: enough to grep logs,
 * short enough to read aloud. Null when there's nothing to correlate (offline).
 */
export function errorReference(e: unknown): string | null {
  if (!(e instanceof ApiError) || e.status === 0) return null;
  const id = e.errorId ?? e.requestId;
  return id ? id.replace(/-/g, "").slice(0, 8) : null;
}

// ---- Adapters -------------------------------------------------------------

/** Mirrors backend/routers/me.py `Profile` (camelCase aliases). */
export interface ProfileWire {
  id: string;
  displayName: string | null;
  onboarded: boolean;
}

export interface Profile {
  id: string;
  displayName: string;
  onboarded: boolean;
}

export function toProfile(w: ProfileWire): Profile {
  return { id: w.id, displayName: w.displayName ?? "", onboarded: w.onboarded };
}

export async function getMe(): Promise<Profile> {
  return toProfile(await apiFetch<ProfileWire>("/api/v1/me"));
}

/**
 * Mirrors backend/routers/me.py `ProfileUpdate` (camelCase aliases). The API rejects
 * any other field with a 422 (`extra="forbid"`), so a field added here must land in
 * `ProfileUpdate` in the same PR; tests/test_wire_contract.py compares the two.
 */
export interface ProfilePatchWire {
  displayName?: string | null;
  onboarded?: boolean | null;
}

export type ProfilePatch = Partial<Pick<Profile, "displayName" | "onboarded">>;

/** Options every write adapter takes: the key its replays share (see lib/query.ts `keyed`). */
export interface WriteOptions {
  idempotencyKey?: string;
}

export async function updateMe(patch: ProfilePatch, opts: WriteOptions = {}): Promise<Profile> {
  const body: ProfilePatchWire = patch;
  return toProfile(
    await apiFetch<ProfileWire>("/api/v1/me", {
      method: "PATCH",
      body: JSON.stringify(body),
      idempotencyKey: opts.idempotencyKey,
    }),
  );
}

/** Mirrors backend/routers/me.py `AccountDeletion`: the literal confirm is required, nothing else is accepted. */
export interface AccountDeletionWire {
  confirm: "DELETE";
}

/** DELETE /api/v1/me -> 204. The caller must sign out right after (the token lives ~1h). */
export async function deleteAccount(): Promise<void> {
  const body: AccountDeletionWire = { confirm: "DELETE" };
  await apiFetch<void>("/api/v1/me", { method: "DELETE", body: JSON.stringify(body) });
}

/** Mirrors backend/routers/push.py `PushTokenIn` (POST). */
export interface PushTokenWire {
  token: string;
  platform?: "ios" | "android" | "web" | null;
}

/** Mirrors backend/routers/push.py `PushTokenRef` (DELETE): the token to forget, nothing else. */
export interface PushTokenRefWire {
  token: string;
}

export async function registerPushToken(token: string, platform: PushTokenWire["platform"]): Promise<void> {
  const body: PushTokenWire = { token, platform };
  await apiFetch<void>("/api/v1/me/push-token", { method: "POST", body: JSON.stringify(body) });
}

export async function unregisterPushToken(token: string): Promise<void> {
  const body: PushTokenRefWire = { token };
  await apiFetch<void>("/api/v1/me/push-token", { method: "DELETE", body: JSON.stringify(body) });
}

/** Mirrors backend/routers/export.py `DataExport`. */
export interface DataExportWire {
  formatVersion: number;
  exportedAt: string;
  userId: string;
  tables: Record<string, Record<string, unknown>[]>;
}

export interface DataExport {
  exportedAt: string;
  userId: string;
  /** Row count per table, for a summary line. */
  counts: Record<string, number>;
  /** The full export, pretty-printed, ready to write to a file. */
  json: string;
}

export function toDataExport(w: DataExportWire): DataExport {
  const counts: Record<string, number> = {};
  for (const [table, rows] of Object.entries(w.tables ?? {})) counts[table] = Array.isArray(rows) ? rows.length : 0;
  return { exportedAt: w.exportedAt, userId: w.userId, counts, json: JSON.stringify(w, null, 2) };
}

export async function exportMyData(): Promise<DataExport> {
  return toDataExport(await apiFetch<DataExportWire>("/api/v1/me/export"));
}

// ---- Pagination ---------------------------------------------------------------

/**
 * One page of a list, as backend/pagination.py `Page[T]` sends it. Mirror each list
 * endpoint's `Page[Thing]` as `interface ThingPageWire { items: ThingWire[]; nextCursor:
 * string | null; }` (tests/test_wire_contract.py pairs it), then adapt with `toPage`.
 */
export interface Page<T> {
  items: T[];
  /** Pass back verbatim for the next page; null on the last one. Opaque: never parse it. */
  nextCursor: string | null;
}

/** @public The adapter every list endpoint's pager uses (mobile/AGENTS.md); the template has no paged screen yet. */
export function toPage<W, T>(w: { items: W[]; nextCursor: string | null }, adapt: (item: W) => T): Page<T> {
  return { items: (w.items ?? []).map(adapt), nextCursor: w.nextCursor ?? null };
}

/**
 * `path?cursor=...&limit=...`, leaving out what isn't set. Built by hand: React Native's
 * URLSearchParams has no `set`.
 * @public For the paged list screens you add (mobile/AGENTS.md); the template has none yet.
 */
export function pagePath(path: string, cursor: string | null, limit?: number): string {
  const parts: string[] = [];
  if (cursor) parts.push(`cursor=${encodeURIComponent(cursor)}`);
  if (limit !== undefined) parts.push(`limit=${limit}`);
  if (!parts.length) return path;
  return `${path}${path.includes("?") ? "&" : "?"}${parts.join("&")}`;
}
