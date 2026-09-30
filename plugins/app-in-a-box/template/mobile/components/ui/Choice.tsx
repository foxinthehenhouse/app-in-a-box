/**
 * Chip and SegmentedControl: selection with a "selection" haptic (no commitment).
 * Selected state is exposed to screen readers and shown by fill + weight, never
 * by colour alone.
 *
 * SegmentedControl is the platform's own control on iOS and Android (@expo/ui:
 * a SwiftUI segmented Picker, Liquid Glass on iOS 26; Material on Android), so it
 * looks, moves and reads to VoiceOver/TalkBack like every other app. Web draws the
 * themed version below (same API), since @expo/ui's web layer is still experimental.
 */
import { useState } from "react";
import { Platform, View, type LayoutChangeEvent } from "react-native";
import { SegmentedControl as NativeSegmentedControl } from "@expo/ui/community/segmented-control";
import Animated, { useAnimatedStyle, useSharedValue } from "react-native-reanimated";

import { haptic, springTo } from "../../lib/motion";
import { makeStyles, useTheme } from "../../lib/theme";
import { PressableScale } from "./PressableScale";
import { Text } from "./Text";

export interface ChipProps {
  label: string;
  selected?: boolean;
  onPress: () => void;
  testID?: string;
}

export function Chip({ label, selected = false, onPress, testID }: ChipProps) {
  const s = useStyles();
  return (
    <PressableScale
      onPress={onPress}
      haptic="selection"
      accessibilityRole="togglebutton"
      accessibilityLabel={label}
      accessibilityState={{ checked: selected }}
      testID={testID}
      style={[s.chip, selected ? s.chipOn : null]}
    >
      <Text variant="secondary" tone={selected ? "onAccent" : "default"} style={selected ? s.bold : null}>
        {selected ? `✓ ${label}` : label}
      </Text>
    </PressableScale>
  );
}

export interface SegmentedControlProps<V extends string> {
  options: readonly { value: V; label: string }[];
  value: V;
  onChange: (value: V) => void;
  /** What the group chooses, e.g. "Appearance". */
  accessibilityLabel: string;
  testID?: string;
}

export function SegmentedControl<V extends string>(props: SegmentedControlProps<V>) {
  return Platform.OS === "web" ? <ThemedSegmentedControl {...props} /> : <PlatformSegmentedControl {...props} />;
}

function PlatformSegmentedControl<V extends string>({ options, value, onChange, testID }: SegmentedControlProps<V>) {
  const t = useTheme();
  // The group's name is the visible Section title above it; each native segment
  // announces its own label, selected state and position.
  return (
    <View testID={testID}>
      <NativeSegmentedControl
        values={options.map((o) => o.label)}
        selectedIndex={Math.max(0, options.findIndex((o) => o.value === value))}
        onChange={(e) => {
          const next = options[e.nativeEvent.selectedSegmentIndex];
          if (!next || next.value === value) return;
          haptic.selection();
          onChange(next.value);
        }}
        appearance={t.isDark ? "dark" : "light"}
        tintColor={t.color.accent}
      />
    </View>
  );
}

function ThemedSegmentedControl<V extends string>({
  options,
  value,
  onChange,
  accessibilityLabel,
  testID,
}: SegmentedControlProps<V>) {
  const t = useTheme();
  const s = useStyles();
  const [width, setWidth] = useState(0);
  const index = Math.max(0, options.findIndex((o) => o.value === value));
  const segment = options.length ? width / options.length : 0;
  const x = useSharedValue(0);
  const thumb = useAnimatedStyle(() => ({ transform: [{ translateX: x.get() }] }));

  function onLayout(e: LayoutChangeEvent) {
    const w = e.nativeEvent.layout.width - t.space.xs * 2;
    setWidth(w);
    x.set(index * (w / Math.max(1, options.length)));
  }

  return (
    <View
      style={s.track}
      onLayout={onLayout}
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    >
      {segment > 0 ? <Animated.View pointerEvents="none" style={[s.thumb, { width: segment }, thumb]} /> : null}
      {options.map((o, i) => {
        const on = o.value === value;
        return (
          <PressableScale
            key={o.value}
            onPress={() => {
              if (on) return;
              x.set(springTo(i * segment, "snappy"));
              onChange(o.value);
            }}
            haptic="selection"
            pressTint={false}
            // "button" + selected, not "radio": RN maps radio to no iOS trait at
            // all, so VoiceOver wouldn't announce the segment as actionable.
            accessibilityRole="button"
            accessibilityLabel={o.label}
            accessibilityState={{ selected: on }}
            testID={testID ? `${testID}-${o.value}` : undefined}
            style={s.segment}
          >
            <Text variant="secondary" tone={on ? "default" : "dim"} style={on ? s.bold : null}>
              {o.label}
            </Text>
          </PressableScale>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  chip: {
    minHeight: t.minTapTarget,
    paddingHorizontal: t.space.md,
    borderRadius: t.radius.pill,
    backgroundColor: t.color.control,
    borderWidth: 1,
    borderColor: t.color.border,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  chipOn: { backgroundColor: t.color.accent, borderColor: t.color.accent },
  bold: { fontWeight: "700" },
  track: {
    flexDirection: "row",
    padding: t.space.xs,
    borderRadius: t.radius.md,
    backgroundColor: t.color.control,
    borderWidth: 1,
    borderColor: t.color.border,
  },
  thumb: {
    position: "absolute",
    top: t.space.xs,
    bottom: t.space.xs,
    left: t.space.xs,
    borderRadius: t.radius.sm,
    backgroundColor: t.color.surfaceRaised,
    ...t.elevation.card,
  },
  segment: {
    flex: 1,
    minHeight: t.minTapTarget - t.space.xs * 2,
    alignItems: "center",
    justifyContent: "center",
  },
}));
