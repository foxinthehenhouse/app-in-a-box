/**
 * Push client with expo-notifications mocked: contextual permission, token with the
 * EAS projectId, register/unregister through the backend adapter, success AND
 * failure analytics, and a no-op (module never loaded) where push can't work.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import { ApiError } from "../api";
import {
  PUSH_TOKEN_KEY,
  disablePush,
  enablePush,
  pushStatus,
  pushSupported,
  refreshPushRegistration,
  routeFromNotification,
  storedPushToken,
} from "../push";

const TOKEN = "ExponentPushToken[abc123]";

// jest-expo's default preset runs as iOS (Platform.OS === "ios").
jest.mock("expo-device", () => ({ __esModule: true, isDevice: true }));
jest.mock("expo-constants", () => ({
  __esModule: true,
  ExecutionEnvironment: { StoreClient: "storeClient", Standalone: "standalone" },
  default: { executionEnvironment: "standalone", expoConfig: { extra: { eas: { projectId: "proj-1" } } } },
}));
jest.mock("expo-router", () => ({ router: { push: jest.fn() } }));
jest.mock("expo-notifications", () => ({
  setNotificationHandler: jest.fn(),
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(async () => ({ data: "ExponentPushToken[abc123]" })),
  setNotificationChannelAsync: jest.fn(),
  AndroidImportance: { DEFAULT: 3 },
}));
jest.mock("../supabase", () => ({ supabase: {}, signOutThisDevice: jest.fn(), currentUserId: jest.fn() }));
jest.mock("../analytics", () => ({
  analytics: { apiFailed: jest.fn(), pushChanged: jest.fn() },
  startTimer: () => () => 5,
}));
jest.mock("../api", () => ({
  ...jest.requireActual("../api"),
  registerPushToken: jest.fn(async () => undefined),
  unregisterPushToken: jest.fn(async () => undefined),
}));

const N = jest.requireMock("expo-notifications") as Record<string, jest.Mock>;
const device = jest.requireMock("expo-device") as { isDevice: boolean };
const api = jest.requireMock("../api") as { registerPushToken: jest.Mock; unregisterPushToken: jest.Mock };
const { analytics } = jest.requireMock("../analytics") as { analytics: { pushChanged: jest.Mock } };
const supa = jest.requireMock("../supabase") as { currentUserId: jest.Mock };

const granted = { granted: true, canAskAgain: true };
const undetermined = { granted: false, canAskAgain: true };
const blocked = { granted: false, canAskAgain: false };

beforeEach(async () => {
  jest.clearAllMocks();
  device.isDevice = true;
  supa.currentUserId.mockResolvedValue("user-a");
  await AsyncStorage.clear();
});

it("is supported on a real device build with a projectId", () => {
  expect(pushSupported()).toBe(true);
});

it("asks only when enabling, registers the token, and remembers it", async () => {
  N.getPermissionsAsync!.mockResolvedValue(undetermined);
  N.requestPermissionsAsync!.mockResolvedValue(granted);
  await expect(enablePush()).resolves.toBe("enabled");
  expect(N.requestPermissionsAsync).toHaveBeenCalledTimes(1);
  expect(N.getExpoPushTokenAsync).toHaveBeenCalledWith({ projectId: "proj-1" });
  expect(api.registerPushToken).toHaveBeenCalledWith(TOKEN, "ios");
  expect(await storedPushToken()).toBe(TOKEN);
  expect(JSON.parse((await AsyncStorage.getItem(PUSH_TOKEN_KEY)) ?? "{}")).toEqual({ token: TOKEN, userId: "user-a" });
  expect(analytics.pushChanged).toHaveBeenCalledWith({
    enabled: true,
    outcome: "enabled",
    success: true,
    error_code: null,
    duration_ms: 5,
  });
  N.getPermissionsAsync!.mockResolvedValue(granted); // the OS now reports the grant
  await expect(pushStatus()).resolves.toBe("enabled");
});

it("reads status without prompting", async () => {
  N.getPermissionsAsync!.mockResolvedValue(undetermined);
  await expect(pushStatus()).resolves.toBe("disabled");
  N.getPermissionsAsync!.mockResolvedValue(blocked);
  await expect(pushStatus()).resolves.toBe("denied");
  expect(N.requestPermissionsAsync).not.toHaveBeenCalled();
});

it("a denial registers nothing", async () => {
  N.getPermissionsAsync!.mockResolvedValue(undetermined);
  N.requestPermissionsAsync!.mockResolvedValue(blocked);
  await expect(enablePush()).resolves.toBe("denied");
  expect(api.registerPushToken).not.toHaveBeenCalled();
  expect(await AsyncStorage.getItem(PUSH_TOKEN_KEY)).toBeNull();
});

it("a backend failure is an error outcome with a failure event, and nothing is stored", async () => {
  N.getPermissionsAsync!.mockResolvedValue(granted);
  api.registerPushToken.mockRejectedValueOnce(new ApiError("down", 503));
  await expect(enablePush()).resolves.toBe("error");
  expect(await AsyncStorage.getItem(PUSH_TOKEN_KEY)).toBeNull();
  expect(analytics.pushChanged).toHaveBeenCalledWith(
    expect.objectContaining({ success: false, outcome: "error", error_code: "http_503" }),
  );
});

it("disabling unregisters this device's token, then forgets it", async () => {
  await AsyncStorage.setItem(PUSH_TOKEN_KEY, JSON.stringify({ token: TOKEN, userId: "user-a" }));
  await expect(disablePush()).resolves.toBe("disabled");
  expect(api.unregisterPushToken).toHaveBeenCalledWith(TOKEN);
  expect(await AsyncStorage.getItem(PUSH_TOKEN_KEY)).toBeNull();
  expect(analytics.pushChanged).toHaveBeenCalledWith(expect.objectContaining({ enabled: false, success: true }));
});

it("disabling with nothing registered is a silent no-op", async () => {
  await expect(disablePush()).resolves.toBe("disabled");
  expect(api.unregisterPushToken).not.toHaveBeenCalled();
  expect(analytics.pushChanged).not.toHaveBeenCalled();
});

it("is a no-op on a simulator: no prompt, no token, no backend call", async () => {
  device.isDevice = false;
  expect(pushSupported()).toBe(false);
  await expect(pushStatus()).resolves.toBe("unsupported");
  await expect(enablePush()).resolves.toBe("unsupported");
  expect(N.getPermissionsAsync).not.toHaveBeenCalled();
  expect(api.registerPushToken).not.toHaveBeenCalled();
});

describe("notification taps", () => {
  it("open only linkable routes from data.url", () => {
    expect(routeFromNotification({ url: "/settings" })).toBe("/settings");
    expect(routeFromNotification({ url: "https://evil.example.com/settings" })).toBeNull();
    expect(routeFromNotification({ url: "/gallery" })).toBeNull();
    expect(routeFromNotification({ screen: "/settings" })).toBeNull();
    expect(routeFromNotification(null)).toBeNull();
  });
});

describe("the remembered token belongs to the user who opted in", () => {
  it("A opts in, A's session ends by a 401 (no endSession), B signs in: B is never registered, toggle off", async () => {
    N.getPermissionsAsync!.mockResolvedValue(granted);
    await expect(enablePush()).resolves.toBe("enabled"); // user A opts in
    api.registerPushToken.mockClear();

    supa.currentUserId.mockResolvedValue("user-b"); // a 401 signed A out; B signs in on this device
    await refreshPushRegistration(); // what usePushNavigation runs on B's launch
    expect(api.registerPushToken).not.toHaveBeenCalled();
    await expect(pushStatus()).resolves.toBe("disabled");
    await expect(disablePush()).resolves.toBe("disabled");
    expect(api.unregisterPushToken).not.toHaveBeenCalled(); // never unregister A's token as B
  });

  it("the owner's launch still refreshes the registration", async () => {
    N.getPermissionsAsync!.mockResolvedValue(granted);
    await enablePush();
    api.registerPushToken.mockClear();
    await refreshPushRegistration();
    expect(api.registerPushToken).toHaveBeenCalledWith(TOKEN, "ios");
  });
});
