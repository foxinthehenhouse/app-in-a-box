# Lonely Socks: product brief

**One-liner:** Sock owners use Lonely Socks to reunite lost pairs.
**Target user:** Anyone with a drawer full of single socks. **Problem (their words):**
"I have 11 single socks and no idea which ones have a partner somewhere."

## Core loop
- **Trigger:** you find a single sock in the laundry.
- **Action:** log it in 5 seconds (colour + pattern).
- **Feedback:** if a matching lonely sock is already logged, the app says so. Tap **Reunite** 🎉
- **Return reason:** your reunion count, plus a weekly "drawer amnesty" nudge.

## Screens (v1)
- **Sign in:** email code.
- **Drawer (home):** your lonely socks, with the possible matches highlighted.
- **Log a sock:** pick a colour and a pattern, then save.
- **Reunions:** total reunited, and a streak of weeks with at least one reunion.
- **Settings:** name, analytics opt-out, sign out.

## Data model (v1)
- `socks`: id, user_id → auth.users, colour (enum of 10), pattern (plain | striped |
  spotted | argyle | novelty), note (≤ 60 chars), status (lonely | reunited),
  reunited_with (sock id, nullable), created_at, reunited_at. RLS on user_id.

A "match" means the same colour and pattern, both lonely, and the same user. It is
computed by the backend, not the app.

## North-star metric
Socks reunited per active user per week.

## The 5 analytics events that measure it
`sock_logged` · `match_suggested` · `sock_reunited` (success/failure) ·
`drawer_viewed` · `reunions_viewed`

## Out of scope for v1
Photos, sharing a drawer with a household, sock-matching ML, selling socks.

## Open questions
Should the drawer amnesty nudge be a push notification? Deferred; no push in v1.
