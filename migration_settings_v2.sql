-- Обновляем дефолт settings
ALTER TABLE users ALTER COLUMN settings SET DEFAULT '{"confirm_add": true, "confirm_delete": true}'::jsonb;

-- Если уже есть записи, обновляем их (миграция данных)
UPDATE users SET settings = '{"confirm_add": true, "confirm_delete": true}'::jsonb WHERE settings IS NULL OR settings = '{}'::jsonb;

