# Story 13: Foundation (Hygiene)

**Epic:** Organization & Community SaaS
**Parent:** .cursor/tz/org_prd.md
**Branch:** `feature/fix-foundation`

## Context
Before implementing the B2B logic, we must ensure the codebase is stable (UTF-8 encoding) and the database schema is ready for hybrid search.

## Technical Tasks

### 1. Fix Encoding
- [ ] Open `prompts.yaml`, `schema.sql`, and all `.py` files in `app/`.
- [ ] Resave them explicitly with **UTF-8** encoding to prevent `cp1251` errors on Windows.
- [ ] Verify: Run the bot locally (`python app/main.py`). It must start without encoding errors.

### 2. Database Initialization
- [ ] Execute the following SQL in Supabase SQL Editor (Critical for Story 15):

```sql
-- 1. Ensure Indexes
CREATE INDEX IF NOT EXISTS idx_contacts_org ON contacts(org_id);
CREATE INDEX IF NOT EXISTS idx_org_members_user ON organization_members(user_id);

-- 2. Hybrid Search Function (RPC)
CREATE OR REPLACE FUNCTION search_hybrid(
  p_user_id BIGINT, 
  p_query TEXT
) 
RETURNS TABLE (
    id UUID,
    name TEXT,
    summary TEXT,
    meta JSONB,
    org_id UUID,
    org_name TEXT
) 
LANGUAGE sql 
AS $$
  SELECT 
    c.id, c.name, c.summary, c.meta, c.org_id, o.name as org_name
  FROM contacts c
  LEFT JOIN organization_members om ON c.org_id = om.org_id
  LEFT JOIN organizations o ON c.org_id = o.id
  WHERE 
    (
      -- Personal: (My ID + No Org)
      (c.user_id = p_user_id AND c.org_id IS NULL)
      OR
      -- Shared: (I am a member of this org)
      (om.user_id = p_user_id)
    )
    AND 
    -- Text Search
    (c.name ILIKE '%' || p_query || '%' OR c.summary ILIKE '%' || p_query || '%')
  LIMIT 20;
$$;
```

## Definition of Done
- [ ] Bot starts locally without encoding crashes.
- [ ] SQL `search_hybrid` function exists in the database.
- [ ] Indexes `idx_contacts_org` and `idx_org_members_user` exist.
