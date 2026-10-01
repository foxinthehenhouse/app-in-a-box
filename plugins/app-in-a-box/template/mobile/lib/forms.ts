/**
 * Forms: react-hook-form + zod. Schemas live here (pure, unit-tested), screens
 * bind them with <FormField> (components/ui/FormField.tsx).
 *
 *   const form = useForm<NameForm>({ resolver: zodResolver(nameSchema), defaultValues, mode: "onChange" });
 *   <FormField control={form.control} name="displayName" label={t("editName.label")} />
 *   <Button onPress={form.handleSubmit(save)} disabled={!form.formState.isValid} />
 *
 * Messages are i18n KEYS ("validation.required"), translated by FormField, so a
 * schema never hardcodes English. Keep limits in sync with the backend's Pydantic
 * `Field(max_length=...)`: the server is the authority, the form is the courtesy.
 */
import { z } from "zod";

/** backend/routers/me.py ProfileUpdate.display_name: max_length=80 */
export const DISPLAY_NAME_MAX = 80;

export const nameSchema = z.object({
  displayName: z.string().trim().min(1, "validation.required").max(DISPLAY_NAME_MAX, "validation.tooLong"),
});
export type NameForm = z.infer<typeof nameSchema>;

export const emailSchema = z.object({
  email: z.string().trim().min(1, "validation.required").pipe(z.email("validation.email")),
});
export type EmailForm = z.infer<typeof emailSchema>;

export const codeSchema = z.object({
  code: z.string().trim().regex(/^\d{6}$/, "validation.code"),
});
export type CodeForm = z.infer<typeof codeSchema>;

/** Account deletion: the user types the literal word, like the API's `{"confirm": "DELETE"}`. */
export const deleteConfirmSchema = z.object({
  // `: boolean` keeps this from being a type predicate, so the form value stays a string.
  confirm: z.string().trim().refine((v): boolean => v === "DELETE", "validation.typeDelete"),
});
export type DeleteConfirmForm = z.infer<typeof deleteConfirmSchema>;

/** Interpolation values for a message key (e.g. the max length in "validation.tooLong"). */
export const MESSAGE_VALUES: Record<string, Record<string, unknown>> = {
  "validation.tooLong": { max: DISPLAY_NAME_MAX },
};

/** First error message key for a value, or null when valid. For tests and non-RHF callers. */
export function firstError<S extends z.ZodType>(schema: S, value: unknown): string | null {
  const r = schema.safeParse(value);
  return r.success ? null : (r.error.issues[0]?.message ?? "validation.required");
}
