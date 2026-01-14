# Story 14: Repository Layer (Secure Core)

**Epic:** Organization & Community SaaS
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/repo-layer`
**Prerequisites:** Story 13

## Context
We are moving from direct Supabase calls in handlers to a **Repository Pattern**. This is critical for security: we must validate if a user belongs to an organization *before* writing data.

## Technical Tasks

### 1. Create ContactRepository
- [ ] Create file `app/repositories/contact_repo.py`.
- [ ] Implement the class with the **Security Check** logic:

```python
# app/repositories/contact_repo.py
from loguru import logger

class ContactRepository:
    def __init__(self, supabase):
        self.db = supabase

    async def create(self, user_id: int, contact_data: dict, org_id: str = None):
        """
        Creates a contact. Validates access if org_id is provided.
        """
        # --- SECURITY CHECK START ---
        if org_id:
            # 1. Verify membership
            response = self.db.table('organization_members')\
                .select('user_id')\
                .eq('user_id', user_id)\
                .eq('org_id', org_id)\
                .execute()
            
            is_member = len(response.data) > 0
            
            if not is_member:
                logger.warning(f"SECURITY ALERT: User {user_id} tried to write to forbidden org {org_id}. Fallback to personal.")
                org_id = None 
        # --- SECURITY CHECK END ---
                
        # Force critical fields
        contact_data['org_id'] = org_id
        contact_data['user_id'] = user_id 
        
        return self.db.table('contacts').insert(contact_data).execute()

    async def get_user_orgs(self, user_id: int):
        # Returns list of org_ids or full org objects
        # Optimization: Join with organizations table to get names
        res = self.db.table('organization_members').select('org_id, organizations(name)').eq('user_id', user_id).execute()
        # Return format: [{'id': uuid, 'name': 'Python Heroes'}, ...]
        return [
            {'id': row['org_id'], 'name': row['organizations']['name']} 
            for row in res.data if row.get('organizations')
        ]
```

### 2. Refactor Handlers
- [ ] Update `app/handlers/text.py` (and any other writers).
- [ ] Replace `supabase.table('contacts').insert(...)` with `ContactRepository(supabase).create(...)`.

## Definition of Done
- [ ] `ContactRepository` exists.
- [ ] Writing with an invalid `org_id` falls back to `NULL` (Personal) and logs a warning.
- [ ] All contact creation in the app goes through the Repo.
