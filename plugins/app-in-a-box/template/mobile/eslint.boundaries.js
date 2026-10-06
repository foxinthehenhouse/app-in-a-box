// Architecture boundaries as lint errors, not prose (AGENTS.md rule 1: backend computes,
// frontend displays). Spread into eslint.config.js; core ESLint rules only, so there is
// nothing extra to install. Fix the import, don't disable the rule: moving a boundary is
// an architecture decision, so it goes in docs/decision-log.md with the config change.
//
//   - Only lib/api.ts talks to the network. Screens and components go through its typed
//     adapters (and lib/query.ts hooks), so every call gets auth, X-Request-ID and errors.
//   - Screens don't reach into Supabase. lib/auth.tsx and lib/session.ts own the client;
//     data goes through the API, where the backend scopes it by user id.
//   - components/ui/ is presentation. It takes data as props and never calls the API, so
//     it renders the same in the gallery, in tests and in a screen.
const FETCH_MESSAGE =
  "Only lib/api.ts calls fetch. Add a typed function there (and a query hook in lib/query.ts) and call that.";

module.exports = [
  {
    files: ["**/*.ts", "**/*.tsx"],
    // Tests stub the network (globalThis.fetch = jest.fn()); they never call it.
    ignores: ["lib/api.ts", "**/__tests__/**", "jest.setup.ts"],
    rules: {
      "no-restricted-globals": ["error", { name: "fetch", message: FETCH_MESSAGE }],
      "no-restricted-properties": [
        "error",
        ...["globalThis", "window", "global", "self"].map((object) => ({
          object,
          property: "fetch",
          message: FETCH_MESSAGE,
        })),
      ],
    },
  },
  {
    files: ["app/**/*.ts", "app/**/*.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@supabase/supabase-js",
              message: "Screens don't talk to Supabase. Use lib/auth.tsx for the session and lib/api.ts for data.",
            },
          ],
          patterns: [
            {
              group: ["**/lib/supabase"],
              message: "Screens don't import lib/supabase. Use lib/auth.tsx for the session and lib/api.ts for data.",
            },
          ],
        },
      ],
    },
  },
  {
    files: ["components/ui/**/*.ts", "components/ui/**/*.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["**/lib/api"],
              message: "components/ui is presentation: take data as props. The screen loads it (lib/query.ts) and passes it in.",
            },
          ],
        },
      ],
    },
  },
];
