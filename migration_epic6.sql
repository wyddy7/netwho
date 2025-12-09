-- Функция для получения случайного контакта пользователя
-- Используется для Active Recall (Random Coffee)
CREATE OR REPLACE FUNCTION get_random_contact(p_user_id BIGINT)
RETURNS TABLE (
  id uuid,
  name text,
  summary text,
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
    c.last_interaction
  FROM contacts c
  WHERE c.user_id = p_user_id
    AND c.is_archived = false
  ORDER BY random()
  LIMIT 1;
END;
$$;

