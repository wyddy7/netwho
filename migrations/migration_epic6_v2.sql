-- Функция для получения N случайных контактов (для батч-анализа Recall)
CREATE OR REPLACE FUNCTION get_random_contacts(p_user_id BIGINT, p_limit INT DEFAULT 3)
RETURNS TABLE (
  id uuid,
  name text,
  summary text,
  meta jsonb,
  last_interaction timestamptz
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
    c.last_interaction
  FROM contacts c
  WHERE c.user_id = p_user_id
    AND c.is_archived = false
  ORDER BY random()
  LIMIT p_limit;
END;
$$;

