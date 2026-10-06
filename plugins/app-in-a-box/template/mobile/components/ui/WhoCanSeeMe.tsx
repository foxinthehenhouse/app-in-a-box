/**
 * WhoCanSeeMe: an always-visible answer to "who can see where I am?" (the `location`
 * guardrail pack). Any screen that shares or shows a user's location renders it, and
 * scripts/check_guardrails.py fails CI when the app reads a position but no screen
 * under app/ does. A location feature people can't see the reach of is how a family
 * tracker becomes a stalking tool.
 *
 * `audience` is already-translated text naming the people, not a count alone: "Only
 * you", "Sam and Alex". `onManage` opens wherever sharing is changed; leave it out only
 * when nobody else can ever see the location. Icon + text, never colour alone.
 *
 * Not in the components/ui barrel on purpose: an app without the pack never bundles it.
 * Import it as `components/ui/WhoCanSeeMe`.
 */
import { StyleSheet, View } from "react-native";

import { useT } from "../../lib/i18n";
import { makeStyles } from "../../lib/theme";
import { Button } from "./Button";
import { Icon } from "./Icon";
import { Text } from "./Text";

export function WhoCanSeeMe({ audience, onManage, testID = "who-can-see-me" }: { audience: string; onManage?: () => void; testID?: string }) {
  const t = useT();
  const s = useStyles();
  return (
    <View style={s.box} testID={testID}>
      <View style={s.row} accessible accessibilityLabel={t("location.summary", { audience })}>
        <Icon sf="location.circle" md="location_on" size={20} color="accent" />
        <View style={s.text}>
          <Text variant="meta">{t("location.visibleTo")}</Text>
          <Text variant="body" testID={`${testID}-audience`}>
            {audience}
          </Text>
        </View>
      </View>
      {onManage ? (
        <Button
          label={t("location.manage")}
          accessibilityLabel={t("location.manageLabel")}
          variant="secondary"
          onPress={onManage}
          testID={`${testID}-manage-button`}
        />
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  box: {
    gap: t.space.sm,
    padding: t.space.md,
    borderRadius: t.radius.md,
    backgroundColor: t.color.surfaceRaised,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: t.color.border,
  },
  row: { flexDirection: "row", alignItems: "center", gap: t.space.sm },
  text: { flex: 1, gap: t.space.xs },
}));
