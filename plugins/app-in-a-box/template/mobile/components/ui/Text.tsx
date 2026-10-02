/**
 * Text roles. Every string on screen goes through <Text variant>, so type comes from
 * tokens (font, size, weight, line height, tracking) and Dynamic Type is capped
 * per role: body text scales up to 2x for low-vision users, display text less, so
 * a 40pt headline doesn't break the layout at the largest accessibility size.
 */
import type { ReactNode } from "react";
import { Text as RNText, type TextProps as RNTextProps } from "react-native";

import { useTheme, type Palette, type TypeRole } from "../../lib/theme";

/**
 * Text tones. Every key here is a palette token painted as TEXT, so
 * scripts/check_contrast.py (repo root) holds it to 4.5:1 on every surface. `success`
 * and `warning` are deliberately absent: they clear 3:1 as icons and dots but not 4.5:1
 * as text on every surface, and a success message is ink with a glyph, never green text.
 * Add a tone here and the gate starts checking that token as text.
 */
export type Tone = "default" | "dim" | "faint" | "accent" | "danger" | "onAccent";

const TONE: Record<Exclude<Tone, "default">, keyof Palette> = {
  dim: "inkDim",
  faint: "inkFaint",
  accent: "accent",
  danger: "danger",
  onAccent: "onAccent",
};

const HEADER_ROLES: ReadonlySet<TypeRole> = new Set(["display", "title", "heading"]);

export interface TextProps extends RNTextProps {
  variant?: TypeRole;
  tone?: Tone;
  children?: ReactNode;
}

export function Text({ variant = "body", tone = "default", style, children, ...rest }: TextProps) {
  const t = useTheme();
  return (
    <RNText
      accessibilityRole={HEADER_ROLES.has(variant) ? "header" : undefined}
      maxFontSizeMultiplier={t.typeScale[variant]}
      {...rest}
      style={[t.type[variant], tone === "default" ? null : { color: t.color[TONE[tone]] }, style]}
    >
      {children}
    </RNText>
  );
}

export const Display = (p: Omit<TextProps, "variant">) => <Text variant="display" {...p} />;
export const Title = (p: Omit<TextProps, "variant">) => <Text variant="title" {...p} />;
export const Heading = (p: Omit<TextProps, "variant">) => <Text variant="heading" {...p} />;
export const Meta = (p: Omit<TextProps, "variant">) => <Text variant="meta" {...p} />;

/** Body copy. `dim` = secondary role (smaller, inkDim). */
export function Body({ dim = false, ...p }: Omit<TextProps, "variant"> & { dim?: boolean }) {
  return <Text variant={dim ? "secondary" : "body"} {...p} />;
}

/** Announced error line. Carries a glyph so meaning is never colour alone. */
export function ErrorText({ children, testID }: { children: ReactNode; testID?: string }) {
  return (
    <Text variant="secondary" tone="danger" accessibilityRole="alert" accessibilityLiveRegion="polite" testID={testID}>
      {"⚠ "}
      {children}
    </Text>
  );
}
