-- CRITICAL FIX: Удаляем ВСЕ версии функции match_contacts, чтобы устранить конфликт имен (Error PGRST203).

-- 1. Удаляем версию из Story 19 (с match_user_id)
DROP FUNCTION IF EXISTS match_contacts(vector, bigint, float, int);

-- 2. Удаляем старую версию (с allowed_org_ids), которая вызывает конфликт
-- Сигнатура: query_embedding vector, match_threshold float, match_count int, match_user_id bigint, allowed_org_ids uuid[]
DROP FUNCTION IF EXISTS match_contacts(vector, float, int, bigint, uuid[]);
-- На всякий случай пробуем другие перестановки, которые могли быть в старых миграциях
DROP FUNCTION IF EXISTS match_contacts(vector, bigint, uuid[], float, int);

-- 3. Создаем ЕДИНСТВЕННУЮ правильную версию (True Hybrid / B2B)
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
  -- Проверяем членство: Либо это личный контакт юзера, либо юзер есть в organization_members этой орги
  LEFT JOIN organization_members om ON c.org_id = om.org_id AND om.user_id = match_user_id
  LEFT JOIN organizations o ON c.org_id = o.id
  WHERE 
    (
      (c.user_id = match_user_id AND c.org_id IS NULL) -- Личное
      OR
      (om.user_id IS NOT NULL) -- Общее (доступ подтвержден через JOIN)
    )
    AND c.is_archived = false
    AND c.embedding IS NOT NULL
    AND 1 - (c.embedding <=> query_embedding) > match_threshold
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
