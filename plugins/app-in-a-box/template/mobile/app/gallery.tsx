/**
 * Component gallery (dev builds only: the route is guarded by __DEV__ in
 * app/_layout.tsx). Every component, in the current mode, plus a side-by-side
 * light/dark strip. Use it to review a re-skin, and as the reference when
 * building a screen. Add new components here when you add them to components/ui.
 */
import { useEffect, useState, type ReactNode } from "react";
import { View } from "react-native";

import {
  AnimatedNumber,
  Avatar,
  Badge,
  Body,
  Button,
  Card,
  Celebration,
  Chip,
  EmptyState,
  ErrorNotice,
  ErrorText,
  Field,
  Heading,
  IconButton,
  ListRow,
  Media,
  Meta,
  ProgressBar,
  Screen,
  Section,
  SegmentedControl,
  SheetHeader,
  Skeleton,
  SkeletonCard,
  StatCard,
  Text,
  closeSheet,
  useToast,
} from "../components/ui";
import { analytics } from "../lib/analytics";
import { useReducedMotion } from "../lib/motion";
import { ThemeScope, canSwitchScheme, makeStyles, useThemePreference, type ColorScheme, type ThemePreference } from "../lib/theme";

const MODES = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const satisfies readonly { value: ThemePreference; label: string }[];

export default function Gallery() {
  const s = useStyles();
  const toast = useToast();
  const reduced = useReducedMotion();
  const { preference, setPreference } = useThemePreference();
  const [chip, setChip] = useState("socks");
  const [text, setText] = useState("");
  const [count, setCount] = useState(12);
  const [wins, setWins] = useState(0);

  useEffect(() => {
    analytics.screenViewed("gallery");
  }, []);

  return (
    <View style={s.fill}>
      <Screen edges={["left", "right", "bottom"]} testID="gallery-screen">
        <SheetHeader title="Component gallery" onClose={closeSheet} testID="gallery-close-button" />
        <Body dim>{reduced ? "Reduce motion is ON: animations are static or fades." : "Turn on Reduce Motion to see every fallback."}</Body>
        {canSwitchScheme ? (
          <SegmentedControl options={MODES} value={preference} onChange={setPreference} accessibilityLabel="Colour mode" testID="gallery-mode" />
        ) : null}

        <Section title="Type roles">
          <Card>
            <Text variant="display">Display</Text>
            <Text variant="title">Title</Text>
            <Heading>Heading</Heading>
            <Body>Body copy reads comfortably at every Dynamic Type size.</Body>
            <Body dim>Secondary copy for supporting detail.</Body>
            <Meta>Meta label</Meta>
            <Text variant="mono">mono 1,234.56</Text>
          </Card>
        </Section>

        <Section title="Stats and media">
          <View style={s.row}>
            <StatCard label="This week" value={count} hint="entries" icon={{ sf: "checkmark", md: "check" }} />
            <StatCard label="Streak" value="4 days" hint="best yet" icon={{ sf: "flame", md: "local_fire_department" }} />
          </View>
          <Media label="Cover photo" ratio="16:9" />
        </Section>

        <Section title="Buttons">
          <Button label="Primary" onPress={() => toast.success("Primary pressed")} />
          <Button label="With icon" icon={{ sf: "plus", md: "add" }} onPress={() => undefined} />
          <Button label="Secondary" variant="secondary" onPress={() => undefined} />
          <Button label="Ghost" variant="ghost" onPress={() => undefined} />
          <Button label="Danger" variant="danger" onPress={() => undefined} />
          <Button label="Loading" loading onPress={() => undefined} />
          <Button label="Disabled" disabled onPress={() => undefined} />
          <View style={s.row}>
            <IconButton sf="heart" md="favorite" accessibilityLabel="Like" onPress={() => undefined} />
            <IconButton sf="square.and.arrow.up" md="share" accessibilityLabel="Share" onPress={() => undefined} tone="filled" />
          </View>
        </Section>

        <Section title="Inputs and selection">
          <Field label="Field" value={text} onChangeText={setText} placeholder="Type something" hint="A hint under the field" />
          <Field label="Field with error" value="oops" onChangeText={() => undefined} error="That doesn't look right" />
          <View style={s.wrap}>
            {["socks", "shirts", "hats"].map((c) => (
              <Chip key={c} label={c} selected={chip === c} onPress={() => setChip(c)} />
            ))}
          </View>
        </Section>

        <Section title="Rows, badges, avatars">
          <Card>
            <ListRow title="Navigates" subtitle="With a subtitle" icon={{ sf: "bell", md: "notifications" }} onPress={() => undefined} />
            <ListRow title="With value" value="On" icon={{ sf: "moon", md: "dark_mode" }} onPress={() => undefined} />
            <ListRow title="Static row" leading={<Avatar name="Sam Rivera" size={32} />} />
          </Card>
          <View style={s.wrap}>
            <Badge label="Neutral" />
            <Badge label="New" tone="accent" />
            <Badge label="Done" tone="success" />
            <Badge label="Pending" tone="warning" />
            <Badge label="Failed" tone="danger" />
          </View>
        </Section>

        <Section title="Numbers and progress">
          <Card>
            <AnimatedNumber value={count} />
            <ProgressBar value={(count % 20) / 20} label="Weekly goal" />
            <Button label="Add 7" variant="secondary" onPress={() => setCount((c) => c + 7)} />
          </Card>
        </Section>

        <Section title="Loading, empty, error">
          <SkeletonCard />
          <Skeleton width="40%" />
          <Card>
            <EmptyState icon={{ sf: "tray", md: "inbox" }} title="Nothing here yet" body="Empty states say what's missing and the one next step." />
          </Card>
          <ErrorText>Couldn&apos;t reach the server. Try again.</ErrorText>
          <ErrorNotice message="Something went wrong (500). Try again." reference="3f9a1c2e" onRetry={() => toast.info("Retrying")} />
        </Section>

        <Section title="Feedback">
          <Button label="Success toast" variant="secondary" onPress={() => toast.success("Saved")} />
          <Button label="Error toast" variant="secondary" onPress={() => toast.error("Couldn't save. Try again.")} />
          <Button label="Celebrate" onPress={() => setWins((w) => w + 1)} />
        </Section>

        <Section title="Both modes">
          <View style={s.row}>
            {(["light", "dark"] as ColorScheme[]).map((mode) => (
              <ThemeScope key={mode} scheme={mode}>
                <ModeSample label={mode} />
              </ThemeScope>
            ))}
          </View>
        </Section>
      </Screen>
      <Celebration trigger={wins} message="Nice work!" />
    </View>
  );
}

function ModeSample({ label }: { label: string }): ReactNode {
  const s = useStyles();
  return (
    <View style={s.sample}>
      <Meta>{label}</Meta>
      <Heading>Aa</Heading>
      <Body dim>Ink ramp</Body>
      <Badge label="Status" tone="success" />
      <Button label="Action" onPress={() => undefined} />
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  fill: { flex: 1 },
  row: { flexDirection: "row", gap: t.space.md },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: t.space.sm },
  sample: { flex: 1, gap: t.space.sm, padding: t.space.md, borderRadius: t.radius.lg, backgroundColor: t.color.bg, borderWidth: 1, borderColor: t.color.border },
}));
