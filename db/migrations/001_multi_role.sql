-- =============================================================================
-- Migration 001 — Multi-role
-- users.role_id (single role)  ->  user_roles (many roles per user)
--
-- Idempotent / safe to re-run. Apply against an EXISTING database that was
-- created by an older db/init.sql (one that still has users.role_id).
-- Fresh databases created by the current db/init.sql already have this shape.
--
-- Run in the Supabase SQL Editor (dev first, then production once ratified).
-- =============================================================================

-- 1) Join table — a user can hold multiple roles.
CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, role_id)
);

CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id);

-- 2) Backfill from the old single-role column, then drop it — only while it
--    still exists, so re-running the migration is a no-op.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'role_id'
  ) THEN
    INSERT INTO user_roles (user_id, role_id)
    SELECT id, role_id FROM users WHERE role_id IS NOT NULL
    ON CONFLICT (user_id, role_id) DO NOTHING;

    DROP INDEX IF EXISTS idx_users_role_id;
    ALTER TABLE users DROP COLUMN role_id;
  END IF;
END $$;
