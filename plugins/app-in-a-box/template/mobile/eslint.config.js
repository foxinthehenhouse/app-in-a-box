// Expo's flat config + a few project rules. Add rules here, not per-file disables.
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  { ignores: ["dist/*", "scripts/*", ".expo/*", "dist-*/*"] },
  {
    files: ["**/*.ts", "**/*.tsx"],
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      // Complexity: split a function that trips these; don't raise the numbers. ESLint
      // counts every &&, ||, ??, ?. and default parameter as a branch (Python's mccabe
      // doesn't), so a component's JSX conditionals and prop defaults cost more here
      // than the same logic in the backend's ruff C90 (max 10).
      complexity: ["error", 15],
      "max-depth": ["error", 4],
      "max-nested-callbacks": ["error", 4],
      // TanStack Query's mutation callbacks take five; nothing of ours should need more.
      "max-params": ["error", 5],
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
]);
