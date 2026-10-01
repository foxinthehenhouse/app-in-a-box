/**
 * Forms: zod schemas (messages are i18n keys) and <FormField> bound to
 * react-hook-form: translated errors, shown only once the field is touched.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { useForm } from "react-hook-form";

import { FormField } from "../../components/ui";
import {
  DISPLAY_NAME_MAX,
  codeSchema,
  deleteConfirmSchema,
  emailSchema,
  firstError,
  nameSchema,
  type NameForm,
} from "../forms";
import { en } from "../../locales/en";

describe("schemas", () => {
  it.each([
    [nameSchema, { displayName: "Sam" }, null],
    [nameSchema, { displayName: "   " }, "validation.required"],
    [nameSchema, { displayName: "x".repeat(DISPLAY_NAME_MAX + 1) }, "validation.tooLong"],
    [nameSchema, { displayName: "x".repeat(DISPLAY_NAME_MAX) }, null],
    [emailSchema, { email: "sam@example.com" }, null],
    [emailSchema, { email: " sam@example.com " }, null],
    [emailSchema, { email: "" }, "validation.required"],
    [emailSchema, { email: "sam@" }, "validation.email"],
    [codeSchema, { code: "123456" }, null],
    [codeSchema, { code: "12345" }, "validation.code"],
    [codeSchema, { code: "12a456" }, "validation.code"],
    [deleteConfirmSchema, { confirm: "DELETE" }, null],
    [deleteConfirmSchema, { confirm: " DELETE " }, null],
    [deleteConfirmSchema, { confirm: "delete" }, "validation.typeDelete"],
    [deleteConfirmSchema, { confirm: "" }, "validation.typeDelete"],
  ] as const)("%# validates to %p", (schema, value, want) => {
    expect(firstError(schema, value)).toBe(want);
  });

  it("every message key exists in the English strings", () => {
    const keys = ["required", "tooLong", "email", "code", "typeDelete"] as const;
    for (const k of keys) expect(en.validation[k]).toBeTruthy();
  });

  it("matches the backend's display_name max_length", () => {
    expect(DISPLAY_NAME_MAX).toBe(80);
  });
});

function NameHarness({ onValid }: { onValid: (v: NameForm) => void }) {
  const form = useForm<NameForm>({ resolver: zodResolver(nameSchema), defaultValues: { displayName: "Sam" }, mode: "onChange" });
  return (
    <>
      <FormField control={form.control} name="displayName" label="Name" testID="name" />
      <FormField control={form.control} name="displayName" label="Mirror" testID="mirror" serverError="Server said no" />
      {/* a plain submit trigger for the test */}
      <FormField control={form.control} name="displayName" label="Submit" testID="submit" onSubmitEditing={() => void form.handleSubmit(onValid)()} />
    </>
  );
}

describe("FormField", () => {
  it("starts from the default value and shows no error before the user types", async () => {
    await render(<NameHarness onValid={jest.fn()} />);
    expect(screen.getByTestId("name").props.value).toBe("Sam");
    expect(screen.queryByText(en.validation.required)).toBeNull();
  });

  it("shows the translated error once the field is invalid and touched", async () => {
    await render(<NameHarness onValid={jest.fn()} />);
    await fireEvent.changeText(screen.getByTestId("name"), "");
    await fireEvent(screen.getByTestId("name"), "blur");
    expect(await screen.findAllByText(en.validation.required, { exact: false })).not.toHaveLength(0);
  });

  it("interpolates limits into the message", async () => {
    await render(<NameHarness onValid={jest.fn()} />);
    await fireEvent.changeText(screen.getByTestId("name"), "x".repeat(DISPLAY_NAME_MAX + 5));
    await fireEvent(screen.getByTestId("name"), "blur");
    const msg = en.validation.tooLong.replace("{{max}}", String(DISPLAY_NAME_MAX));
    expect(await screen.findAllByText(msg, { exact: false })).not.toHaveLength(0);
  });

  it("shows a server error when the value itself is valid", async () => {
    await render(<NameHarness onValid={jest.fn()} />);
    expect(screen.getByText("Server said no", { exact: false })).toBeTruthy();
  });

  it("submits the parsed (trimmed) value only when valid", async () => {
    const onValid = jest.fn();
    await render(<NameHarness onValid={onValid} />);
    await fireEvent.changeText(screen.getByTestId("name"), "  Riley  ");
    await fireEvent(screen.getByTestId("submit"), "submitEditing");
    await waitFor(() => expect(onValid).toHaveBeenCalledWith({ displayName: "Riley" }, undefined));
  });
});
