-- Unified Search Hybrid Function (Fixes security leak and respects pending user search)
-- This migration replaces all previous versions of search_hybrid.

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
  -- Security: Join organization_members with BOTH org_id and user_id to verify membership
  LEFT JOIN organization_members om ON c.org_id = om.org_id AND om.user_id = p_user_id
  LEFT JOIN organizations o ON c.org_id = o.id
  WHERE 
    (
      -- Personal: (My ID + No Org)
      (c.user_id = p_user_id AND c.org_id IS NULL)
      OR
      -- Shared: (I am a member of this org AND status is approved OR pending)
      -- Story 23 requires pending users to be able to search (with app-layer limits)
      (om.user_id IS NOT NULL AND om.status IN ('approved', 'pending'))
    )
    AND 
    -- Text Search (Name, Summary OR Organization Name)
    (
      c.name ILIKE '%' || p_query || '%' 
      OR c.summary ILIKE '%' || p_query || '%'
      OR o.name ILIKE '%' || p_query || '%'
    )
    AND c.is_archived = false
  LIMIT 20;
$$;
