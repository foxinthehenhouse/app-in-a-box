/**
 * Signed-out group. A layout makes "(auth)" a real route the root Stack.Protected
 * guard can name; without it the group's screens float loose in the root Stack.
 */
import { Stack } from "expo-router";

import { useTheme } from "../../lib/theme";

export default function AuthLayout() {
  const t = useTheme();
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: t.color.bg } }} />;
}
