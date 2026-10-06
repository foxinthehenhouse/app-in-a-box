# Add payments, AI, push, offline and social sign-in

Some capabilities are in every generated app from day one. Others depend on your
product, so they're recipes: skill files your agent follows to add them the safe way,
with the migration, the env wiring, the tests and a "done means" check. This page says
which is which.

## How to run a recipe

With the plugin installed, just ask in your app's repo: "add a paywall", "add Sign in
with Apple", "remind people every evening". Each recipe's description tells your
agent when it applies. To call one by name, use `/app-in-a-box:recipe-payments` in
Claude Code or `$recipe-payments` in Codex. Without the plugin, point any agent at the
recipe's `SKILL.md` in your clone of the kit.

Every recipe starts by naming the decisions that are yours (price points, which
model, when to ask for notification permission) and asks before it builds.

## At a glance

| Capability | In every app | Recipe |
|---|---|---|
| Payments and subscriptions | No | [recipe-payments](../../plugins/app-in-a-box/skills/recipe-payments/SKILL.md) |
| An AI feature | No | [recipe-ai-feature](../../plugins/app-in-a-box/skills/recipe-ai-feature/SKILL.md) |
| Push notifications | Client, Settings toggle, token storage and receipts | [recipe-push](../../plugins/app-in-a-box/skills/recipe-push/SKILL.md) for credentials and sending |
| Offline | Persisted cache, queued and replayed edits | [recipe-offline](../../plugins/app-in-a-box/skills/recipe-offline/SKILL.md) per new resource, or PowerSync |
| Apple and Google sign-in | Email codes only | [recipe-social-auth](../../plugins/app-in-a-box/skills/recipe-social-auth/SKILL.md) |

## Payments: RevenueCat, decided on the server

The app shows the paywall and makes the purchase through RevenueCat, which wraps both
stores. What the user is entitled to is decided **server-side**: RevenueCat's webhook
writes an `entitlements` table and the backend checks it, because anything the client
says can be forged. You set up the store products and RevenueCat yourself (agreements,
tax, banking); the recipe does the migration, webhook, gating and tests. Digital goods
must go through in-app purchase on both stores.

## AI: one fenced module, capped and evaluated

Model calls live in exactly one backend module, named in the AI fence in `AGENTS.md`.
The app never calls a model or holds a key. The recipe pins the SDK, registers the key
so `/health` names it when it's missing, adds a per-user daily cost cap in Postgres
and an eval set, and fails honestly: no canned answer pretending to be a real one. You
choose the model and the cap, and whether user content may be sent to the provider
(which changes your privacy policy and store labels).

## Push notifications

The client (`mobile/lib/push.ts`, a Settings toggle, tap-to-open the right screen) and
the backend (push tokens, a send service, a receipts job) are already there. The
recipe adds the store credentials, asks for permission at a moment that makes sense
for a feature (never on first launch), and wires the send sites with tests.

## Offline

Every app has tier 1: reads survive restarts and no signal, and edits made offline
are paused and replayed. The recipe extends that to each new resource (query hooks,
optimistic updates, idempotent creates). If your core loop must write offline for
long stretches, it describes the upgrade to PowerSync, a local SQLite database synced
with Supabase.

## Social sign-in

Email one-time codes work everywhere with no setup, so ship with those first. Add
Sign in with Apple and Google when you're preparing a TestFlight build. It uses
Supabase Auth with the native ID-token flow, no web redirect. On iOS, Apple requires
Sign in with Apple if you offer any other social login. Provider setup:
[SOCIAL_AUTH.md](../../plugins/app-in-a-box/docs/SOCIAL_AUTH.md).

## Related

- [Quickstart](../../README.md#quickstart)
- [What's in the generated repo, and why](what-you-get.md)
- [Ship to TestFlight and Google Play](ship-to-testflight-and-google-play.md)
- [Production checklist](../../plugins/app-in-a-box/docs/PRODUCTION.md): built in
  versus recipe, and store review gotchas
