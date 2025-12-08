CREATE OR REPLACE FUNCTION match_contacts(
  query_embedding vector(1536),
  match_user_id bigint,
  match_threshold float DEFAULT 0.15, -- Еще ниже порог (было 0.2)
  match_count int DEFAULT 10 -- Больше результатов (было 5)
)
RETURNS TABLE (
  id uuid,
  name text,
  summary text,
  meta jsonb,
  distance float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    contacts.id,
    contacts.name,
    contacts.summary,
    contacts.meta,
    1 - (contacts.embedding <=> query_embedding) AS distance
  FROM contacts
  WHERE contacts.user_id = match_user_id
    AND contacts.is_archived = false
    AND contacts.embedding IS NOT NULL
    AND 1 - (contacts.embedding <=> query_embedding) > match_threshold
  ORDER BY contacts.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

