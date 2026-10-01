/**
 * Toggle: the platform switch, themed. Use it (not RN's Switch) for on/off settings,
 * usually as a ListRow's `trailing`. On iOS/Android it is the native control with the
 * accent track; on web, react-native-web draws it and falls back to its own teal for
 * the "on" thumb unless told otherwise, so this passes the theme there too.
 */
import { type ComponentType } from "react";
import { Switch, type SwitchProps } from "react-native";

import { useTheme } from "../../lib/theme";

// react-native-web's Switch also takes activeThumbColor (the "on" thumb); RN's types don't list it.
const ThemedSwitch = Switch as ComponentType<SwitchProps & { activeThumbColor?: string }>;

export interface ToggleProps {
  value: boolean;
  onValueChange: (value: boolean) => void;
  /** What it turns on: "Push notifications". */
  accessibilityLabel: string;
  disabled?: boolean;
  testID?: string;
}

export function Toggle({ value, onValueChange, accessibilityLabel, disabled, testID }: ToggleProps) {
  const t = useTheme();
  return (
    <ThemedSwitch
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
      accessibilityLabel={accessibilityLabel}
      trackColor={{ true: t.color.accent, false: t.color.border }}
      activeThumbColor={t.color.onAccent}
      testID={testID}
    />
  );
}
