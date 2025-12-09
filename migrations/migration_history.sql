-- Таблица истории чата
CREATE TABLE IF NOT EXISTS chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- Индекс для быстрого поиска последних сообщений
CREATE INDEX IF NOT EXISTS idx_chat_history_user_created ON chat_history(user_id, created_at DESC);

-- RPC функция для получения последних N сообщений (чтобы не гонять лишние данные)
CREATE OR REPLACE FUNCTION get_chat_history(p_user_id BIGINT, p_limit INT)
RETURNS TABLE (
    role TEXT,
    content TEXT
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT t.role, t.content
    FROM (
        SELECT ch.role, ch.content, ch.created_at
        FROM chat_history ch
        WHERE ch.user_id = p_user_id
        ORDER BY ch.created_at DESC
        LIMIT p_limit
    ) t
    ORDER BY t.created_at ASC;
END;
$$;

