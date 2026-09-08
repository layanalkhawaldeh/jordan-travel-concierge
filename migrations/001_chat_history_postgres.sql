-- Run this once on an existing PostgreSQL database before starting version 3.0.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS title VARCHAR DEFAULT 'New conversation';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'active';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

UPDATE conversations
SET title = 'New conversation'
WHERE title IS NULL OR BTRIM(title) = '';

UPDATE conversations
SET status = 'active'
WHERE status IS NULL OR BTRIM(status) = '';

UPDATE conversations
SET created_at = COALESCE(created_at, updated_at, CURRENT_TIMESTAMP);

ALTER TABLE agent_execution_logs ADD COLUMN IF NOT EXISTS model_name VARCHAR;
