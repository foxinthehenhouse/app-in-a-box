/**
 * Icon: SF Symbols on iOS, Material Symbols on Android and web (expo-symbols).
 * Pass both names: `<Icon sf="house.fill" md="home" />`. Browse SF names in
 * Apple's SF Symbols app and Material names at fonts.google.com/icons.
 *
 * Icons are decorative by default (hidden from screen readers) because the
 * control they sit in carries the label. Pass `label` for a standalone icon
 * that means something on its own.
 */
import { SymbolView, type AndroidSymbol, type SFSymbol } from "expo-symbols";

import { useTheme, type Palette } from "../../lib/theme";

export interface IconProps {
  sf: SFSymbol;
  md: AndroidSymbol;
  size?: number;
  color?: keyof Palette;
  label?: string;
  testID?: string;
}

export function Icon({ sf, md, size = 22, color = "ink", label, testID }: IconProps) {
  const t = useTheme();
  return (
    <SymbolView
      name={{ ios: sf, android: md, web: md }}
      size={size}
      tintColor={t.color[color]}
      testID={testID}
      accessible={!!label}
      accessibilityLabel={label}
      accessibilityRole={label ? "image" : undefined}
      accessibilityElementsHidden={!label}
      importantForAccessibility={label ? "yes" : "no-hide-descendants"}
      style={{ width: size, height: size }}
    />
  );
}
