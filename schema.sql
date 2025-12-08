-- Сначала удалим старое, если есть (для чистоты эксперимента)
DROP TABLE IF EXISTS interactions;
DROP TABLE IF EXISTS contacts;
DROP TABLE IF EXISTS users;
DROP FUNCTION IF EXISTS match_contacts;

-- Включаем векторное расширение
CREATE EXTENSION IF NOT EXISTS vector;

-- Таблица users (Пользователи)
CREATE TABLE users (
  id BIGINT PRIMARY KEY,  -- Telegram ID
  username TEXT,
  full_name TEXT NOT NULL,
  is_premium BOOLEAN DEFAULT false,
  terms_accepted BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица contacts (Контакты/Записи)
CREATE TABLE contacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  summary TEXT,
  raw_text TEXT,
  meta JSONB DEFAULT '{}'::jsonb,
  -- text-embedding-3-small = 1536
  embedding vector(1536),  
  created_at TIMESTAMPTZ DEFAULT NOW(),
  last_interaction TIMESTAMPTZ,
  reminder_at TIMESTAMPTZ,
  is_archived BOOLEAN DEFAULT false
);

-- Таблица interactions (История взаимодействий)
CREATE TABLE interactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('meeting', 'call', 'message', 'note')),
  content TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индексы
CREATE INDEX idx_contacts_user_id ON contacts(user_id);
-- ivfflat индекс для ускорения поиска (опционально, на малых объемах можно без него)
CREATE INDEX idx_contacts_embedding ON contacts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_contacts_reminder_at ON contacts(reminder_at) WHERE reminder_at IS NOT NULL;

-- В MVP отключаем RLS, так как бот работает через API Key и сам контролирует доступ по user_id
ALTER TABLE contacts DISABLE ROW LEVEL SECURITY;
ALTER TABLE interactions DISABLE ROW LEVEL SECURITY;
ALTER TABLE users DISABLE ROW LEVEL SECURITY;

-- RPC функция для поиска
CREATE OR REPLACE FUNCTION match_contacts(
  query_embedding vector(1536),
  match_user_id bigint,
  match_threshold float DEFAULT 0.4,
  match_count int DEFAULT 5
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
