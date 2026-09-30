/**
 * Root layout: providers, the auth gate and the root Stack.
 *
 * The gate is declarative (`Stack.Protected`): signed-out users can only reach
 * (auth), signed-in users only (app) and the sheets. Never `router.replace`
 * into a group to "log someone in"; change auth state and the guard redirects.
 * Sheets (formSheet routes) are registered here, once, and nowhere else.
 *
 * Also mounted here, once: the persisted TanStack Query cache (offline-first,
 * lib/query.ts), the offline banner, the OTA "update ready" prompt
 * (lib/updates.ts) and notification-tap routing (lib/push.ts). Deep links from
 * the OS are mapped in app/+native-intent.tsx.
 */
import { useEffect } from "react";
import Constants, { ExecutionEnvironment } from "expo-constants";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import * as SystemUI from "expo-system-ui";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";

import { OfflineBanner, ToastProvider, UpdateBanner } from "../components/ui";
import { AuthProvider, useAuth } from "../lib/auth";
import "../lib/i18n";
import { usePendingLinkReplay } from "../lib/links";
import { initMonitoring, wrapRoot } from "../lib/monitoring";
import { usePushNavigation } from "../lib/push";
import { persistOptions, queryClient, wireConnectivity } from "../lib/query";
import { ThemeProvider, useTheme, useThemePreference } from "../lib/theme";
import { useUpdatePrompt } from "../lib/updates";

initMonitoring();
wireConnectivity();
SplashScreen.preventAutoHideAsync().catch(() => undefined);
// Expo Go owns its splash; the fade only applies to your own builds.
if (Constants.executionEnvironment !== ExecutionEnvironment.StoreClient) {
  SplashScreen.setOptions({ fade: true, duration: 250 });
}

function RootStack() {
  const { user, loading } = useAuth();
  const { ready } = useThemePreference();
  const t = useTheme();
  const update = useUpdatePrompt();
  usePushNavigation(user !== null);
  usePendingLinkReplay(user !== null, loading || !ready);

  useEffect(() => {
    SystemUI.setBackgroundColorAsync(t.color.bg).catch(() => undefined);
  }, [t.color.bg]);

  useEffect(() => {
    if (!loading && ready) SplashScreen.hideAsync().catch(() => undefined);
  }, [loading, ready]);

  if (loading || !ready) return null; // the splash stays up until auth + theme are known

  const signedIn = user !== null;
  return (
    <>
      <StatusBar style={t.isDark ? "light" : "dark"} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: t.color.bg } }}>
        <Stack.Protected guard={signedIn}>
          <Stack.Screen name="(app)" />
          <Stack.Screen
            name="edit-name"
            options={{
              presentation: "formSheet",
              sheetAllowedDetents: [0.45, 0.9],
              sheetGrabberVisible: true,
              sheetCornerRadius: t.radius.lg,
              contentStyle: { backgroundColor: t.color.surface },
            }}
          />
          <Stack.Screen
            name="delete-account"
            options={{
              presentation: "formSheet",
              sheetAllowedDetents: [0.75, 1],
              sheetGrabberVisible: true,
              sheetCornerRadius: t.radius.lg,
              contentStyle: { backgroundColor: t.color.surface },
            }}
          />
        </Stack.Protected>
        <Stack.Protected guard={!signedIn}>
          <Stack.Screen name="(auth)" />
        </Stack.Protected>
        <Stack.Protected guard={__DEV__}>
          <Stack.Screen name="gallery" options={{ presentation: "modal" }} />
        </Stack.Protected>
      </Stack>
      <OfflineBanner />
      <UpdateBanner visible={update.ready} onRestart={update.restart} onLater={update.dismiss} />
    </>
  );
}

function RootLayout() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <PersistQueryClientProvider
        client={queryClient}
        persistOptions={persistOptions}
        // Replay edits queued offline in a previous session, once the cache is back.
        onSuccess={() => void queryClient.resumePausedMutations()}
      >
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider>
              <RootStack />
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </PersistQueryClientProvider>
    </GestureHandlerRootView>
  );
}

export default wrapRoot(RootLayout);
