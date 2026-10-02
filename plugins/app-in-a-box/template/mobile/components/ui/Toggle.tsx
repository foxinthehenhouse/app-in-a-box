/**
 * Toggle: the platform switch, themed. Use it (not RN's Switch) for on/off settings,
 * usually as a ListRow's `trailing`. On iOS/Android it is the native control with the
 * accent track; on web, react-native-web draws it and falls back to its own teal for
 * the "on" thumb unless told otherwise, so this passes the theme there too.
 *
 * The native switch is ~31pt tall (UISwitch), under the 48pt minimum target, so it
 * sits centred in a 48pt box and its touch area is padded with hitSlop to fill that
 * box. The box is not an accessibility element; the switch keeps its own label.
 */
import { type ComponentType } from "react";
import { Switch, View, type SwitchProps } from "react-native";

import { makeStyles, useTheme } from "../../lib/theme";

/** UISwitch's intrinsic height; Android's switch is taller, so the padding there is generous, never short. */
const SWITCH_HEIGHT = 31;

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
  const s = useStyles();
  const slop = Math.max(0, Math.ceil((t.minTapTarget - SWITCH_HEIGHT) / 2));
  return (
    <View style={s.box}>
      <ThemedSwitch
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        accessibilityLabel={accessibilityLabel}
        trackColor={{ true: t.color.accent, false: t.color.border }}
        activeThumbColor={t.color.onAccent}
        hitSlop={{ top: slop, bottom: slop, left: slop, right: slop }}
        testID={testID}
      />
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  box: { minHeight: t.minTapTarget, minWidth: t.minTapTarget, alignItems: "center", justifyContent: "center" },
}));
