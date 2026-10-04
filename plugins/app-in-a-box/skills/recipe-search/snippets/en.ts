// recipe-search: add `search` inside `tabs` and the `search` block at the top level of
// `export const en = { ... }` in mobile/locales/en.ts (and every other locale). Rewrite
// the copy in the app's own voice; keep the {{query}} placeholder.

  // inside tabs: { ... }
    search: "Search",

  // top level
  search: {
    title: "Search",
    fieldLabel: "Search your items",
    placeholder: "Try a word or \"a phrase\"",
    idleTitle: "Find anything you've saved",
    idleBody: "Search titles and notes. Put a phrase in quotes, or add -word to leave something out.",
    searching: "Searching",
    found: "{{count}} found",
    noResultsTitle: "Nothing matches \"{{query}}\"",
    noResultsBody: "Check the spelling, or try fewer or different words.",
    more: "Show more results",
    moreLabel: "Load the next page of results",
  },
