---
type: llm
weight: 3
---
1. The review identifies that BOTH `get_entry` and `delete_entry` filter only by
   `id`, not by the caller's user id, so any signed-in user can read or delete
   another user's entry (an IDOR), and that the service key means RLS won't catch it.
2. It rates this a blocker (not a minor or style note).
3. Its verdict is "not ready" / do not merge (not "safe to merge").
4. It gives the fix: add `.eq("user_id", user.id)` to both queries (or equivalent).
5. It notes the test can't catch the bug: it never requests an entry that belongs
   to a different user.
