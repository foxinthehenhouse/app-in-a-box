/**
 * Jest setup (package.json `jest.setupFiles`, set by the kit's mobile-deps.sh).
 * Native modules with no JS fallback get their libraries' official mocks here,
 * once, so every test that renders the app (which mounts the query cache,
 * connectivity and the persister) works without per-file boilerplate.
 */
jest.mock("@react-native-async-storage/async-storage", () =>
  require("@react-native-async-storage/async-storage/jest/async-storage-mock"),
);
jest.mock("@react-native-community/netinfo", () => require("@react-native-community/netinfo/jest/netinfo-mock.js"));
