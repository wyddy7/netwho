-- Fix for Story 23: Allow pending users to search (controlled by App Layer limits)
-- Also fix Vector Search security hole (exclude banned users)

-- 1. Update SQL Search (search_hybrid)
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
      -- Personal
      (c.user_id = p_user_id AND c.org_id IS NULL)
      OR
      -- Shared: Member of org AND (approved OR pending)
      -- App Layer handles the "3 free searches" limit for pending users.
      -- We strictly exclude 'banned' or NULL status if not personal.
      (om.user_id = p_user_id AND om.status IN ('approved', 'pending'))
    )
    AND 
    -- Text Search
    (c.name ILIKE '%' || p_query || '%' OR c.summary ILIKE '%' || p_query || '%')
  LIMIT 20;
$$;

-- 2. Update Vector Search (match_contacts)
CREATE OR REPLACE FUNCTION match_contacts(
  query_embedding vector(1536),
  match_user_id bigint,
  match_threshold float DEFAULT 0.5,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id uuid,
  name text,
  summary text,
  meta jsonb,
  org_id uuid,
  org_name text,
  distance float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    c.id,
    c.name,
    c.summary,
    c.meta,
    c.org_id,
    o.name as org_name,
    1 - (c.embedding <=> query_embedding) AS distance
  FROM contacts c
  LEFT JOIN organization_members om ON c.org_id = om.org_id AND om.user_id = match_user_id
  LEFT JOIN organizations o ON c.org_id = o.id
  WHERE 
    (
      -- Personal
      (c.user_id = match_user_id AND c.org_id IS NULL)
      OR
      -- Shared: Member AND (approved OR pending)
      (om.user_id IS NOT NULL AND om.status IN ('approved', 'pending'))
    )
    AND c.is_archived = false
    AND c.embedding IS NOT NULL
    AND 1 - (c.embedding <=> query_embedding) > match_threshold
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
