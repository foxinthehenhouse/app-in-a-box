/**
 * Field: a labelled text input.
 *
 * FULLY CONTROLLED on purpose. It never copies `value` into its own state, so a
 * parent that loads data after mount (a profile fetch) always shows it. An
 * input that captures its value at mount and never re-reads the prop renders a
 * blank field over real data, and a Save then writes the blank back: silent
 * data loss that a testID-only test won't catch (see __tests__/Field.test.tsx).
 *
 * For forms seeded from a fetch, still prefer: fetch -> skeleton -> mount the
 * form with `useState(() => fetched.value)`, so edits start from real data.
 */
import { useState } from "react";
import { TextInput, View, type TextInputProps } from "react-native";

import { makeStyles, useTheme } from "../../lib/theme";
import { ErrorText, Text } from "./Text";

export interface FieldProps extends Omit<TextInputProps, "style" | "value" | "onChangeText"> {
  label: string;
  value: string;
  onChangeText: (text: string) => void;
  hint?: string;
  error?: string | null;
}

export function Field({ label, value, onChangeText, hint, error, testID, onFocus, onBlur, ...rest }: FieldProps) {
  const t = useTheme();
  const s = useStyles();
  const [focused, setFocused] = useState(false);
  return (
    <View style={s.wrap}>
      <Text variant="meta" nativeID={testID ? `${testID}-label` : undefined}>
        {label}
      </Text>
      <TextInput
        {...rest}
        value={value}
        onChangeText={onChangeText}
        testID={testID}
        accessibilityLabel={label}
        accessibilityHint={hint}
        accessibilityLabelledBy={testID ? `${testID}-label` : undefined}
        placeholderTextColor={t.color.inkFaint}
        selectionColor={t.color.accent}
        cursorColor={t.color.accent}
        maxFontSizeMultiplier={t.typeScale.body}
        onFocus={(e) => {
          setFocused(true);
          onFocus?.(e);
        }}
        onBlur={(e) => {
          setFocused(false);
          onBlur?.(e);
        }}
        style={[t.type.body, s.input, focused ? s.focused : null, error ? s.invalid : null]}
      />
      {error ? <ErrorText>{error}</ErrorText> : hint ? <Text variant="secondary">{hint}</Text> : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: t.space.xs },
  input: {
    minHeight: t.minTapTarget,
    backgroundColor: t.color.control,
    borderRadius: t.radius.md,
    paddingHorizontal: t.space.md,
    paddingVertical: t.space.sm,
    borderWidth: 1,
    borderColor: t.color.border,
  },
  focused: { borderColor: t.color.accent },
  invalid: { borderColor: t.color.danger },
}));
