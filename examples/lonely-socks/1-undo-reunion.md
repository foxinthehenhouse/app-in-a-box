# Undo a reunion  (#1)

## Problem & outcome
You tap Reunite, then realise one sock is navy, not black. Right now the mistake is
permanent and inflates the north-star metric. **Outcome:** one tap returns both socks
to the drawer. Metric: `sock_unreunited` stays under 10% of `sock_reunited`. If it
goes higher, matching is too loose.

## Scope / Out of scope
In scope: undo from the Reunions screen for the most recent reunion.
Out of scope: undo history, editing a sock's colour.

## UX
Reunions screen: under the count, show "Last reunion: Pink, spotted · Undo". After
undo, announce "Pink, spotted socks are single again" and refresh the count.

## Data & API
No migration. `POST /api/v1/socks/{id}/unpair` sets both socks back to `lonely`,
clears `reunited_with`/`reunited_at`, and returns the sock. Rejected with 409 if the
sock isn't reunited; 404 if it isn't yours. `Drawer` gains an additive field,
`lastReunion: Sock | null`.

## Analytics
`sock_unreunited` {success, error_code, duration_ms}

## Requirements → Tests
- FR-01 Undo returns both socks to lonely → TC-01 `test_unpair_returns_both_to_drawer`
- FR-02 Can't undo someone else's sock → TC-02 `test_cannot_unpair_someone_elses_sock`
- FR-03 Can't undo a lonely sock → TC-03 `test_unpair_lonely_is_conflict`
- FR-04 Drawer reports the most recent reunion → TC-04 `test_drawer_reports_last_reunion`

## Risks & ⚖️
⚖️ Only the most recent reunion can be undone (I chose simplicity over a full
history). The owner can widen this later.
