// Expo's flat config + a few project rules. Add rules here, not per-file disables.
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");
// What may import or call what: only lib/api.ts calls fetch, screens don't import
// Supabase, components/ui doesn't import lib/api. Rules and reasons in that file.
const boundaries = require("./eslint.boundaries.js");

module.exports = defineConfig([
  expoConfig,
  { ignores: ["dist/*", "scripts/*", ".expo/*", "dist-*/*"] },
  {
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/^#[0-9a-fA-F]{3,8}$/]",
          message: "Use a theme token from lib/theme.ts, not a hex literal.",
        },
      ],
    },
  },
  { files: ["lib/tokens.ts"], rules: { "no-restricted-syntax": "off" } },
  // jest.mock() factories are hoisted above imports, so they must use require().
  { files: ["**/__tests__/**", "jest.setup.ts"], rules: { "@typescript-eslint/no-require-imports": "off" } },
  ...boundaries,
]);
