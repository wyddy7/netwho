-- 1. Для "Обратного Триала" (даем Pro при регистрации)
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TIMESTAMP WITH TIME ZONE;

-- 2. Для счетчика News-Jacking (лимит 3 раза)
ALTER TABLE users ADD COLUMN IF NOT EXISTS news_jacks_count INTEGER DEFAULT 0;

-- 3. Для рефералки (откуда пришел юзер, на будущее)
ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_source VARCHAR(50);

-- 4. АМНИСТИЯ (Выдать 3 дня триала всем СУЩЕСТВУЮЩИМ фри-юзерам, чтобы реактивировать их)
-- Мы обновляем только тех, у кого нет активной Pro-подписки
UPDATE users 
SET trial_ends_at = NOW() + INTERVAL '3 days' 
WHERE pro_until IS NULL OR pro_until < NOW();

