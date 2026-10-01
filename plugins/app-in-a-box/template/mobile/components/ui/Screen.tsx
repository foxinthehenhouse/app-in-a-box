/**
 * Screen, Card and Section: the page scaffolding.
 *
 * Screen uses react-native-safe-area-context (RN's own SafeAreaView is
 * deprecated) and draws edge-to-edge: the background runs under the status bar
 * and home indicator, content is inset. Native tabs float over the bottom on
 * iOS 26, so the scroll view adjusts its insets automatically.
 */
import type { ReactNode } from "react";
import { RefreshControl, ScrollView, View, type StyleProp, type ViewStyle } from "react-native";
import Animated from "react-native-reanimated";
import { SafeAreaView, type Edge } from "react-native-safe-area-context";

import { entrance, useReducedMotion } from "../../lib/motion";
import { makeStyles, useTheme } from "../../lib/theme";
import { PressableScale } from "./PressableScale";
import { Meta } from "./Text";

export interface ScreenProps {
  children: ReactNode;
  testID?: string;
  /** Scrolls by default. Pass false for a fixed layout (e.g. a centred empty state). */
  scroll?: boolean;
  /** Tabs own the bottom inset; sheets and stack screens usually want it. */
  edges?: Edge[];
  /** Pull to refresh. */
  refreshing?: boolean;
  onRefresh?: () => void;
  /** Surface colour for sheets (formSheet routes). */
  sheet?: boolean;
}

export function Screen({
  children,
  testID,
  scroll = true,
  edges = ["top", "left", "right"],
  refreshing,
  onRefresh,
  sheet = false,
}: ScreenProps) {
  const t = useTheme();
  const s = useStyles();
  const bg = { backgroundColor: sheet ? t.color.surface : t.color.bg };
  return (
    <SafeAreaView style={[s.fill, bg]} edges={edges} testID={testID}>
      {scroll ? (
        <ScrollView
          contentContainerStyle={s.content}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="interactive"
          contentInsetAdjustmentBehavior="automatic"
          automaticallyAdjustKeyboardInsets
          refreshControl={
            onRefresh ? (
              <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={t.color.accent} />
            ) : undefined
          }
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[s.fill, s.content]}>{children}</View>
      )}
    </SafeAreaView>
  );
}

export interface CardProps {
  children: ReactNode;
  /** Pressable card: needs a purpose label. */
  onPress?: () => void;
  accessibilityLabel?: string;
  /** Stagger position for the entrance animation (omit for none). */
  index?: number;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

export function Card({ children, onPress, accessibilityLabel, index, style, testID }: CardProps) {
  const t = useTheme();
  const s = useStyles();
  const reduced = useReducedMotion();
  const body = [s.card, t.elevation.card, style];
  const inner = onPress ? (
    <PressableScale onPress={onPress} accessibilityRole="button" accessibilityLabel={accessibilityLabel} style={body} testID={testID}>
      {children}
    </PressableScale>
  ) : (
    <View style={body} testID={testID}>
      {children}
    </View>
  );
  if (index === undefined) return inner;
  return <Animated.View entering={entrance(index, reduced)}>{inner}</Animated.View>;
}

/** A titled group of content. */
export function Section({ title, children, testID }: { title: string; children: ReactNode; testID?: string }) {
  const s = useStyles();
  return (
    <View style={s.section} testID={testID}>
      <Meta accessibilityRole="header">{title}</Meta>
      {children}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  fill: { flex: 1 },
  content: { padding: t.space.lg, paddingBottom: t.space.xxl, gap: t.space.md },
  card: {
    backgroundColor: t.color.surfaceRaised,
    borderRadius: t.radius.lg,
    padding: t.space.lg,
    gap: t.space.sm,
    overflow: "hidden",
  },
  section: { gap: t.space.sm },
}));
