/**
 * The session lives in SecureStore, chunked under its 2048-byte value cap (the mock in
 * jest.setup.ts throws over the cap, so an unchunked write fails here too).
 */
import * as SecureStore from "expo-secure-store";

import { CHUNK_CHARS, chunkValue, createSecureStorage } from "../secure-store";

const store = SecureStore as unknown as { getItemAsync: jest.Mock; setItemAsync: jest.Mock; deleteItemAsync: jest.Mock };
const storage = createSecureStorage();
const bytes = (s: string) => new TextEncoder().encode(s).length;
const KEY = "sb-abc-auth-token";
const SESSION = JSON.stringify({ access_token: "a".repeat(2200), refresh_token: "r".repeat(400), user: { email: "zoë@example.com" } });

beforeEach(async () => {
  await storage.removeItem(KEY);
  jest.clearAllMocks();
});

it("round-trips a session larger than one SecureStore value", async () => {
  expect(bytes(SESSION)).toBeGreaterThan(2048);
  await storage.setItem(KEY, SESSION);
  expect(await storage.getItem(KEY)).toBe(SESSION);
  for (const [, value] of store.setItemAsync.mock.calls as [string, string][]) {
    expect(bytes(value)).toBeLessThanOrEqual(2048);
  }
});

it("every chunk stays under the cap even when every character is 3 bytes", () => {
  const worst = "€".repeat(CHUNK_CHARS * 4 + 1);
  for (const c of chunkValue(worst)) expect(bytes(c)).toBeLessThanOrEqual(2048);
  expect(chunkValue(worst).join("")).toBe(worst);
});

it("a shorter value replaces a longer one with no stale chunks left behind", async () => {
  await storage.setItem(KEY, SESSION);
  await storage.setItem(KEY, "short");
  expect(await storage.getItem(KEY)).toBe("short");
  expect(await store.getItemAsync(`${KEY}.1`)).toBeNull();
});

it("removeItem clears the count and every chunk; a missing chunk reads as no session", async () => {
  await storage.setItem(KEY, SESSION);
  await storage.removeItem(KEY);
  expect(await storage.getItem(KEY)).toBeNull();
  expect(await store.getItemAsync(`${KEY}.0`)).toBeNull();

  await storage.setItem(KEY, SESSION);
  await store.deleteItemAsync(`${KEY}.1`); // a hole
  expect(await storage.getItem(KEY)).toBeNull();
});
