<!-- Generated from privacy/data-map.yaml by scripts/check_data_map.py. Don't edit:
     change the map, then run `python3 scripts/check_data_map.py --write`. CI fails when this is stale. -->

# Google Play Data safety answers

The answers for Play Console → **App content → Data safety**, drafted from the data
map. The owner reviews them against the running app and submits them.

**Does your app collect or share any of the required user data types?** Yes.

**Is all of the user data collected by your app encrypted in transit?** Yes: the app
talks only to HTTPS endpoints (the API, Supabase, and any analytics and crash services).

**Do you provide a way for users to request that their data is deleted?** Yes: Settings →
Delete account deletes the account and its data. Play also asks for a web link where
people can request deletion without the app: [add it at pre-launch].

Service providers that process data for you (listed under `processors` in the map)
don't count as sharing; only `third_parties` do.

| Category | Data type | Collected | Shared | Processed ephemerally | Required or optional | Purposes | Where it comes from |
|---|---|---|---|---|---|---|---|
| App activity | App interactions | Yes | No | No | Required | Analytics, App functionality | `posthog SDK`, `profiles.onboarded`, analytics events: `account_deleted`, `analytics_opt_changed`, `data_exported`, `deep_link_opened`, `profile_updated`, `push_changed`, `push_opened`, `screen_viewed`, `sheet_opened`, `sign_in_code_sent`, `sign_in_completed`, `sign_in_requested`, `theme_changed` |
| App activity | Other user-generated content | Yes | No | No | Required | App functionality | `idempotency_keys.response_body` |
| App info and performance | Crash logs | Yes | No | No | Required | App functionality | `sentry SDK` |
| App info and performance | Other app performance data | Yes | No | No | Optional | Analytics | analytics events: `account_deleted`, `api_failed`, `data_exported`, `profile_updated`, `push_changed`, `sign_in_code_sent`, `sign_in_completed` |
| Device or other IDs | Device or other IDs | Yes | No | No | Required | Analytics, App functionality | `posthog SDK`, `push_tickets.token`, `push_tokens.token` |
| Personal info | Email address | Yes | No | No | Required | Account management, App functionality | `auth.users.email` |
| Personal info | Name | Yes | No | No | Optional | App functionality | `profiles.display_name` |
| Personal info | User IDs | Yes | No | No | Required | Analytics, App functionality, Fraud prevention, security, and compliance | `audit_events.actor_id`, `idempotency_keys.user_id`, `posthog SDK`, `profiles.id`, `push_tickets.user_id`, `push_tokens.user_id`, `rate_limits.key` |
