/**
 * StatCard: one number that matters, with its label and a hint ("12 · entries this
 * week"). The prototype's `stat` block. A numeric value counts up on mount
 * (AnimatedNumber, static under reduce motion); text values ("4 days") render as-is.
 * Read as one element: "This week, 12, entries".
 */
import { View } from "react-native";

import { makeStyles } from "../../lib/theme";
import { AnimatedNumber } from "./AnimatedNumber";
import { Icon, type IconProps } from "./Icon";
import { Card } from "./Screen";
import { Body, Meta, Text } from "./Text";

export interface StatCardProps {
  label: string;
  value: number | string;
  hint?: string;
  icon?: Pick<IconProps, "sf" | "md">;
  /** Stagger position for the entrance animation. */
  index?: number;
  testID?: string;
}

export function StatCard({ label, value, hint, icon, index, testID }: StatCardProps) {
  const s = useStyles();
  const spoken = [label, String(value), hint].filter(Boolean).join(", ");
  return (
    <Card index={index} style={s.card} testID={testID}>
      <View accessible accessibilityLabel={spoken} style={s.stack}>
        <View style={s.eyebrow}>
          {icon ? <Icon sf={icon.sf} md={icon.md} size={16} color="accent" /> : null}
          <Meta>{label}</Meta>
        </View>
        {typeof value === "number" ? (
          <AnimatedNumber value={value} variant="title" />
        ) : (
          <Text variant="title">{value}</Text>
        )}
        {hint ? <Body dim>{hint}</Body> : null}
      </View>
    </Card>
  );
}

const useStyles = makeStyles((t) => ({
  card: { flex: 1 },
  stack: { gap: t.space.xs },
  eyebrow: { flexDirection: "row", alignItems: "center", gap: t.space.xs },
}));
