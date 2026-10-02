/**
 * The Supabase client is built on the chunked SecureStore adapter on native (jest-expo
 * runs as iOS); web leaves `storage` undefined so supabase-js uses localStorage.
 */
import * as SecureStore from "expo-secure-store";

jest.mock("@supabase/supabase-js", () => ({ createClient: jest.fn(() => ({ auth: {} })) }));

const { createClient } = jest.requireMock("@supabase/supabase-js") as { createClient: jest.Mock };
const secure = SecureStore as unknown as { setItemAsync: jest.Mock };

it("hands supabase-js the chunked SecureStore adapter on native", async () => {
  require("../supabase");
  const [, , options] = createClient.mock.calls[0] as [string, string, { auth: { storage?: unknown } }];
  const storage = options.auth.storage as { setItem: (k: string, v: string) => Promise<void>; getItem: (k: string) => Promise<string | null> };
  expect(storage).toBeDefined();
  const session = "v".repeat(3000); // > 2048 bytes: only storable through the chunked adapter
  await storage.setItem("sb-x-auth-token", session);
  expect(await storage.getItem("sb-x-auth-token")).toBe(session);
  // It went to SecureStore (in pieces), not to AsyncStorage.
  expect(secure.setItemAsync.mock.calls.filter(([k]) => String(k).startsWith("sb-x-auth-token.")).length).toBeGreaterThan(1);
});
