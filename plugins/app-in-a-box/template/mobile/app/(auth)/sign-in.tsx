import { useState } from "react";
import { View } from "react-native";
import Animated from "react-native-reanimated";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";

import { Badge, Body, Button, Display, ErrorText, FormField, Screen } from "../../components/ui";
import { analytics, startTimer } from "../../lib/analytics";
import { APP } from "../../lib/app";
import { sendEmailCode, verifyEmailCode, type AuthErrorCode } from "../../lib/auth";
import { DEMO } from "../../lib/demo";
import { codeSchema, emailSchema, type CodeForm, type EmailForm } from "../../lib/forms";
import { useT } from "../../lib/i18n";
import { entrance, haptic, useReducedMotion } from "../../lib/motion";
import { makeStyles } from "../../lib/theme";

export default function SignIn() {
  const s = useStyles();
  const t = useT();
  const reduced = useReducedMotion();
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AuthErrorCode | null>(null);
  const emailForm = useForm<EmailForm>({ resolver: zodResolver(emailSchema), defaultValues: { email: "" }, mode: "onChange" });
  const codeForm = useForm<CodeForm>({ resolver: zodResolver(codeSchema), defaultValues: { code: "" }, mode: "onChange" });
  const email = useWatch({ control: emailForm.control, name: "email" }) ?? "";

  const send = emailForm.handleSubmit(async (values) => {
    setBusy(true);
    setError(null);
    analytics.signInRequested("email_otp");
    const res = await sendEmailCode(values.email);
    setBusy(false);
    if (res.error) {
      haptic.error();
      setError(res.error);
    } else setSent(true);
  });

  const verify = codeForm.handleSubmit(async (values) => {
    const elapsed = startTimer();
    setBusy(true);
    setError(null);
    const res = await verifyEmailCode(email.trim(), values.code);
    setBusy(false);
    analytics.signInCompleted({
      method: "email_otp",
      success: !res.error,
      error_code: res.error ? `verify_${res.error}` : null,
      duration_ms: elapsed(),
    });
    if (res.error) {
      haptic.error();
      setError(res.error);
    }
    // On success the auth guard in app/_layout.tsx moves you into the app.
  });

  /** The code was sent to the locked address; going back unlocks it and drops the code. */
  const changeEmail = () => {
    setSent(false);
    setError(null);
    codeForm.reset();
  };

  return (
    <Screen testID="signin-screen" edges={["top", "left", "right", "bottom"]}>
      <Animated.View entering={entrance(0, reduced)} style={s.hero}>
        {DEMO ? <Badge label={t("auth.demoBadge")} tone="accent" testID="signin-demo-badge" /> : null}
        <Display>{APP.name}</Display>
        <Body dim>{APP.oneLiner}</Body>
      </Animated.View>
      <Animated.View entering={entrance(1, reduced)} style={s.form}>
        <FormField
          control={emailForm.control}
          name="email"
          label={t("auth.email")}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="emailAddress"
          returnKeyType="send"
          onSubmitEditing={() => void send()}
          // Locked once a code is sent: the code belongs to THIS address.
          editable={!sent}
          testID="signin-email-input"
        />
        {sent ? (
          <View style={s.form}>
            <FormField
              control={codeForm.control}
              name="code"
              label={t("auth.code")}
              keyboardType="number-pad"
              autoComplete="one-time-code"
              textContentType="oneTimeCode"
              maxLength={6}
              hint={t("auth.codeSent", { email: email.trim() })}
              testID="signin-code-input"
            />
            <Button
              label={t("auth.signIn")}
              onPress={() => void verify()}
              loading={busy}
              disabled={!codeForm.formState.isValid}
              testID="signin-verify-button"
            />
            <Button label={t("auth.resend")} variant="ghost" onPress={() => void send()} disabled={busy} testID="signin-resend-button" />
            <Button
              label={t("auth.changeEmail")}
              accessibilityLabel={t("auth.changeEmailLabel")}
              variant="ghost"
              onPress={changeEmail}
              disabled={busy}
              testID="signin-change-email-button"
            />
          </View>
        ) : (
          <Button
            label={t("auth.sendCode")}
            onPress={() => void send()}
            loading={busy}
            disabled={!emailForm.formState.isValid}
            testID="signin-send-button"
          />
        )}
        {error ? <ErrorText>{t(`auth.errors.${error}`)}</ErrorText> : null}
      </Animated.View>
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  hero: { gap: t.space.sm, marginTop: t.space.xxl, marginBottom: t.space.xl },
  form: { gap: t.space.md },
}));
