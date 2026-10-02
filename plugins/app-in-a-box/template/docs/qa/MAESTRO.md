# Maestro E2E

Flows live in `mobile/.maestro/`. Each route has a root testID (`<screen>-screen` or
`<screen>-sheet`) and at least one flow that targets it. `npm run gates` enforces
both through `check-maestro-coverage`, and it also fails on a flow `id:` that
nothing renders any more.

| Flow | Tag | Covers |
|---|---|---|
| `smoke.yaml` | `smoke` | launch → sign-in, email field |
| `home.yaml` | `demo` | signed-in home, tab bar |
| `edit-name.yaml` | `demo` | edit-name sheet → name on home |
| `settings.yaml` | `demo` | rows, switches, sign-out |
| `delete-account.yaml` | `demo` | cancel, then confirm with DELETE |
| `gallery.yaml` | `demo` | component gallery (dev builds) |

`common/` holds the shared steps (`launch.yaml`, `signin-demo.yaml`). Maestro only
runs a folder's top level, so these never run on their own.

## Two tags, two places

- **`smoke`** runs on any build. EAS runs it on every PR
  (`.eas/workflows/e2e.yml`: an Android emulator and an iOS simulator). It repacks the
  last `e2e-test` build with the PR's JS, or builds one when native code changed.
- **`demo`** signs in through demo mode, which is `__DEV__`-only, so a store build
  can never ship the fake backend. These run locally against Metro:

```bash
cd mobile && EXPO_PUBLIC_DEMO=1 npx expo start      # then open it in the simulator
maestro test -e APP_URL=exp://127.0.0.1:8081 .maestro/   # Expo Go
# dev client: APP_URL=<scheme>://expo-development-client/?url=http%3A%2F%2F127.0.0.1%3A8081
```

Signed-in flows on EAS would need a test account on a staging backend. Add that when
there is one, and tag those flows `staging`.

## Agents: the Maestro MCP

`.mcp.json` registers `maestro mcp` (Codex gets the same server in
`.codex/config.toml`). It needs the Maestro CLI installed and a booted simulator
or emulator. The loop:

1. `list_devices`: pick the booted device.
2. `run` a flow file, or inline commands while writing one.
3. When a selector misses, `inspect_screen` shows the real hierarchy and testIDs,
   and `take_screenshot` shows what the user would see.
4. `cheat_sheet` gives the command syntax. `maestro check-syntax <file>` validates a
   flow without a device.

Cloud runs (`run_on_cloud`) cost money and aren't pre-approved.

## Writing a flow

- Target `id:` (testIDs), not text. Copy changes and translations break text selectors.
- Start with `- runFlow: common/launch.yaml`, or `common/signin-demo.yaml` for
  signed-in screens. Each flow starts from `clearState`, so flows don't depend on
  each other.
- Wait with `extendedWaitUntil` after a network call. Never wait with a fixed sleep.
- New screen: give its root a `-screen`/`-sheet` testID, add a flow, and tag it.
  Opt out only with `// maestro-coverage: skip <reason>` in the route file.
