/**
 * AgeGate: a neutral age screen (the `minors` guardrail pack). Mounted on the sign-in
 * screen when the pack is on, before anything is collected.
 *
 * Neutral on purpose, per the FTC's COPPA guidance: it asks for a birth month and
 * year with no hint of the "right" answer (no "you must be 13"), and the outcome is
 * kept (lib/age.ts) so a child can't go back and try an older year. Only the outcome
 * is stored, never the date. An under-age answer shows a calm "ask a parent" message:
 * how the app then gets a parent's verifiable consent is the owner's call
 * (docs/privacy/GUARDRAILS.md lists the options).
 */
import { useState } from "react";
import { View } from "react-native";

import { recordAge, validBirth, type AgeStatus } from "../../lib/age";
import { APP } from "../../lib/app";
import { useT } from "../../lib/i18n";
import { makeStyles } from "../../lib/theme";
import { Button } from "./Button";
import { Field } from "./Field";
import { Body, ErrorText, Title } from "./Text";

export function AgeGate({ status, onDone }: { status: AgeStatus; onDone: (status: AgeStatus) => void }) {
  const t = useT();
  const s = useStyles();
  const [month, setMonth] = useState("");
  const [year, setYear] = useState("");
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);
  const valid = validBirth(Number(year), Number(month));

  if (status === "underAge") {
    return (
      <View style={s.wrap} testID="age-gate-under-age">
        <Title>{t("age.underAgeTitle")}</Title>
        <Body dim>{t("age.underAgeBody", { app: APP.name })}</Body>
      </View>
    );
  }

  const submit = async () => {
    setTouched(true);
    if (!valid) return;
    setBusy(true);
    onDone(await recordAge(Number(year), Number(month)));
  };

  return (
    <View style={s.wrap} testID="age-gate">
      <Title>{t("age.title")}</Title>
      <Body dim>{t("age.body")}</Body>
      <View style={s.row}>
        <View style={s.cell}>
          <Field
            label={t("age.month")}
            value={month}
            onChangeText={(v) => setMonth(v.replace(/\D/g, ""))}
            keyboardType="number-pad"
            maxLength={2}
            testID="age-gate-month-input"
          />
        </View>
        <View style={s.cell}>
          <Field
            label={t("age.year")}
            value={year}
            onChangeText={(v) => setYear(v.replace(/\D/g, ""))}
            keyboardType="number-pad"
            maxLength={4}
            testID="age-gate-year-input"
          />
        </View>
      </View>
      {touched && !valid ? <ErrorText testID="age-gate-error">{t("age.invalid")}</ErrorText> : null}
      <Button
        label={t("age.continue")}
        accessibilityLabel={t("age.continueLabel")}
        onPress={() => void submit()}
        loading={busy}
        testID="age-gate-continue-button"
      />
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: t.space.md, marginTop: t.space.xxl },
  row: { flexDirection: "row", gap: t.space.md },
  cell: { flex: 1 },
}));
