/**
 * Home. The scaffold replaces the empty state with the core-loop screen from
 * docs/product/BRIEF.md. Keep the pattern: analytics on mount, data through a
 * query hook in lib/query.ts (cached, works offline) over a lib/api.ts adapter,
 * a skeleton while loading, an honest empty/error state (never fake data), pull
 * to refresh, and every string through t().
 */
import { useEffect } from "react";
import { router } from "expo-router";
import { View } from "react-native";

import { Avatar, Button, Card, EmptyState, ErrorNotice, Meta, Screen, SkeletonCard, Title } from "../../components/ui";
import { analytics } from "../../lib/analytics";
import { APP } from "../../lib/app";
import { DEMO } from "../../lib/demo";
import { useT } from "../../lib/i18n";
import { useMe } from "../../lib/query";
import { makeStyles } from "../../lib/theme";
import { useLoaded } from "../../lib/use-load";

export default function Home() {
  const s = useStyles();
  const t = useT();
  const me = useLoaded(useMe());

  useEffect(() => {
    analytics.screenViewed("home");
  }, []);

  const name = me.data?.displayName ?? "";
  return (
    <Screen testID="home-screen" refreshing={me.refreshing} onRefresh={me.refresh}>
      <View style={s.header}>
        <View style={s.flex}>
          <Meta>{DEMO ? t("home.demoSuffix", { name: APP.name }) : APP.name}</Meta>
          <Title>{name ? t("home.greeting", { name }) : t("home.welcome")}</Title>
        </View>
        {me.data ? <Avatar name={name || APP.name} testID="home-avatar" /> : null}
      </View>

      {me.loading ? (
        <SkeletonCard announce={t("home.loadingProfile")} testID="home-skeleton" />
      ) : me.error && !me.data ? (
        <Card>
          <ErrorNotice message={me.error} reference={me.errorRef} onRetry={me.reload} testID="home-error" />
        </Card>
      ) : (
        <Card index={0}>
          <EmptyState
            icon={{ sf: "sparkles", md: "auto_awesome" }}
            title={t("home.emptyTitle")}
            body={t("home.emptyBody")}
            action={
              name ? null : (
                <Button
                  label={t("home.addName")}
                  icon={{ sf: "person.crop.circle", md: "account_circle" }}
                  onPress={() => router.push("/edit-name")}
                  testID="home-add-name-button"
                />
              )
            }
            testID="home-empty"
          />
        </Card>
      )}
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  header: { flexDirection: "row", alignItems: "center", gap: t.space.md, marginBottom: t.space.sm },
  flex: { flex: 1, gap: t.space.xs },
}));
