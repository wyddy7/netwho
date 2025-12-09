-- Добавляем поля для User Persona и настроек Recall
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS bio TEXT DEFAULT NULL,
ADD COLUMN IF NOT EXISTS recall_settings JSONB DEFAULT '{"enabled": true, "days": [5], "time": "15:00", "focus": null}'::jsonb;

