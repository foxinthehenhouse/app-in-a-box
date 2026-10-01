---
max_turns: 15
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill]
runs: 3
---
Review this change before I merge it. There's no GitHub PR and no checkout here, so
skip the gates and the PR lookup: review the diff below as the PR, and give me your verdict.

```diff
--- a/backend/routers/entries.py
+++ b/backend/routers/entries.py
@@ -1,6 +1,22 @@
 from fastapi import APIRouter, Depends, HTTPException
 from backend.auth import get_current_user, User
 from backend.db import supabase

 router = APIRouter(prefix="/entries")

+
+@router.get("/{entry_id}")
+def get_entry(entry_id: str, user: User = Depends(get_current_user)):
+    rows = supabase.table("entries").select("*").eq("id", entry_id).limit(1).execute().data
+    if not rows:
+        raise HTTPException(404, "not found")
+    return rows[0]
+
+
+@router.delete("/{entry_id}")
+def delete_entry(entry_id: str, user: User = Depends(get_current_user)):
+    supabase.table("entries").delete().eq("id", entry_id).execute()
+    return {"deleted": True}
--- a/tests/test_entries.py
+++ b/tests/test_entries.py
@@ -0,0 +1,6 @@
+def test_get_entry(client, auth_headers, seed_entry):
+    r = client.get(f"/entries/{seed_entry.id}", headers=auth_headers)
+    assert r.status_code == 200
```

Context: the backend uses the Supabase service key, which bypasses row-level security.
