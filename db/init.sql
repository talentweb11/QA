-- =============================================================================
-- FinTrack — Database Initialisation Script
-- Safe to re-run against an existing database (idempotent).
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

DO $$ BEGIN
  CREATE TYPE user_status AS ENUM ('PENDING', 'ACTIVE', 'SUSPENDED');
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;

DO $$ BEGIN
  CREATE TYPE statement_status AS ENUM ('PENDING', 'PROCESSED', 'FAILED');
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;

DO $$ BEGIN
  CREATE TYPE category_type AS ENUM ('INCOME', 'EXPENSE');
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;

DO $$ BEGIN
  CREATE TYPE consent_access_level AS ENUM ('SUMMARY_ONLY', 'FULL_VIEW');
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;

DO $$ BEGIN
  CREATE TYPE consent_status AS ENUM ('ACTIVE', 'REVOKED');
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;

DO $$ BEGIN
  CREATE TYPE audit_outcome AS ENUM ('SUCCESS', 'FAILURE');
EXCEPTION WHEN duplicate_object THEN NULL; END; $$;

-- =============================================================================
-- TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- roles
-- Lookup table — seeded at the bottom of this file.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS roles (
    id        SERIAL      PRIMARY KEY,
    role_name VARCHAR(20) UNIQUE NOT NULL
);

-- -----------------------------------------------------------------------------
-- users
-- Core identity and authentication table.
-- Sensitive columns are hashed or encrypted at the application layer before
-- being written here. The DB only ever sees ciphertext or hashes.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                              UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    email                           VARCHAR(255) UNIQUE NOT NULL,
    password_hash                   VARCHAR(255) NOT NULL,
    totp_secret                     VARCHAR(255) NULL,
    mfa_enabled                     BOOLEAN      NOT NULL DEFAULT FALSE,
    display_name                    VARCHAR(100) NOT NULL,
    nric                            VARCHAR(255) NULL,
    status                          user_status  NOT NULL DEFAULT 'PENDING',
    email_verification_token_hash   VARCHAR(255) NULL,
    email_verification_expires_at   TIMESTAMP    NULL,
    failed_login_attempts           INTEGER      NOT NULL DEFAULT 0,
    locked_until                    TIMESTAMP    NULL,
    created_at                      TIMESTAMP    NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN users.password_hash IS
  'bcrypt hash with work factor >= 12. Plaintext password never stored or logged.';
COMMENT ON COLUMN users.totp_secret IS
  'AES-256-GCM encrypted at application layer before storage. Null until MFA is enrolled.';
COMMENT ON COLUMN users.nric IS
  'AES-256-GCM encrypted at application layer. PDPA-sensitive PII.';
COMMENT ON COLUMN users.email_verification_token_hash IS
  'Hashed token. Raw token sent via email only. Set to NULL after successful verification.';

-- -----------------------------------------------------------------------------
-- user_roles
-- Many-to-many: a user may hold several roles (e.g. INDIVIDUAL + HOUSEHOLD).
-- Every account gets INDIVIDUAL as a base role at registration; HOUSEHOLD and
-- ADVISOR are additive; ADMIN is assigned out-of-band.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    PRIMARY KEY (user_id, role_id)
);

-- -----------------------------------------------------------------------------
-- sessions
-- Server-side session store. Raw session token held by client only.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL,
    ip_address  VARCHAR(45) NOT NULL,
    last_active TIMESTAMP   NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMP   NOT NULL
);

COMMENT ON COLUMN sessions.token_hash IS
  'Hashed session token. Raw token held by client only. Never stored in plaintext.';

-- -----------------------------------------------------------------------------
-- password_reset_tokens
-- Single-use, time-limited tokens for the password reset flow (SR-12).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP   NOT NULL,
    used_at    TIMESTAMP   NULL,
    created_at TIMESTAMP   NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN password_reset_tokens.token_hash IS
  'Hashed token. Raw token sent via email only. Check used_at IS NULL before accepting.';

-- -----------------------------------------------------------------------------
-- bank_statements
-- Metadata for uploaded bank statement files. Files live outside the web root.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bank_statements (
    id                       UUID             PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                  UUID             NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_number_encrypted VARCHAR(255)     NULL,
    file_name                VARCHAR(255)     NOT NULL,
    storage_path             VARCHAR(500)     NOT NULL,
    file_hash                VARCHAR(64)      NOT NULL,
    status                   statement_status NOT NULL DEFAULT 'PENDING',
    uploaded_at              TIMESTAMP        NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN bank_statements.account_number_encrypted IS
  'AES-256-GCM encrypted at application layer. Raw account number never stored in plaintext.';
COMMENT ON COLUMN bank_statements.file_hash IS
  'SHA-256 hex digest. Must be verified against the file on every retrieval.';
COMMENT ON COLUMN bank_statements.storage_path IS
  'Internal path or object-store URI. Never expose to client or include in API responses.';

-- -----------------------------------------------------------------------------
-- categories
-- user_id = NULL  → global system category available to all users.
-- user_id = <uuid> → custom category for that user only.
-- Uniqueness enforced via partial indexes below (NULL-safe).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id      UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID          NULL REFERENCES users(id) ON DELETE CASCADE,
    name    VARCHAR(100)  NOT NULL,
    type    category_type NOT NULL
);

