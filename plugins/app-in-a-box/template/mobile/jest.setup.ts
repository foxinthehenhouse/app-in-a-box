/**
 * Jest setup (package.json `jest.setupFiles`, set by the kit's mobile-deps.sh).
 * Native modules with no JS fallback get their libraries' official mocks here,
 * once, so every test that renders the app (which mounts the query cache,
 * connectivity and the persister) works without per-file boilerplate.
 */
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);
jest.mock("@react-native-community/netinfo", () => require("@react-native-community/netinfo/jest/netinfo-mock.js"));
// supabase-js (realtime-js) refuses to construct without a global WebSocket, which the
// app has on every device and the browser but Node < 22 under jest does not. Tests never
// open a realtime socket, so an inert stand-in is enough for `createClient` to build.
if (typeof globalThis.WebSocket === "undefined") {
  class JestWebSocket {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    readyState = 3;
    close(): void {}
    send(): void {}
    addEventListener(): void {}
    removeEventListener(): void {}
  }
  (globalThis as { WebSocket?: unknown }).WebSocket = JestWebSocket;
}
// expo-secure-store has no JS fallback. This in-memory stand-in enforces the real
// 2048-byte value limit, so a test that stores an unchunked session fails here too.
// Seeded with one answer: the age gate's outcome (lib/age.ts, the `minors` guardrail
// pack). Every test runs as a user who is of age, so flows written before the pack was
// turned on still reach sign-in; lib/__tests__/age.test.ts clears it to test the gate.
jest.mock("expo-secure-store", () => {
  const items = new Map<string, string>([["age_policy", "ofAge"]]);
  return {
    getItem: jest.fn((key: string) => items.get(key) ?? null),
    getItemAsync: jest.fn(async (key: string) => items.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => {
      if (new TextEncoder().encode(value).length > 2048) throw new Error(`expo-secure-store: value for ${key} exceeds 2048 bytes`);
      items.set(key, value);
    }),
    deleteItemAsync: jest.fn(async (key: string) => {
      items.delete(key);
    }),
  };
});
