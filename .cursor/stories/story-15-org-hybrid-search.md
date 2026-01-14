# Story 15: Hybrid Search Implementation

**Epic:** Organization & Community SaaS
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/hybrid-search`
**Prerequisites:** Story 14

## Context
Users need to see both their personal contacts and contacts from organizations they belong to in a single search interface.

## Technical Tasks

### 1. Update Repository
- [ ] Add `search` method to `app/repositories/contact_repo.py`:

```python
    async def search(self, user_id: int, query: str):
        # Calls the RPC function created in Story 13
        return self.db.rpc('search_hybrid', {'p_user_id': user_id, 'p_query': query}).execute()
```

### 2. Update Search Service
- [ ] Modify `app/services/search_service.py`.
- [ ] Replace existing search logic (or add a branch) to use `repo.search` when doing text-based lookups.
- [ ] Ensure the output format handles the new `org_name` field (display it in the UI if present).

## Definition of Done
- [ ] Searching for a term returns contacts from the user's personal list.
- [ ] Searching for a term returns contacts from an organization the user is a member of.
- [ ] Results clearly indicate if a contact belongs to an organization.
