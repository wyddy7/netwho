# Story 19: True Hybrid Search (RAG + SQL)

**Epic:** Organization & Community SaaS
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/true-hybrid-search`
**Prerequisites:** Story 18

## Context
Current search relies heavily on exact SQL matching. While accurate for names, it fails for semantic queries ("who in skop", "find developer") or when the user's query structure doesn't match the database fields exactly. We need to restore Vector Search (RAG) but ensure it respects Organization security boundaries.

## Technical Tasks

### 1. Database Upgrade (Secure Vector Search)
- [ ] Create `migrations/fix_vector_search_v3.sql`.
- [ ] Update `match_contacts` RPC function to:
    -   Join `organization_members` to verify access.
    -   Return `org_id` and `org_name` in the result set (for UI consistency).
    -   Filter by `(user_id = me AND personal) OR (member of org)`.

### 2. Search Service Upgrade (Double Barrel)
- [ ] Modify `app/services/search_service.py`:
    -   Restore `ai_service.get_embedding(query)`.
    -   Execute SQL Search (`repo.search`) -> `results_sql`.
    -   Execute Vector Search (`rpc match_contacts`) -> `results_vec`.
    -   **Merge Strategy:**
        -   Start with `results_sql` (High Precision).
        -   Append `results_vec` if ID not already in list (Semantic Recall).
        -   Limit total results (e.g., 20).

## Definition of Done
- [ ] Query "skop" finds contacts from "Skop" org via SQL (already working) OR Vector (context match).
- [ ] Query "python dev" finds contacts with "developer" in notes via Vector search.
- [ ] Results show Organization tags correctly.
- [ ] Security is maintained (user sees only their own or shared contacts).
