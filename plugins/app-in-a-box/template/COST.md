# What this app costs to run

Each service below has a free tier big enough for a prototype and the first users. This
page says what you pay, where each free tier runs out, and how to make sure a surprise
can't cost more than you chose. Prices move: check each provider's pricing page when you
sign up, and update this page when your plan changes.

## The monthly bill

| Service | What it does here | Free tier covers | You start paying when |
|---|---|---|---|
| Supabase | Postgres, auth | 2 projects, 500 MB database, 50k monthly active users; pauses after 7 idle days (`supabase-keepalive.yml` stops that) | you want managed backups, more than 500 MB, or no pausing: Pro, about $25/mo per org |
| Railway | Hosts the API | trial credit | after the trial: Hobby, about $5/mo including $5 of usage |
| Expo (EAS) | Builds, OTA updates | a limited number of builds a month; OTA updates up to a monthly-active-user cap | you build more often than the free quota, or pass the update cap |
| GitHub | Code, CI | 2,000 Actions minutes/mo on private repos | CI minutes run out (metered use is off by default, so jobs queue instead of billing) |
| Sentry (if on) | Errors, uptime | the Developer plan's monthly error quota | you pass the quota; extra usage needs a pay-as-you-go budget, which you set |
| PostHog (if on) | Analytics, replay | 1M events and 5k replays a month | you pass a product's free volume and have set a billing limit above $0 |
| Resend | Sign-in email | 100 emails a day, 3,000 a month | more sign-ins than that |
| Better Stack (if picked) | Uptime alerts | 10 monitors, 3-minute checks, email alerts | you want faster checks, phone calls or a status page |
| Cloudflare R2 | Nightly backups | 10 GB stored, no egress fees | backups pass 10 GB (30 days of a 300 MB dump) |
| Anthropic (if AI is on) | AI feature | none: pay per token | the first call |
| Apple Developer | App Store, TestFlight | none | **$99/yr** to ship on iOS |
| Google Play | Play Store | none | **$25 once** |

A typical prototype with a handful of testers runs at **about $5/mo** (Railway) plus the
store fees. The first bill that grows with users is usually Supabase Pro, then EAS.

## Spend caps and billing alerts (owner)

Do these once, before real users. An agent can't: they're billing settings in each
console. Tick them off here so the next person knows they're done.

- [ ] **Railway:** Workspace → Usage → set a **hard limit** (the service stops at it)
      and an email alert at about 75% of it. Without a hard limit a runaway loop bills
      until you notice.
- [ ] **Supabase:** Organization → Billing → **Spend cap ON** (the default on Pro: usage
      past the plan's quota is restricted instead of billed). Turn it off only on
      purpose, with a usage alert.
- [ ] **Anthropic** (if AI is on): Console → Limits → a **monthly spend limit** for the
      workspace, and email notifications at the thresholds you'd want to hear about.
      The app's own per-user caps (`recipe-ai-feature`) are the second fence.
- [ ] **Sentry:** Settings → Subscription → **pay-as-you-go budget $0** unless you mean
      it, and spike protection on. Past the quota events are dropped, not billed.
- [ ] **PostHog:** Billing → a **billing limit** on each product (analytics, replay,
      flags). $0 keeps you on the free volume; data past it is dropped.
- [ ] **Expo:** Billing → check the plan and any usage-based add-on; set a spending
      limit if your plan offers one.
- [ ] **GitHub:** Settings → Billing → Budgets: leave the Actions budget at $0 (jobs
      wait for next month's minutes instead of billing).
- [ ] **Cloudflare R2:** the bucket's lifecycle rule deletes backups after 30 days
      (`docs/runbooks/backup-restore.md`), so storage stays flat; add a billing
      notification in Cloudflare → Notifications.
- [ ] **One inbox reads all of these:** the billing email on every account goes to an
      address someone checks weekly.

## Signals worth acting on

- The uptime monitor (Better Stack or Sentry Uptime on `/health`) alerts when the API
  is down. A Supabase "your project will be paused" email means the keep-alive stopped.
- Supabase → Reports: database size creeping toward 500 MB is a month or two of
  warning before Pro.
- Railway → Metrics: memory climbing day over day is a leak, not growth.
- The AI feature's own spend line (`recipe-ai-feature`), if you added one.

## Where it's recorded

The plan and caps you chose go in `appbox.yaml` → `resources` (provision records what it
created) and in `docs/decision-log.md` when you change plans, so the reason survives.
