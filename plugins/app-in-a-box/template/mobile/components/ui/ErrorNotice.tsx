/**
 * ErrorNotice: an honest error with a way forward.
 *
 *   <ErrorNotice message={me.error} reference={me.errorRef} onRetry={me.reload} testID="home-error" />
 *
 * - The message is announced (role "alert") and carries a glyph (never colour alone).
 * - `reference` is the short support code from `errorReference(e)` (lib/api.ts): the
 *   server's error_id, or the X-Request-ID it logged the call under. Tapping it
 *   copies it, so a user can paste it into a support email and you can grep the
 *   Railway logs / Sentry for it.
 * - `onRetry` shows a secondary "Try again" button.
 */
import * as Clipboard from "expo-clipboard";
import { View } from "react-native";

import { analytics } from "../../lib/analytics";
import { useT } from "../../lib/i18n";
import { makeStyles } from "../../lib/theme";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { PressableScale } from "./PressableScale";
import { ErrorText, Text } from "./Text";
import { useToast } from "./Toast";

export interface ErrorNoticeProps {
  message: string;
  reference?: string | null;
  onRetry?: () => void;
  testID?: string;
}

export function ErrorNotice({ message, reference, onRetry, testID }: ErrorNoticeProps) {
  const s = useStyles();
  const t = useT();
  const toast = useToast();

  async function copy() {
    if (!reference) return;
    analytics.errorReferenceCopied();
    try {
      await Clipboard.setStringAsync(reference);
    } catch {
      // clipboard unavailable (some web contexts): the reference is still on screen
    }
    toast.info(t("errors.referenceCopied"));
  }

  return (
    <View style={s.wrap} testID={testID}>
      <ErrorText testID={testID ? `${testID}-message` : undefined}>{message}</ErrorText>
      {reference ? (
        <PressableScale
          onPress={copy}
          haptic="selection"
          accessibilityRole="button"
          accessibilityLabel={t("errors.copyReference", { ref: reference })}
          testID={testID ? `${testID}-reference` : undefined}
          style={s.ref}
        >
          <Icon sf="doc.on.doc" md="content_copy" size={14} color="inkFaint" />
          <Text variant="mono" tone="faint">
            {t("errors.reference", { ref: reference })}
          </Text>
        </PressableScale>
      ) : null}
      {onRetry ? (
        <Button
          label={t("common.tryAgain")}
          variant="secondary"
          onPress={onRetry}
          testID={testID ? `${testID}-retry-button` : undefined}
        />
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: t.space.sm },
  ref: {
    minHeight: t.minTapTarget,
    flexDirection: "row",
    alignItems: "center",
    gap: t.space.xs,
    alignSelf: "flex-start",
  },
}));
