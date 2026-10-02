/**
 * Root layout: providers, the auth gate and the root Stack.
 *
 * The gate is declarative (`Stack.Protected`): signed-out users can only reach
 * (auth), signed-in users only (app) and the sheets. Never `router.replace`
 * into a group to "log someone in"; change auth state and the guard redirects.
 * Sheets (formSheet routes) are registered here, once, and nowhere else.
 *
 * Custom fonts (lib/fonts.ts) load here too; the splash stays up until they're in.
 *
 * Also mounted here, once: the persisted TanStack Query cache (offline-first,
 * lib/query.ts), the offline banner, the OTA "update ready" prompt
 * (lib/updates.ts) and notification-tap routing (lib/push.ts). Deep links from
 * the OS are mapped in app/+native-intent.tsx.
 */
import { useEffect } from "react";
import Constants, { ExecutionEnvironment } from "expo-constants";
import { useFonts } from "expo-font";
import { Stack, type ErrorBoundaryProps } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import * as SystemUI from "expo-system-ui";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";

import { Button, EmptyState, OfflineBanner, Screen, ToastProvider, UpdateBanner } from "../components/ui";
import { AuthProvider, useAuth } from "../lib/auth";
import { MISSING_CONFIG, configured } from "../lib/config";
import { fontAssets } from "../lib/fonts";
import { useT } from "../lib/i18n";
import { usePendingLinkReplay } from "../lib/links";
import { initMonitoring, reportError, wrapRoot } from "../lib/monitoring";
import { usePushNavigation } from "../lib/push";
import { persistOptions, queryClient, wireConnectivity } from "../lib/query";
import { ThemeProvider, useTheme, useThemePreference } from "../lib/theme";
import { useUpdatePrompt } from "../lib/updates";

initMonitoring();
// A build missing its server settings is reported once, at boot, with the names of what
// is missing (never values). Users see t("errors.misconfigured") on sign-in and on calls.
if (!configured) reportError(new Error("App build is missing configuration"), { missing: MISSING_CONFIG.join(",") });
wireConnectivity();
SplashScreen.preventAutoHideAsync().catch(() => undefined);
// Expo Go owns its splash; the fade only applies to your own builds.
if (Constants.executionEnvironment !== ExecutionEnvironment.StoreClient) {
  SplashScreen.setOptions({ fade: true, duration: 250 });
}

function RootStack() {
  const { user, loading } = useAuth();
  const { ready: themeReady } = useThemePreference();
  // A font that fails to load falls back to the system font rather than hanging the splash.
  const [fontsLoaded, fontError] = useFonts(fontAssets);
  const ready = themeReady && (fontsLoaded || fontError !== null);
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

  if (loading || !ready) return null; // the splash stays up until auth, theme and fonts are known

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

/**
 * Expo Router renders this in place of the app when a route throws during render.
 * Themed (the theme hook falls back to the OS scheme outside its provider), reported
 * to monitoring, and recoverable: Retry re-renders the failed route.
 */
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  const t = useT();
  useEffect(() => {
    reportError(error, { boundary: "root" });
  }, [error]);
  return (
    <Screen scroll={false} edges={["top", "left", "right", "bottom"]} testID="root-error-boundary">
      <EmptyState
        icon={{ sf: "exclamationmark.triangle", md: "error" }}
        title={t("errorBoundary.title")}
        body={t("errorBoundary.body")}
        action={
          <Button
            label={t("errorBoundary.retry")}
            accessibilityLabel={t("errorBoundary.retryLabel")}
            onPress={() => void retry()}
            testID="root-error-retry-button"
          />
        }
      />
    </Screen>
  );
}
