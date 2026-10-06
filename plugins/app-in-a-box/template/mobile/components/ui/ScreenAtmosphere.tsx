/**
 * ScreenAtmosphere: the light a screen sits in, frozen from the prototype into
 * design/tokens.json `atmosphere` (see lib/atmosphere.ts).
 *
 * Two radial lights at the frozen geometry, colours and contrast-capped alpha,
 * plus an optional static film grain. Mode `none` with grain off renders nothing.
 * It is decoration: painted behind the content (never over text), invisible to
 * screen readers and touches, and still. <Screen> mounts it; a custom full-screen
 * layout can mount it as its first child.
 */
import { Image, StyleSheet, View } from "react-native";

import { atmosphereGradient, grainStyle, grainTile } from "../../lib/atmosphere";
import { useTheme } from "../../lib/theme";

export function ScreenAtmosphere({ testID }: { testID?: string }) {
  const { scheme } = useTheme();
  const gradient = atmosphereGradient(scheme);
  const grain = grainStyle(scheme);
  if (!gradient && !grain) return null;
  return (
    <View
      style={[s.layer, gradient ? { experimental_backgroundImage: gradient } : null]}
      accessible={false}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      testID={testID}
    >
      {grain ? <Image source={{ uri: grainTile }} resizeMode="repeat" accessible={false} style={[s.grain, grain]} /> : null}
    </View>
  );
}

// No colours here (they come from the tokens per scheme), so a static sheet is safe.
const s = StyleSheet.create({
  layer: { ...StyleSheet.absoluteFill, pointerEvents: "none" },
  grain: StyleSheet.absoluteFill,
});
