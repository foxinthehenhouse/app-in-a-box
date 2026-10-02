/**
 * AuthProvider + the query cache: a user change clears the cache WITHOUT
 * stranding the new user's screens. The cache used to be cleared in an effect
 * that ran after the signed-in screen had already subscribed and started
 * fetching, so `client.clear()` cancelled that fetch and the screen sat on its
 * skeleton forever (and an optimistic edit had no query to land in).
 */
import { Text } from "react-native";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react-native";

import type { Profile } from "../api";
import { AuthProvider, useAuth } from "../auth";
import { queryClient, useMe } from "../query";

type AuthListener = (event: string, session: { user: { id: string; email: string } } | null) => void;
const mockAuthListeners: AuthListener[] = [];

jest.mock("../supabase", () => ({
  supabase: {
    auth: {
      getSession: jest.fn(async () => ({ data: { session: null } })),
      onAuthStateChange: jest.fn((cb: AuthListener) => {
        mockAuthListeners.push(cb);
        return { data: { subscription: { unsubscribe: jest.fn() } } };
      }),
    },
  },
  signOutThisDevice: jest.fn(),
  currentUserId: jest.fn(async () => null),
}));
jest.mock("../analytics", () => ({
  analytics: { apiFailed: jest.fn(), profileUpdated: jest.fn() },
  identifyUser: jest.fn(),
  resetAnalytics: jest.fn(),
  startTimer: () => () => 0,
}));
jest.mock("../api", () => ({ ...jest.requireActual("../api"), getMe: jest.fn() }));

const api = jest.requireMock("../api") as { getMe: jest.Mock };
const supabaseMock = jest.requireMock("../supabase") as { supabase: { auth: { getSession: jest.Mock } } };

const PROFILES: Record<string, Profile> = {
  "user-a": { id: "user-a", displayName: "Alex", onboarded: true },
  "user-b": { id: "user-b", displayName: "Bea", onboarded: true },
};
let currentUser = "user-b";

function Name() {
  const me = useMe();
  return <Text testID="name">{me.data?.displayName ?? "loading"}</Text>;
}

function Gate() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? <Name /> : <Text>signed out</Text>;
}

async function mount() {
  await render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

async function emit(userId: string | null) {
  currentUser = userId ?? currentUser;
  await act(async () => {
    for (const l of mockAuthListeners) l(userId ? "SIGNED_IN" : "SIGNED_OUT", userId ? { user: { id: userId, email: `${userId}@x.co` } } : null);
  });
}

beforeEach(() => {
  mockAuthListeners.length = 0;
  queryClient.clear();
  supabaseMock.supabase.auth.getSession.mockImplementation(async () => ({ data: { session: null } }));
  // A slow network: the fetch is still in flight when the auth change settles.
  api.getMe.mockImplementation(
    () => new Promise((resolve) => setTimeout(() => resolve(PROFILES[currentUser]), 30)),
  );
});

it("a fresh sign-in (signed out -> B) shows B's data instead of a skeleton forever", async () => {
  await mount();
  expect(await screen.findByText("signed out")).toBeTruthy();
  await emit("user-b");
  expect(await screen.findByText("Bea", {}, { timeout: 2000 })).toBeTruthy();
});

it("switching accounts (A -> B) drops A's data and loads B's", async () => {
  await mount();
  // Let the stored-session read settle first (as the test above does): emitting before it
  // resolves lets its "no session" result land after A's sign-in and overwrite it.
  expect(await screen.findByText("signed out")).toBeTruthy();
  await emit("user-a");
  expect(await screen.findByText("Alex", {}, { timeout: 2000 })).toBeTruthy();
  await emit("user-b");
  expect(await screen.findByText("Bea", {}, { timeout: 2000 })).toBeTruthy();
  expect(screen.queryByText("Alex")).toBeNull();
});

it("clears the splash even when reading the stored session fails", async () => {
  supabaseMock.supabase.auth.getSession.mockImplementation(async () => {
    throw new Error("storage unavailable");
  });
  await mount();
  expect(await screen.findByText("signed out")).toBeTruthy();
});
