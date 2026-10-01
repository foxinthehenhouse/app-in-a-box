/**
 * FormField: the design system's <Field>, bound to react-hook-form.
 *
 *   <FormField control={form.control} name="email" label={t("auth.email")} keyboardType="email-address" />
 *
 * - Value/onChange/onBlur come from the form (still fully controlled, like Field).
 * - The error is the zod message KEY, translated here (with MESSAGE_VALUES), and
 *   shown only once the field is touched or the form was submitted, so nobody
 *   gets "This can't be empty" before they've typed.
 * - `serverError` shows an API failure on the field (e.g. a 422 from save).
 */
import { useController, type Control, type FieldPath, type FieldValues } from "react-hook-form";

import { MESSAGE_VALUES } from "../../lib/forms";
import { translate } from "../../lib/i18n";
import { Field, type FieldProps } from "./Field";

export interface FormFieldProps<T extends FieldValues>
  extends Omit<FieldProps, "value" | "onChangeText" | "error"> {
  control: Control<T>;
  name: FieldPath<T>;
  serverError?: string | null;
}

export function FormField<T extends FieldValues>({ control, name, serverError, onBlur, ...rest }: FormFieldProps<T>) {
  const { field, fieldState, formState } = useController({ control, name });
  const key = fieldState.error?.message;
  const show = !!key && (fieldState.isTouched || formState.isSubmitted);
  const error = show && key ? translate(key, MESSAGE_VALUES[key]) : (serverError ?? null);
  return (
    <Field
      {...rest}
      value={typeof field.value === "string" ? field.value : String(field.value ?? "")}
      onChangeText={field.onChange}
      onBlur={(e) => {
        field.onBlur();
        onBlur?.(e);
      }}
      error={error}
    />
  );
}
