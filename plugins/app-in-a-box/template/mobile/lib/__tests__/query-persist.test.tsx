/**
 * The persisted cache belongs to ONE user. If the session lapsed while the app was
 * closed (or someone else signs in), the cache on disk is another user's data:
 * it must be dropped on restore, never rendered, not even for a frame.
 */
import { Text } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { QueryClient, dehydrate } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { render, screen } from "@testing-library/react-native";

import type { Profile } from "../api";
import { CACHE_BUSTER, makeQueryClient, persistOptions, queryKeys, useMe } from "../query";

jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn(), currentUserId: jest.fn(async () => null) }));
jest.mock("../analytics", () => ({ analytics: { apiFailed: jest.fn() }, startTimer: () => () => 0 }));
jest.mock("../api", () => ({ ...jest.requireActual("../api"), getMe: jest.fn() }));

const api = jest.requireMock("../api") as { getMe: jest.Mock };
const supa = jest.requireMock("../supabase") as { currentUserId: jest.Mock };

const ALEX: Profile = { id: "user-a", displayName: "Alex", onboarded: true };
const BEA: Profile = { id: "user-b", displayName: "Bea", onboarded: true };
const CACHE_KEY = "app-query-cache";

/** What a previous launch left on disk: user A's profile, owned by A. */
async function persistCacheOf(profile: Profile, owner: string) {
  const c = new QueryClient();
  c.setQueryData(queryKeys.me, profile);
  await AsyncStorage.setItem(
    CACHE_KEY,
    JSON.stringify({ buster: CACHE_BUSTER, timestamp: Date.now(), clientState: dehydrate(c), owner }),
  );
  c.clear();
}

const seen: string[] = [];
function Name() {
  const me = useMe();
  const name = me.data?.displayName ?? "loading";
  seen.push(name);
  return <Text>{name}</Text>;
}

async function launch() {
  await render(
    <PersistQueryClientProvider client={makeQueryClient()} persistOptions={persistOptions}>
      <Name />
    </PersistQueryClientProvider>,
  );
}

beforeEach(async () => {
  seen.length = 0;
  await AsyncStorage.clear();
  api.getMe.mockReset();
});

it("drops A's persisted cache when the session lapsed; B signing in never sees A's data", async () => {
  await persistCacheOf(ALEX, "user-a");
  supa.currentUserId.mockResolvedValue(null); // A's session expired while the app was closed
  api.getMe.mockResolvedValue(BEA); // ...and B is who signs in
  await launch();
  expect(await screen.findByText("Bea")).toBeTruthy();
  expect(seen).not.toContain("Alex");
  expect(await AsyncStorage.getItem(CACHE_KEY)).not.toContain("Alex");
});

it("drops a cache owned by a different user than the restored session", async () => {
  await persistCacheOf(ALEX, "user-a");
  supa.currentUserId.mockResolvedValue("user-b");
  api.getMe.mockResolvedValue(BEA);
  await launch();
  expect(await screen.findByText("Bea")).toBeTruthy();
  expect(seen).not.toContain("Alex");
});

it("restores the cache for the user who owns it (offline-first still works)", async () => {
  await persistCacheOf(ALEX, "user-a");
  supa.currentUserId.mockResolvedValue("user-a");
  api.getMe.mockImplementation(() => new Promise(() => undefined)); // offline: no answer
  await launch();
  expect(await screen.findByText("Alex")).toBeTruthy();
});
