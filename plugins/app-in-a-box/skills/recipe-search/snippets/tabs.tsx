// recipe-search: register the tab in BOTH layouts (same route, same label), between
// Home and Settings. Two to four tabs in all; if the app already has four, put search
// behind a header button on Home instead (router.push("/search")).

// mobile/app/(app)/_layout.tsx, inside <NativeTabs>:
      <NativeTabs.Trigger name="search">
        <NativeTabs.Trigger.Icon sf="magnifyingglass" md="search" />
        <NativeTabs.Trigger.Label>{tr("tabs.search")}</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>

// mobile/app/(app)/_layout.web.tsx, inside <TabList>:
        <TabTrigger name="search" href="/search" asChild>
          <TabButton icon="search" label={tr("tabs.search")} testID="tab-search" />
        </TabTrigger>