-- -----------------------------------------------------------------------------
-- transactions
-- Individual financial records — manually entered or parsed from a statement.
-- amount is NOT encrypted: aggregation (SUM, AVG) is required for dashboard
-- queries (FR-08). Encryption at rest is handled at the storage level.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id               UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id          UUID          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    statement_id     UUID          NULL REFERENCES bank_statements(id) ON DELETE SET NULL,
    category_id      UUID          NOT NULL REFERENCES categories(id),
    transaction_date DATE          NOT NULL,
    amount           DECIMAL(12,2) NOT NULL,
    merchant_name    VARCHAR(255)  NULL,
    description      TEXT          NULL,
    created_at       TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- consents
-- Models both household member invitations (SUMMARY_ONLY) and financial
-- advisor grants (FULL_VIEW) in a single table.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consents (
    id           UUID                 PRIMARY KEY DEFAULT uuid_generate_v4(),
    grantor_id   UUID                 NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    grantee_id   UUID                 NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    access_level consent_access_level NOT NULL,
    status       consent_status       NOT NULL DEFAULT 'ACTIVE',
    expires_at   TIMESTAMP            NULL,
    created_at   TIMESTAMP            NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMP            NOT NULL DEFAULT NOW(),
    UNIQUE (grantor_id, grantee_id)
);

-- -----------------------------------------------------------------------------
-- audit_logs
-- Append-only security event log.
-- Application code must NEVER UPDATE or DELETE rows in this table (SR-06/SR-16).
-- No updated_at trigger is applied here by design.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id         UUID          PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID          NULL REFERENCES users(id) ON DELETE SET NULL,
    event_type VARCHAR(50)   NOT NULL,
    resource_id UUID         NULL,
    outcome    audit_outcome NOT NULL,
    ip_address VARCHAR(45)   NOT NULL,
    user_agent VARCHAR(500)  NULL,
    timestamp  TIMESTAMP     NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN audit_logs.timestamp IS
  'Append-only. Application code must never UPDATE or DELETE rows in this table.';

-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_users_email        ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_locked_until ON users(locked_until);

CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id    ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_prt_user_id    ON password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_prt_expires_at ON password_reset_tokens(expires_at);

CREATE INDEX IF NOT EXISTS idx_bank_statements_user_id ON bank_statements(user_id);

CREATE INDEX IF NOT EXISTS idx_transactions_user_id          ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_statement_id     ON transactions(statement_id);
CREATE INDEX IF NOT EXISTS idx_transactions_transaction_date ON transactions(transaction_date);

CREATE INDEX IF NOT EXISTS idx_categories_user_id ON categories(user_id);

-- Partial indexes for categories uniqueness (NULL-safe)
CREATE UNIQUE INDEX IF NOT EXISTS categories_global_name_unique
  ON categories(name) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS categories_user_name_unique
  ON categories(user_id, name) WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_consents_grantor_id ON consents(grantor_id);
CREATE INDEX IF NOT EXISTS idx_consents_grantee_id ON consents(grantee_id);
CREATE INDEX IF NOT EXISTS idx_consents_expires_at ON consents(expires_at);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id    ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp  ON audit_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type);

-- =============================================================================
-- TRIGGER — updated_at for consents
-- Not applied to audit_logs (append-only by design).
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_consents_updated_at ON consents;
CREATE TRIGGER update_consents_updated_at
  BEFORE UPDATE ON consents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- SEED DATA
-- =============================================================================

INSERT INTO roles (role_name)
VALUES ('INDIVIDUAL'), ('HOUSEHOLD'), ('ADVISOR'), ('ADMIN')
ON CONFLICT (role_name) DO NOTHING;

INSERT INTO categories (user_id, name, type) VALUES
  (NULL, 'Groceries',      'EXPENSE'),
  (NULL, 'Dining & Food',  'EXPENSE'),
  (NULL, 'Transport',      'EXPENSE'),
  (NULL, 'Utilities',      'EXPENSE'),
  (NULL, 'Healthcare',     'EXPENSE'),
  (NULL, 'Shopping',       'EXPENSE'),
  (NULL, 'Entertainment',  'EXPENSE'),
  (NULL, 'Housing & Rent', 'EXPENSE'),
  (NULL, 'Education',      'EXPENSE'),
  (NULL, 'Salary',         'INCOME'),
  (NULL, 'Freelance',      'INCOME'),
  (NULL, 'Investment',     'INCOME'),
  (NULL, 'Other Expense',  'EXPENSE'),
  (NULL, 'Other Income',   'INCOME')
ON CONFLICT DO NOTHING;
