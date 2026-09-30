/**
 * Delete account (App Store 5.1.1(v), Google Play data deletion policy): findable
 * in the app (Settings → Account), explicit, and final.
 *
 * Flow: explain what goes → the user types DELETE (zod-validated, the same literal
 * the API requires) → DELETE /api/v1/me with {"confirm": "DELETE"} → end the
 * session, which closes the sheet via the auth guard (skip the push unregister: the cascade already
 * removed the tokens) → toast on the sign-in screen. Success AND failure analytics.
 *
 * Once the DELETE succeeded the account is gone, whatever happens next: a failing
 * local sign-out is retried step by step (forceLocalSignOut) and is NEVER reported
 * as "Couldn't delete your account" or as a failure event.
 *
 * Play also needs a WEB deletion URL (a form or a support email is accepted):
 * see $KIT/docs/PRODUCTION.md.
 */
import { useEffect, useState } from "react";
import { View } from "react-native";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Body, Button, ErrorNotice, FormField, Screen, SheetHeader, closeSheet, useToast } from "../components/ui";
import { analytics, startTimer } from "../lib/analytics";
import { ApiError, deleteAccount, errorMessage, errorReference } from "../lib/api";
import { deleteConfirmSchema, type DeleteConfirmForm } from "../lib/forms";
import { useT } from "../lib/i18n";
import { haptic } from "../lib/motion";
import { endSession, forceLocalSignOut } from "../lib/session";
import { makeStyles } from "../lib/theme";

export default function DeleteAccountSheet() {
  const s = useStyles();
  const t = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const form = useForm<DeleteConfirmForm>({
    resolver: zodResolver(deleteConfirmSchema),
    defaultValues: { confirm: "" },
    mode: "onChange",
  });

  useEffect(() => {
    analytics.sheetOpened("delete_account");
  }, []);

  const submit = form.handleSubmit(async () => {
    const elapsed = startTimer();
    setBusy(true);
    setFailure(null);
    try {
      await deleteAccount();
    } catch (e) {
      analytics.accountDeleted({
        success: false,
        error_code: e instanceof ApiError ? `http_${e.status}` : "delete_failed",
        duration_ms: elapsed(),
      });
      haptic.error();
      setFailure(e);
      setBusy(false);
      return;
    }
    analytics.accountDeleted({ success: true, error_code: null, duration_ms: elapsed() });
    // No closeSheet() here: signing out flips the Stack.Protected guard, which
    // removes this sheet with the rest of the signed-in stack. Dismissing first
    // races the guard (a POP that no navigator can handle).
    try {
      await endSession({ unregisterPush: false });
    } catch {
      await forceLocalSignOut();
    }
    toast.success(t("deleteAccount.deleted"));
  });

  return (
    <Screen sheet edges={["left", "right", "bottom"]} testID="delete-account-sheet">
      <SheetHeader title={t("deleteAccount.title")} testID="delete-account-close-button" />
      <View style={s.body}>
        <Body>{t("deleteAccount.warning")}</Body>
        <Body dim>{t("deleteAccount.whatGoes")}</Body>
        <Body dim>{t("deleteAccount.exportFirst")}</Body>
        <FormField
          control={form.control}
          name="confirm"
          label={t("deleteAccount.confirmLabel")}
          hint={t("deleteAccount.confirmHint")}
          autoCapitalize="characters"
          autoCorrect={false}
          autoComplete="off"
          testID="delete-account-confirm-input"
        />
        {failure ? (
          <ErrorNotice
            message={`${t("deleteAccount.failed")} ${errorMessage(failure)}`}
            reference={errorReference(failure)}
            testID="delete-account-error"
          />
        ) : null}
        <Button
          label={t("deleteAccount.submit")}
          accessibilityLabel={t("deleteAccount.submitLabel")}
          variant="danger"
          onPress={() => void submit()}
          loading={busy}
          disabled={!form.formState.isValid}
          testID="delete-account-submit-button"
        />
        <Button label={t("common.cancel")} variant="ghost" onPress={closeSheet} disabled={busy} testID="delete-account-cancel-button" />
      </View>
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  body: { gap: t.space.md },
}));
