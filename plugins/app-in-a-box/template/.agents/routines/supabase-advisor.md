# supabase-advisor

Cadence: weekly (Wed 08:xx). Runs in: cloud. Connectors: Supabase.

1. Run the Supabase advisors through the Supabase connector: security, then performance
   (`get_advisors`), for this project's ref (`appbox.yaml` → `resources.supabase`).
2. Skip anything already open: search issues labelled `supabase-advisor` for the
   finding's name.
3. One issue per NEW finding, labelled `supabase-advisor`: what it is, which table or
   function, why it matters for users' data, and the migration that fixes it (draft the
   SQL; never apply it; migrations follow `.agents/rules/db-migrations.md`).
