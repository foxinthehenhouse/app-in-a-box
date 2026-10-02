/**
 * Unmatched route (a stale link, a typo'd push payload that slipped past
 * lib/links.ts, a removed screen). Themed, translated, and one tap from Home;
 * logged as a view so dead links show up in the product data.
 */
import { useCallback } from "react";
import { router, useFocusEffect } from "expo-router";

import { Button, EmptyState, Screen } from "../components/ui";
import { analytics } from "../lib/analytics";
import { useT } from "../lib/i18n";

export default function NotFound() {
  const t = useT();
  useFocusEffect(
    useCallback(() => {
      analytics.screenViewed("not_found");
    }, []),
  );
  return (
    <Screen scroll={false} edges={["top", "left", "right", "bottom"]} testID="not-found-screen">
      <EmptyState
        icon={{ sf: "questionmark.circle", md: "help" }}
        title={t("notFound.title")}
        body={t("notFound.body")}
        action={<Button label={t("notFound.home")} onPress={() => router.replace("/")} testID="not-found-home-button" />}
      />
    </Screen>
  );
}
