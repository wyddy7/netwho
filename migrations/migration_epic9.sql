-- Story 09: Monetization & Telegram Stars
-- Add pro_until column to users table to track subscription status

ALTER TABLE users 
ADD COLUMN IF NOT EXISTS pro_until TIMESTAMPTZ DEFAULT NULL;

-- Optional: Index for querying pro users quickly (if needed later)
-- CREATE INDEX idx_users_pro_until ON users(pro_until);

