---
name: recipe-payments
description: Add in-app purchases / subscriptions with RevenueCat to an App in a Box app, with the entitlement decided SERVER-side (RevenueCat webhook -> entitlements table -> backend check), never trusted from the client. Use when the owner wants a paywall, subscriptions, "premium", "pro tier", IAP, or to charge for a feature. Covers store + RevenueCat setup, the webhook endpoint, migration, gating, env wiring, tests and the done-means check.
---

# Recipe: payments (RevenueCat, server-side entitlements)

Digital goods in iOS/Android apps must use store IAP (App Store 3.1.1, Play billing
policy). RevenueCat wraps both stores. The **client** shows the paywall and makes the
purchase; the **server** decides what the user is entitled to, from RevenueCat's
webhook, because anything the client says can be forged.

⚖️ Owner decisions before starting: price points and trial, the entitlement names
(`pro`), and whether the paywall is hard (blocks the core loop) or soft.

## Steps

1. **(owner)** App Store Connect: agreements/tax/banking, subscription group + products.
   Play Console: subscriptions with base plans. RevenueCat: project, both apps, products
   → one entitlement `pro` → an offering.
2. **Migration** `supabase/migrations/<ts>_entitlements.sql`:
   ```sql
   -- Rollback: drop table if exists public.revenuecat_events; drop table if exists public.entitlements;
   create table if not exists public.entitlements (
     user_id uuid not null references auth.users (id) on delete cascade,
     entitlement text not null,
     expires_at timestamptz,           -- null = lifetime
     product_id text, store text, updated_at timestamptz not null default now(),
     primary key (user_id, entitlement)
   );
   alter table public.entitlements enable row level security;
   create policy "entitlements_select_own" on public.entitlements
     for select using (auth.uid() = user_id);   -- read-only to users; writes: webhook only
   create table if not exists public.revenuecat_events (   -- idempotency: RC retries
     event_id text primary key, received_at timestamptz not null default now()
   );
   alter table public.revenuecat_events enable row level security;
   revoke all on public.revenuecat_events from anon, authenticated;
   ```
   Plus an atomic `apply_revenuecat_event(p_event_id, p_user_id, p_entitlement,
   p_expires_at, p_product, p_store)` function (pattern: `backend/AGENTS.md` → Atomic
   multi-row writes): insert the event id (return early on conflict), upsert the
   entitlement, in one transaction.
3. **Config** `backend/config.py`: `"payments (RevenueCat)": ("REVENUECAT_WEBHOOK_SECRET",)`.
4. **Webhook** `backend/routers/billing.py`: `POST /webhooks/revenuecat`,
   `include_in_schema=False`:
   - 503 if `feature_missing("payments (RevenueCat)")`; 401 unless
     `hmac.compare_digest(request Authorization header, "Bearer " + secret)` (copy
     `require_cron_secret` in `routers/internal.py`).
   - `app_user_id` is the Supabase user id (step 6); ignore events whose id isn't a
     UUID (anonymous RC ids). Map `INITIAL_PURCHASE`/`RENEWAL`/`UNCANCELLATION`/
     `PRODUCT_CHANGE` → set `expires_at = expiration_at_ms`; `EXPIRATION` → expires now;
     `CANCELLATION` → keep until expiry (they paid for the period); `TRANSFER` → move.
   - Call the rpc; always 200 after a verified, parsed event (RC retries non-2xx).
5. **Gate** `backend/services/entitlements.py`: `has_entitlement(db, user_id, "pro")`
   (`.eq("user_id", user_id)`, `expires_at is null or > now()`), and a dependency
   `require_entitlement("pro")` → 402 `{"detail": "entitlement_required"}` on premium
   routes. `GET /api/v1/me/entitlements` returns the list for the UI.
6. **Mobile**: `npx expo install react-native-purchases react-native-purchases-ui`;
   `Purchases.configure({ apiKey: <platform key> , appUserID: session.user.id })` after
   sign-in, `Purchases.logOut()` on sign-out. Paywall via `RevenueCatUI.presentPaywall()`.
   After a purchase, refetch `/api/v1/me/entitlements` (poll briefly; the webhook lands
   in seconds). Show "Restore purchases" (App Review requires it).

## Env / wiring checklist

| Where | What |
|---|---|
| Railway | `railway variables --set "REVENUECAT_WEBHOOK_SECRET=$(openssl rand -hex 32)"` |
| RevenueCat | Integrations → Webhooks: URL `https://<api>/webhooks/revenuecat`, Authorization `Bearer <same secret>` |
| EAS (preview + production) | `EXPO_PUBLIC_REVENUECAT_IOS_KEY`, `EXPO_PUBLIC_REVENUECAT_ANDROID_KEY` via `eas env:create`, and add both to `EAS_MANAGED` |
| FEATURE_CONFIG | `"payments (RevenueCat)"` (step 3) |
| `secrets-rotation.md` | already lists the webhook secret |

## Tests to add

- Webhook: 503 without secret; 401 wrong/missing header (constant-time compare);
  a replayed `event_id` changes nothing; `EXPIRATION` revokes; a non-UUID
  `app_user_id` is ignored; the event's user id (not any caller) is the row written.
- Gate: premium route 402 without entitlement, 200 with, 402 after `expires_at`;
  user A's entitlement never unlocks user B (filter-honouring fake).
- Migration static tests already require RLS + service-only function grants.

## Done means

- [ ] A sandbox purchase on a preview build flips `/api/v1/me/entitlements` to include
      `pro` within 10 s, and the premium route returns 200.
- [ ] Letting the sandbox subscription lapse (sandbox renews every few minutes) flips it
      back and the route returns 402.
- [ ] `/health` lists nothing under `features_unavailable` in production.
- [ ] The paywall screen fires a view event and purchase success/failure events.
