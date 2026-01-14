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
