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
  -- Проверяем членство в организации через эффективный JOIN
  LEFT JOIN organization_members om ON c.org_id = om.org_id AND om.user_id = match_user_id
  LEFT JOIN organizations o ON c.org_id = o.id
  WHERE 
    (
      -- Личное: (Мой ID + Нет Организации)
      (c.user_id = match_user_id AND c.org_id IS NULL)
      OR
      -- Общее: (Я найден в таблице участников этой орги И статус approved)
      (om.user_id IS NOT NULL AND om.status = 'approved')
    )
    AND c.is_archived = false
    AND c.embedding IS NOT NULL
    AND 1 - (c.embedding <=> query_embedding) > match_threshold
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
