/**
 * Search (recipe-search). The pattern: a search field whose text is debounced
 * (lib/search.ts) before it reaches the server, and one honest state at a time:
 *
 *   idle         nothing typed yet (or too short): say what search can do
 *   loading      a skeleton while the first page is on its way (or typing is settling)
 *   error        <ErrorNotice> with a retry and the support reference
 *   no results   name the query, suggest what to try; never a blank screen
 *   results      rows, then "Show more" while the server has another page
 *
 * The server ranks and scopes the results; this screen only renders them. Results
 * are announced to screen readers when a new search lands. Wire `onPress` on a row
 * to your item's detail route.
 */
import { useCallback, useEffect, useState } from "react";
import { useFocusEffect } from "expo-router";
import { AccessibilityInfo } from "react-native";

import { Button, Card, EmptyState, ErrorNotice, Field, ListRow, Screen, SkeletonCard, Title } from "../../components/ui";
import { errorMessage, errorReference } from "../../lib/api";
import { analytics } from "../../lib/analytics";
import { useT } from "../../lib/i18n";
import { MIN_QUERY_CHARS, useSearch } from "../../lib/search";

export default function Search() {
  const t = useT();
  const [text, setText] = useState("");
  const search = useSearch(text);
  const { query, items, settling } = search;

  // On focus, not on mount: native tabs mount every tab at launch.
  useFocusEffect(
    useCallback(() => {
      analytics.screenViewed("search");
    }, []),
  );

  const landed = search.isSuccess && !search.isFetching && !settling;
  useEffect(() => {
    if (landed && query) AccessibilityInfo.announceForAccessibility(t("search.found", { count: items.length }));
  }, [landed, query, items.length, t]);

  const typing = text.trim().length > 0 && text.trim().length < MIN_QUERY_CHARS;
  const idle = query === "" && !settling;
  const loading = !idle && (settling || search.isPending);

  return (
    <Screen testID="search-screen">
      <Title>{t("search.title")}</Title>
      <Field
        label={t("search.fieldLabel")}
        value={text}
        onChangeText={setText}
        placeholder={t("search.placeholder")}
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="search"
        clearButtonMode="while-editing"
        inputMode="search"
        testID="search-input"
      />

      {idle || typing ? (
        <Card>
          <EmptyState
            icon={{ sf: "magnifyingglass", md: "search" }}
            title={t("search.idleTitle")}
            body={t("search.idleBody")}
            testID="search-idle"
          />
        </Card>
      ) : loading ? (
        <SkeletonCard announce={t("search.searching")} testID="search-skeleton" />
      ) : search.isError && items.length === 0 ? (
        <Card>
          <ErrorNotice
            message={errorMessage(search.error)}
            reference={errorReference(search.error)}
            onRetry={() => void search.refetch()}
            testID="search-error"
          />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={{ sf: "text.magnifyingglass", md: "search_off" }}
            title={t("search.noResultsTitle", { query })}
            body={t("search.noResultsBody")}
            testID="search-empty"
          />
        </Card>
      ) : (
        <>
          <Card testID="search-results">
            {items.map((hit) => (
              <ListRow key={hit.id} title={hit.title} subtitle={hit.snippet || undefined} testID={`search-result-${hit.id}`} />
            ))}
          </Card>
          {search.isError ? (
            <ErrorNotice
              message={errorMessage(search.error)}
              reference={errorReference(search.error)}
              onRetry={() => void search.fetchNextPage()}
              testID="search-more-error"
            />
          ) : search.hasNextPage ? (
            <Button
              label={t("search.more")}
              accessibilityLabel={t("search.moreLabel")}
              variant="secondary"
              loading={search.isFetchingNextPage}
              onPress={() => void search.fetchNextPage()}
              testID="search-more-button"
            />
          ) : null}
        </>
      )}
    </Screen>
  );
}
