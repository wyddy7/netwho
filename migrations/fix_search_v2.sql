-- Обновляем функцию поиска, чтобы она искала и по названию организации (o.name)
-- Это позволит находить контакты по запросу "skop", даже если агент не использует спец-фильтры.

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
      -- Личное: (Мой ID + Нет Организации)
      (c.user_id = p_user_id AND c.org_id IS NULL)
      OR
      -- Общее: (Я есть в таблице участников этой орги)
      (om.user_id = p_user_id)
    )
    AND 
    (
      -- Поиск по тексту (Имя, Описание ИЛИ Название Организации)
      c.name ILIKE '%' || p_query || '%' 
      OR c.summary ILIKE '%' || p_query || '%'
      OR o.name ILIKE '%' || p_query || '%'
    )
  LIMIT 20;
$$;
