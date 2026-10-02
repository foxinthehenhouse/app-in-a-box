/**
 * The Supabase session on the device keychain / keystore (expo-secure-store), not in
 * AsyncStorage (plain, app-sandbox-only storage). ⚖️ Kyle 2026-10-02.
 *
 * SecureStore caps a VALUE at 2048 bytes (it warns today and may throw in a future
 * SDK). A Supabase session (access JWT + refresh token + user) is typically 2–4 KB, so
 * a value is split into chunks of CHUNK_CHARS UTF-16 code units (<= 3 bytes each in
 * UTF-8, so every chunk stays under the cap even for non-ASCII emails), stored as
 * `<key>.<i>`, with the chunk COUNT at `<key>`. Reads reassemble; a missing chunk reads
 * as "no session" (signed out) rather than a corrupt one; shrinking deletes leftovers.
 *
 * Web has no SecureStore: lib/supabase.ts leaves `storage` undefined there and
 * supabase-js uses localStorage. Pure chunking is exported for tests; the storage
 * adapter takes the store as a parameter so the 2048-byte limit can be enforced in tests.
 */
import * as SecureStore from "expo-secure-store";

/** 640 code units x 3 bytes worst case = 1920 bytes, under SecureStore's 2048 limit. */
export const CHUNK_CHARS = 640;

export interface KeyValueStore {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
}

/** What supabase-js's `auth.storage` wants. */
export interface SessionStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export function chunkValue(value: string, size: number = CHUNK_CHARS): string[] {
  const out: string[] = [];
  for (let i = 0; i < value.length; i += size) out.push(value.slice(i, i + size));
  return out.length ? out : [""];
}

const chunkKey = (key: string, i: number) => `${key}.${i}`;

async function readCount(store: KeyValueStore, key: string): Promise<number> {
  const raw = await store.getItemAsync(key);
  const n = raw === null ? 0 : Number(raw);
  return Number.isInteger(n) && n > 0 ? n : 0;
}

export function createSecureStorage(store: KeyValueStore = SecureStore): SessionStorage {
  return {
    async getItem(key) {
      const n = await readCount(store, key);
      if (!n) return null;
      const parts: string[] = [];
      for (let i = 0; i < n; i++) {
        const part = await store.getItemAsync(chunkKey(key, i));
        if (part === null) return null; // a hole = no usable session; the next sign-in overwrites it
        parts.push(part);
      }
      return parts.join("");
    },
    async setItem(key, value) {
      const previous = await readCount(store, key);
      const chunks = chunkValue(value);
      for (let i = 0; i < chunks.length; i++) await store.setItemAsync(chunkKey(key, i), chunks[i] ?? "");
      await store.setItemAsync(key, String(chunks.length)); // the count last: readers never see a partial write as complete
      for (let i = chunks.length; i < previous; i++) await store.deleteItemAsync(chunkKey(key, i));
    },
    async removeItem(key) {
      const n = await readCount(store, key);
      await store.deleteItemAsync(key); // the count first: a crash mid-way leaves orphans, never a readable half-session
      for (let i = 0; i < n; i++) await store.deleteItemAsync(chunkKey(key, i));
    },
  };
}
