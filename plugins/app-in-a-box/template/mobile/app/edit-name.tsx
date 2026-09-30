/**
 * Example sheet (native formSheet, registered in app/_layout.tsx): edit a field
 * and save it. The pattern to copy for any "edit one thing" flow:
 *
 * 1. Load -> skeleton -> mount the form with defaultValues from the loaded data,
 *    so the input starts from real data (never a blank that Save writes back).
 * 2. react-hook-form + a zod schema from lib/forms.ts, bound with <FormField>:
 *    validation messages are i18n keys, shown once the field is touched.
 * 3. Save through an OPTIMISTIC mutation (lib/query.ts useUpdateMe): the new
 *    value shows everywhere at once, rolls back if the server refuses, and fires
 *    success AND failure analytics. Offline, it queues and syncs on reconnect.
 * 4. Online: wait for the server, then close the sheet, THEN toast (a toast
 *    would render under the native sheet on iOS). Offline: close and say it'll sync.
 */
import { useEffect } from "react";
import { View } from "react-native";
import { zodResolver } from "@hookform/resolvers/zod";
import { onlineManager } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";

import { Body, Button, ErrorNotice, FormField, Screen, SheetHeader, Skeleton, closeSheet, useToast } from "../components/ui";
import { analytics } from "../lib/analytics";
import { errorMessage, errorReference, type Profile } from "../lib/api";
import { DISPLAY_NAME_MAX, nameSchema, type NameForm } from "../lib/forms";
import { useT } from "../lib/i18n";
import { useMe, useUpdateMe } from "../lib/query";
import { makeStyles } from "../lib/theme";
import { useLoaded } from "../lib/use-load";

export default function EditNameSheet() {
  const t = useT();
  const me = useLoaded(useMe());
  useEffect(() => {
    analytics.sheetOpened("edit_name");
  }, []);

  return (
    <Screen sheet edges={["left", "right", "bottom"]} testID="edit-name-sheet">
      <SheetHeader title={t("editName.title")} testID="edit-name-close-button" />
      {me.data ? (
        <NameEditor profile={me.data} />
      ) : me.error ? (
        <ErrorNotice message={me.error} reference={me.errorRef} onRetry={me.reload} testID="edit-name-error" />
      ) : (
        <Skeleton height={48} />
      )}
    </Screen>
  );
}

function NameEditor({ profile }: { profile: Profile }) {
  const s = useStyles();
  const t = useT();
  const toast = useToast();
  const update = useUpdateMe();
  const form = useForm<NameForm>({
    resolver: zodResolver(nameSchema),
    defaultValues: { displayName: profile.displayName },
    mode: "onChange",
  });
  const typed = useWatch({ control: form.control, name: "displayName" }) ?? "";
  const unchanged = typed.trim() === profile.displayName;
  const failure = update.error;

  const save = form.handleSubmit(async ({ displayName }) => {
    if (!onlineManager.isOnline()) {
      update.mutate({ displayName }); // queued; replays on reconnect (even after a restart)
      closeSheet();
      toast.info(t("editName.savedOffline"));
      return;
    }
    try {
      await update.mutateAsync({ displayName });
      closeSheet();
      toast.success(t("editName.saved"));
    } catch {
      // Rolled back in useUpdateMe's onError; the error shows under the field.
    }
  });

  return (
    <View style={s.form}>
      <Body dim>{t("editName.intro")}</Body>
      <FormField
        control={form.control}
        name="displayName"
        label={t("editName.label")}
        autoFocus
        autoCapitalize="words"
        returnKeyType="done"
        onSubmitEditing={() => !unchanged && void save()}
        maxLength={DISPLAY_NAME_MAX + 20}
        serverError={failure ? errorMessage(failure) : null}
        testID="edit-name-input"
      />
      {failure && errorReference(failure) ? (
        <ErrorNotice message={t("editName.failed")} reference={errorReference(failure)} testID="edit-name-save-error" />
      ) : null}
      <Button
        label={t("common.save")}
        accessibilityLabel={t("editName.saveLabel")}
        onPress={() => void save()}
        loading={update.isPending && onlineManager.isOnline()}
        disabled={unchanged || !form.formState.isValid}
        testID="edit-name-save-button"
      />
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  form: { gap: t.space.md },
}));
