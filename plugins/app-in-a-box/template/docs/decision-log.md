# Decision log

Append-only. One entry per architectural or irreversible decision.

```
## YYYY-MM-DD: ADR-NNN: Title
**Status:** ACCEPTED | SUPERSEDED-BY-ADR-XXX | REJECTED
**Decision:** one sentence. **Context → choice → rationale.**
**Reversibility:** High | Medium | Low (what undoing it takes)
```

## ADR-001: Stack from App in a Box
**Status:** ACCEPTED
**Decision:** Expo + FastAPI + Supabase + Railway + PostHog + Sentry, scaffolded by
App in a Box. Context: fastest path to an instrumented TestFlight build with a
production-grade repo. Rationale: every piece has a free or cheap tier, a CLI and an
MCP server, so agents can operate it.
**Reversibility:** Medium. Backend host and analytics vendor are swappable; Supabase
Auth + RLS are load-bearing.
