-- Добавляем поле settings в таблицу users
ALTER TABLE users ADD COLUMN IF NOT EXISTS settings JSONB DEFAULT '{"rage_mode": false}'::jsonb;

-- Обновляем функцию поиска, чтобы она поддерживала "Показать всех" (пустой эмбеддинг или спец. запрос)
-- Но так как мы используем векторный поиск, "показать всех" - это просто сортировка по created_at (без вектора).
-- Создадим отдельную функцию для получения последних контактов

CREATE OR REPLACE FUNCTION get_recent_contacts(
  match_user_id bigint,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id uuid,
  name text,
  summary text,
  meta jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    contacts.id,
    contacts.name,
    contacts.summary,
    contacts.meta
  FROM contacts
  WHERE contacts.user_id = match_user_id
    AND contacts.is_archived = false
  ORDER BY contacts.created_at DESC
  LIMIT match_count;
END;
$$;

