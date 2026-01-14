-- Migration for Story 20: Schema & Access Control
-- Add status and free_searches_used to organization_members

-- 1. Add status field with constraints
ALTER TABLE organization_members 
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';

-- Add check constraint separately to avoid issues if column already exists
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_org_member_status') THEN
        ALTER TABLE organization_members 
        ADD CONSTRAINT check_org_member_status CHECK (status IN ('pending', 'approved', 'banned'));
    END IF;
END $$;

-- 2. Add free_searches_used field
ALTER TABLE organization_members 
ADD COLUMN IF NOT EXISTS free_searches_used INTEGER DEFAULT 0;

-- 3. Create index for fast status checks
CREATE INDEX IF NOT EXISTS idx_org_members_status ON organization_members(status);

-- 4. Update existing members to 'approved'
UPDATE organization_members SET status = 'approved' WHERE status IS NULL OR status = 'pending';

-- 5. Update Hybrid Search to respect status
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
  LEFT JOIN organization_members om ON c.org_id = om.org_id AND om.user_id = p_user_id
  LEFT JOIN organizations o ON c.org_id = o.id
  WHERE 
    (
      -- Personal: (My ID + No Org)
      (c.user_id = p_user_id AND c.org_id IS NULL)
      OR
      -- Shared: (I am a member of this org AND approved)
      (om.user_id = p_user_id AND om.status = 'approved')
    )
    AND 
    -- Text Search
    (c.name ILIKE '%' || p_query || '%' OR c.summary ILIKE '%' || p_query || '%')
  LIMIT 20;
$$;
