<!-- Generated from privacy/data-map.yaml by scripts/check_data_map.py. Don't edit:
     change the map, then run `python3 scripts/check_data_map.py --write`. CI fails when this is stale. -->

# App Store privacy answers

The answers for App Store Connect → your app → **App Privacy**, drafted from the data
map. The owner reviews them against the running app and submits them; Apple holds the
developer responsible for their accuracy.

**Do you or your third-party partners collect data from this app?** Yes.

**Is data used to track people across apps and websites owned by other companies?** No.

| Data type | Apple's group | Linked to the user | Used for tracking | Purposes | Where it comes from |
|---|---|---|---|---|---|
| Email Address | Contact Info | Yes | No | App Functionality | `auth.users.email` |
| Name | Contact Info | Yes | No | App Functionality | `profiles.display_name` |
| Crash Data | Diagnostics | No | No | App Functionality | `sentry SDK` |
| Other Diagnostic Data | Diagnostics | Yes | No | Analytics | analytics events: `account_deleted`, `api_failed`, `data_exported`, `profile_updated`, `push_changed`, `sign_in_code_sent`, `sign_in_completed` |
| Device ID | Identifiers | Yes | No | Analytics, App Functionality | `posthog SDK`, `push_tickets.token`, `push_tokens.token` |
| User ID | Identifiers | Yes | No | Analytics, App Functionality | `posthog SDK`, `profiles.id`, `push_tickets.user_id`, `push_tokens.user_id`, `rate_limits.key` |
| Product Interaction | Usage Data | Yes | No | Analytics, App Functionality | `posthog SDK`, `profiles.onboarded`, analytics events: `account_deleted`, `analytics_opt_changed`, `data_exported`, `deep_link_opened`, `profile_updated`, `push_changed`, `push_opened`, `screen_viewed`, `sheet_opened`, `sign_in_code_sent`, `sign_in_completed`, `sign_in_requested`, `theme_changed` |

## Privacy manifest (PrivacyInfo.xcprivacy)

The same data types, plus the required-reason APIs below, are written to
`mobile/app.json` → `expo.ios.privacyManifests`; Expo turns that into the app's
`PrivacyInfo.xcprivacy` at build time.

| Required-reason API | Reasons |
|---|---|
| DiskSpace | E174.1 |
| FileTimestamp | C617.1 |
| SystemBootTime | 35F9.1 |
| UserDefaults | CA92.1 |
