# FinTrack — Development Phase Checklist
**ICT2216 Secure Software Development · Lab P2 Team 23**

> This is the **development** checklist — it tracks building the FinTrack application.
> For the **report** checklist, see `WORKPLAN.md`.
> Check items off as you complete them (`- [ ]` → `- [x]`), then commit.
> Phases run top-to-bottom by dependency — do not start a phase until its predecessors are done.
> `🔴 Critical` = blocks everything below it. `⚠️ Has deps` = check the note first.

---

## Team ownership

| # | Name | Track | Implementation area |
|---|------|-------|---------------------|
| 1 | **Daffa** | SE | Auth endpoints · Profile · Session flows (FR-01/02/04/05/12/14) |
| 2 | **Wen Yuan** | SE | Transactions · Upload pipeline · Dashboard · Export (FR-03/06/07/08/13) |
| 3 | **Shamik** | SE | Household · Advisor consent · Admin panel (FR-09/10/11/15/16) |
| 4 | **HC Y** | IS | Encryption utilities · File security · Secrets config (SR-01–05) |
| 5 | **Shifan** | IS | bcrypt · TOTP · Password policy · Reset tokens (SR-09–12) |
| 6 | **Owen** | IS | RBAC middleware · Audit service · Access rules (SR-06/13–16) |
| 7 | **Abdillah** | IS | Session middleware · Lockout · Rate limiting · File size (SR-07/08/17–19) |
| 8 | **Saad** | IS | Security headers · CSRF · Error handling · Prod hardening (SR-20–23) |

---

## Decisions log

| ID | Decision | Outcome |
|----|----------|---------|
| D-01 | Password hashing algorithm | **bcrypt**, work factor 12. Confirmed consistent in `db/init.sql`. |
| D-02 | Auditor role | **Removed.** Four roles only: INDIVIDUAL, HOUSEHOLD, ADVISOR, ADMIN. |
| D-03 | `transactions.amount` encryption | **Not encrypted.** SQL aggregation (SUM, AVG) required for FR-08 dashboard. Encryption at rest is at storage level only. |
| D-04 | Supabase RLS | **Feature enabled, zero policies.** Flask uses direct connection string (bypasses RLS). REST API is locked out by deny-all. |
| D-05 | `db/init.sql` | **Complete and run against Supabase.** 9 tables, 6 ENUM types, roles and global categories seeded. |

---

## Phase 0 — Foundation
> **Team-wide.** Everyone is blocked until this phase is done. Own tasks are assigned but any team member can help unblock.

- [ ] `All` 🔴 **Verify `docker-compose up` runs cleanly**
  > Flask container, Postgres container, and React container all start without errors. `db/init.sql` runs automatically on first Postgres start. Confirm all 9 tables exist in the local DB.

- [ ] `All` 🔴 **Verify Supabase connection works from Flask**
  > `backend/.env` has `DATABASE_URL` pointing to Supabase. Running Flask dev server connects and can execute a simple `SELECT 1` without error.

- [x] `Daffa` 🔴 **Create SQLAlchemy models in `backend/app/models.py`**
  > One model class per table, matching `db/init.sql` exactly: `Role`, `User`, `Session`, `PasswordResetToken`, `BankStatement`, `Category`, `Transaction`, `Consent`, `AuditLog`. Include all columns, types, foreign keys, and relationships.

- [x] `Daffa` 🔴 **Set up Flask app factory in `backend/app/__init__.py`**
  > `create_app(config)` function: initialise SQLAlchemy, register blueprints (auth, users, statements, transactions, consents, admin), attach error handlers. Blueprints can be empty stubs at this point.

- [x] `HC Y` 🔴 **Create `backend/app/config.py`**
  > `DevelopmentConfig` and `ProductionConfig` classes. Load from `.env`: `DATABASE_URL`, `SECRET_KEY`, `AES_KEY` (32 bytes), `TOTP_ENCRYPTION_KEY`, `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD`. `DEBUG=True` only in Dev.

- [x] `HC Y` 🔴 **Commit `.env.example` to repo with all required keys**
  > Never commit `.env` itself (SR-04). `.env.example` lists every required key with placeholder values. Add `.env` to `.gitignore` if not already there.

- [x] `Wen Yuan` **Set up React app routing and auth context**
  > React Router v6 routes structure. `AuthContext` that stores current user + session state. `ProtectedRoute` component that redirects unauthenticated users to `/login`.

- [ ] `All` **Smoke test: `/api/health` returns 200 and confirms DB connection**
  > Simple Flask route that runs `db.session.execute('SELECT 1')` and returns `{"status": "ok"}`. Every team member confirms this works in their local environment.
  > ✅ Confirmed: Daffa

---

## Phase 1 — Security utilities
> **Shifan + HC Y.** Build these shared utility functions before anyone touches auth or data storage. All crypto lives here — no team member should roll their own.

- [x] `Shifan` 🔴 **`hash_password(plaintext)` and `verify_password(plaintext, hashed)`**
  > In `backend/app/utils/crypto.py`. Uses `bcrypt`, work factor 12 (D-01). `hash_password` returns a string. `verify_password` returns bool. Never log or return plaintext. (SR-09)

- [x] `Shifan` 🔴 **`generate_totp_secret()` and `verify_totp_code(encrypted_secret, code)`**
  > `generate_totp_secret()` returns a base32 string. `verify_totp_code` decrypts the stored secret (using HC Y's `decrypt_field`), then verifies the 6-digit code using `pyotp`. Returns bool. (SR-11)

- [x] `Shifan` **`get_totp_provisioning_uri(email, secret)`**
  > Returns the `otpauth://` URI used to generate a QR code for authenticator app setup. (FR-01 / SR-11)

- [x] `Shifan` **`validate_password_complexity(password)` → `(bool, str)`**
  > Returns `(True, "")` or `(False, reason)`. Rules: min 12 characters, not in a common-passwords blocklist (use `zxcvbn` or a static list of top-1000 passwords), no truncation. (SR-10)

- [x] `Shifan` **`generate_secure_token()` → raw token + hashed token**
  > Used for email verification and password reset links. Returns `(raw_token, token_hash)`. Raw token is sent by email only; hash is stored in DB. Use `secrets.token_urlsafe(32)` + `hashlib.sha256`. (SR-12)

- [x] `HC Y` 🔴 **`encrypt_field(plaintext)` and `decrypt_field(ciphertext)` using AES-256-GCM**
  > In `backend/app/utils/encryption.py`. Key loaded from `AES_KEY` env var. Uses a random 12-byte IV per encryption. Ciphertext format: `base64(iv + tag + ciphertext)`. Used for: `totp_secret`, `nric`, `account_number_encrypted`. (SR-02)

- [x] `HC Y` **`hash_file_sha256(file_bytes)` → hex digest string**
  > Returns lowercase SHA-256 hex digest of the given bytes. Stored in `bank_statements.file_hash`. Called on upload and on every retrieval for integrity verification. (SR-05)

- [x] `HC Y` **Unit test all utility functions**
  > `tests/test_utils.py`: test round-trip encrypt/decrypt, correct bcrypt verify, wrong password returns False, TOTP verify with valid code, TOTP verify with wrong code, SHA-256 known-answer test.

---

## Phase 2 — Core authentication
> **Daffa + Shifan + Abdillah.** Phase 1 must be fully done first. Every other feature depends on login working.

- [x] `Daffa` 🔴 **`POST /api/auth/register`** *(FR-02 / SR-09 / SR-10)*
  > Validate email format + uniqueness. Validate password complexity (`validate_password_complexity`). Hash password (`hash_password`). Create user with `status=PENDING`. Generate email verification token (`generate_secure_token`), store hash + expiry in `users`. Send verification email with raw token in link. Return generic 201 (no indication whether email already exists).

- [x] `Daffa` **`GET /api/auth/verify-email?token=<raw>`** *(FR-02)*
  > Hash the incoming token, look up `users.email_verification_token_hash`. Check not expired. Set `status=ACTIVE`, clear `email_verification_token_hash` and `email_verification_expires_at`. Return 200.

- [x] `Daffa` 🔴 **`POST /api/auth/login` — step 1** *(FR-01 / SR-09)*
  > Check account exists and `status=ACTIVE`. Check `locked_until` (Abdillah's middleware). Verify password with `verify_password`. On failure: increment `failed_login_attempts`, log `AUTH_FAILURE` audit event. On success: if `mfa_enabled=True`, return `{"mfa_required": true, "session_challenge": <temp_token>}`; if `mfa_enabled=False`, create full session (see Abdillah's session creation task). Log `AUTH_SUCCESS`.

- [x] `Daffa` **`POST /api/auth/login/mfa` — step 2** *(FR-01 / SR-11)*
  > Validate the `session_challenge` from step 1. Verify TOTP code (`verify_totp_code`). On success: create full session, set session cookie. On failure: increment `failed_login_attempts`. Log `MFA_FAILURE` or `AUTH_SUCCESS`.

- [x] `Daffa` **`POST /api/auth/logout`** *(FR-01 / SR-19)*
  > Delete `sessions` row for current session. Set cookie expiry to the past. Return 200. Works even if session is already gone (idempotent).

- [x] `Daffa` **`GET /api/auth/me`**
  > Return: `id`, `email`, `display_name`, `role.role_name`, `mfa_enabled`, `status`. No password hash, no secrets, no NRIC.

- [x] `Daffa` **`POST /api/auth/password-reset/request`** *(FR-14 / SR-12)*
  > Look up user by email. Whether or not the email exists, return the same 200 response (prevents email enumeration). If user exists: generate reset token (`generate_secure_token`), store hash + `expires_at = now + 15 min` in `password_reset_tokens`. Send email with raw token. Log `PASSWORD_RESET_REQUESTED`.

- [x] `Daffa` **`POST /api/auth/password-reset/confirm`** *(FR-14 / SR-12)*
  > Hash incoming token, find matching `password_reset_tokens` row. Check `used_at IS NULL` and `expires_at > now`. Validate new password complexity. Hash new password. Update `users.password_hash`. Set `password_reset_tokens.used_at = now`. Log `PASSWORD_RESET_USED`.

- [x] `Daffa` **`POST /api/auth/mfa/setup`** *(FR-01 / SR-11)*
  > Generate TOTP secret. Encrypt with `encrypt_field`. Store in `users.totp_secret`. Return QR URI (`get_totp_provisioning_uri`). Do NOT set `mfa_enabled=True` yet — user must verify first.

- [x] `Daffa` **`POST /api/auth/mfa/enable`** *(FR-01 / SR-11)*
  > Verify the submitted TOTP code against the stored (encrypted) secret. If valid: set `mfa_enabled=True`. If invalid: return 400.

- [x] `Daffa` **`POST /api/auth/mfa/disable`** *(FR-01)*
  > Require current TOTP code to confirm. Set `mfa_enabled=False`, clear `totp_secret`. Log event.

- [x] `Shifan` **Email + reset token generation wired up** *(SR-12)*
  > Confirm `generate_secure_token` is being called correctly in register and password reset flows. Hash stored in DB, raw token in email link only. Verify 15-min expiry and single-use check in `/password-reset/confirm`.

- [x] `Abdillah` 🔴 **Session creation helper** *(SR-17 / SR-18)*
  > `create_session(user_id, ip_address, user_agent)`: insert row into `sessions` with `expires_at = now + 8 hours`. Return session `id`. Called by login step 1 (no MFA) and login step 2 (MFA confirmed).

- [x] `Abdillah` 🔴 **Session cookie config** *(SR-17)*
  > Set on every session creation response: `HttpOnly=True`, `Secure=True` (prod), `SameSite='Lax'`, `Path='/'`. Cookie value = raw session UUID (the `sessions.id`, not a hash — DB lookup validates it).

- [x] `Abdillah` 🔴 **Session middleware — idle + absolute timeout** *(FR-12 / SR-18)*
  > In `backend/app/middleware/session.py`. On every authenticated request: (1) check `sessions.expires_at > now` — if not, delete session, return 401. (2) check `now - sessions.last_active < 15 min` — if not, delete session, return 401. (3) update `sessions.last_active = now`.

- [x] `Abdillah` 🔴 **Account lockout — increment and check** *(SR-07)*
  > On each failed login: `users.failed_login_attempts += 1`. If `failed_login_attempts >= 5`: `users.locked_until = now + 10 min`. On every login attempt: if `locked_until IS NOT NULL AND locked_until > now`, return 403 with a generic message. On successful login: reset `failed_login_attempts = 0`, clear `locked_until`.

- [x] `Abdillah` **Rate limiting on auth endpoints** *(SR-07)*
  > Apply Flask-Limiter (or equivalent) to: `POST /api/auth/login` (10/min per IP), `POST /api/auth/password-reset/request` (5/min per IP), `POST /api/statements/upload` (20/hour per user). Return 429 on breach.

---

## Phase 3 — Profile and account management
> **Daffa.** Depends on Phase 2 auth middleware being in place.

- [x] `Daffa` **`GET /api/users/me`** *(FR-03)*
  > Return: `display_name`, `email`, `role`, `mfa_enabled`, `status`, `created_at`. No sensitive fields (no `nric` raw value, no `password_hash`).

- [x] `Daffa` **`PATCH /api/users/me`** *(FR-04)*
  > Accept: `display_name` (non-empty string). Validate and update. Return updated profile.

- [x] `Daffa` **`PATCH /api/users/me/password`** *(FR-04 / SR-10)*
  > Accept: `current_password`, `new_password`. Verify `current_password` with `verify_password`. Validate `new_password` with `validate_password_complexity`. Hash and store. Invalidate all other active sessions (prevent session fixation after password change). Log event.

- [x] `Daffa` **`DELETE /api/users/me`** *(FR-05)*
  > Accept: `password` for re-confirmation. Verify password. Delete user row — all related data cascades (sessions, transactions, statements, consents, etc.). Log `ACCOUNT_DELETED` before deletion. Return 200.

---

## Phase 4 — File upload and validation pipeline
> **Wen Yuan + HC Y + Abdillah.** Depends on Phase 2 (auth) and Phase 1 (encryption + hashing utilities). This phase implements the 7-layer validation pipeline from §9.5.

- [x] `Abdillah` 🔴 **Server-side file size check: reject > 10 MB before any processing** *(SR-08)*
  > Check `Content-Length` header or read byte count. If > 10,485,760 bytes, return 413 immediately — do not write to disk, do not parse. Cannot be bypassed by omitting the Content-Length header.

- [x] `HC Y` **MIME type validation: check file magic bytes, not just extension** *(SR-03)*
  > Use `python-magic` or equivalent. Accept only `text/csv` and `application/pdf`. Reject everything else with 415.

- [x] `HC Y` **Random server-generated filename** *(SR-03)*
  > Generate `str(uuid4()) + original_extension`. Never use the client-supplied filename for storage. Store original filename in `bank_statements.file_name` for display only.

- [x] `HC Y` **Store file outside web root** *(SR-03)*
  > Write to the path in `STORAGE_BASE_PATH` env var (must not be inside the Flask `static/` directory). For S3-compatible: upload to private bucket. Store resulting path in `bank_statements.storage_path`. Never include this path in API responses.

- [x] `HC Y` **Compute and store SHA-256 hash on upload** *(SR-05)*
  > Call `hash_file_sha256(file_bytes)` after reading the file. Store in `bank_statements.file_hash`. On every subsequent retrieval of the file, re-hash and compare — reject if mismatch.

- [x] `Wen Yuan` **CSV parser: extract transactions from bank statement CSV**
  > Parse rows into: `transaction_date` (DATE), `amount` (DECIMAL), `merchant_name` (str), `description` (str). Handle: missing columns, malformed dates, non-numeric amounts. Return list of dicts or raise `ParseError`. Implemented in `app/services/statement_parser.py`.

- [x] `Wen Yuan` **PDF parser: extract transactions from bank statement PDF**
  > Use `pdfplumber` or `PyMuPDF`. Same output format as CSV parser. Best-effort — log a warning if extraction yields zero rows. Implemented with `pdfplumber` in `app/services/statement_parser.py`.

- [x] `Wen Yuan` **`POST /api/statements/upload`** *(FR-07)*
  > Orchestrate in order: (1) size check, (2) MIME check, (3) rename, (4) store, (5) hash, (6) parse transactions, (7) insert `bank_statement` + `transaction` rows in a single DB transaction (rollback all on any step failure). Encrypt `account_number_encrypted` if extracted. Log `STATEMENT_UPLOADED` (SUCCESS or FAILURE). Imported rows default to global "Other Expense"/"Other Income" by amount sign. Stored via Supabase Storage (`app/services/storage.py`). NOTE: size pre-check (Abdillah SR-08) and magic-byte MIME (HC Y SR-03) are left as `# TODO` baselines.
  > **Category-aware two-phase upload:** the parser now reads a `category` column (`statement_parser.py`, `_CATEGORY_KEYS` → `category_name`). Upload maps each row's category to a global/user Category (`_category_lookup`), blank → Other fallback. If the file names categories that don't exist, upload does **not** import — it stores a `PENDING` statement and returns `status:'NEEDS_CATEGORIES'` with `unknown_categories[{name, suggested_type}]`. New confirm route **`POST /api/statements/<id>/import`** re-fetches the stored file, re-verifies the SHA-256 (SR-05), maps categories (now created), inserts transactions, sets `PROCESSED`, logs `STATEMENT_IMPORTED`; guards: PENDING-only (409 otherwise), object-level 404, hash-mismatch 409, still-missing category 400. Tests: `tests/test_statements.py` (13).

- [x] `Wen Yuan` **`GET /api/statements`** *(FR-07)*
  > Return list of current user's statements: `id`, `file_name`, `status`, `uploaded_at`. No `storage_path`, no `file_hash` in response.

---

## Phase 5 — Transactions and financial features
> **Wen Yuan.** Depends on Phase 4 (upload pipeline creates transactions). Auth middleware from Phase 2 must be in place.

- [x] `Wen Yuan` **`GET /api/transactions`** *(FR-06)*
  > List own transactions. Support query params: `from` (date), `to` (date), `category_id`, `type` (INCOME/EXPENSE). Object-level check: `user_id == current_user.id` enforced at query level (not just result filter). Implemented in `app/routes/transactions.py` (`from`/`to` filters; `category_id`/`type` filters still TODO). Other Phase 5 endpoints remain open.

- [x] `Wen Yuan` **`POST /api/transactions`** *(FR-06)*
  > Accept: `transaction_date`, `amount`, `category_id`, `merchant_name?`, `description?`. Validate: `amount` is a valid decimal (not float), `category_id` exists and is either global or belongs to current user, `transaction_date` is a valid date not in the far future. Insert and return created transaction.

- [x] `Wen Yuan` **`PATCH /api/transactions/:id`** *(FR-06)*
  > Object-level check: confirm `transactions.user_id == current_user.id` before updating. Partial update: accept any subset of editable fields. Implemented in `app/routes/transactions.py` (`update_transaction`); shared field validators reused with `POST`.

- [x] `Wen Yuan` **`DELETE /api/transactions/:id`** *(FR-06)*
  > Object-level check before delete. Return 204. Implemented in `app/routes/transactions.py` (`delete_transaction`); logs `TRANSACTION_DELETED` before row removal.

- [x] `Wen Yuan` **`GET /api/dashboard`** *(FR-08)*
  > Return three datasets for current user: (1) spending by category this month (SUM grouped by category), (2) monthly total spend/income for last 6 months, (3) top 5 merchants by total spend this month. All aggregated with SQL — amounts are NOT decrypted (D-03). Implemented in `app/routes/dashboard.py` (`get_dashboard`); all sums via `func.sum` in-DB (no decrypt), 6-month trend zero-filled, `@require_auth`, read-only (no audit).

- [x] `Wen Yuan` **`GET /api/transactions/export`** *(FR-13)*
  > Stream a CSV file of all own transactions. Set `Content-Disposition: attachment; filename="transactions.csv"`. Columns: date, amount, category, merchant, description. Object-level: only current user's rows. Implemented in `app/routes/transactions.py` (`export_transactions`); object-level scoped, CSV formula-injection sanitised (`_csv_safe`), logs `TRANSACTION_EXPORTED`.

- [x] `Wen Yuan` **`GET /api/categories`**
  > Return: global categories (user_id=NULL) + current user's custom categories. Label which are global vs custom. Implemented in `app/routes/categories.py` (`list_categories`); each item carries `is_global` boolean.

- [x] `Wen Yuan` **`POST /api/categories`**
  > Create custom category for current user. Enforce unique name per user (partial index in DB handles this — catch `IntegrityError` and return 409). Implemented in `app/routes/categories.py` (`create_category`); logs `CATEGORY_CREATED`.

- [x] `Wen Yuan` **`DELETE /api/categories/:id`**
  > Object-level check: must own the category (cannot delete global categories). If any transaction references this category: return 409 with clear message. Implemented in `app/routes/categories.py` (`delete_category`); pre-checks referencing transactions, `IntegrityError` backstop, returns 204; logs `CATEGORY_DELETED`.

---

## Phase 6 — RBAC and access control foundation
> **Owen.** 🔴 Must be complete before Phase 7. Every endpoint in Phases 3–5 and 7 needs these decorators applied.

- [x] `Owen` 🔴 **`@require_auth` decorator**
  > In `backend/app/middleware/auth.py`. Reads session cookie. Looks up `sessions` row. Checks session is valid (Abdillah's middleware handles timeout separately). Loads `User` into `flask.g.current_user`. Returns 401 if no valid session. Apply to every authenticated route.

- [x] `Owen` 🔴 **`@require_role(*roles)` decorator** *(SR-13)*
  > Stacks on top of `@require_auth`. A user may hold several roles; passes if `g.current_user.role_names` intersects the allowed roles. Returns 403 if not permitted. Example: `@require_role('ADMIN')`, `@require_role('ADVISOR', 'INDIVIDUAL')`. *(Multi-role: users↔roles is a many-to-many via `user_roles`; see `db/migrations/001_multi_role.sql`.)*

- [x] `Owen` 🔴 **`assert_owns_resource(record_user_id)` helper** *(SR-13)*
  > Raises `403 Forbidden` if `record_user_id != g.current_user.id`. Called inside every endpoint that accesses a user-owned record before returning or modifying it. Never rely on filtering results after fetching — check ownership at query time.

- [x] `Owen` 🔴 **`get_valid_consent(grantor_id, grantee_id)` helper** *(SR-14)*
  > Returns a `Consent` object if a consent exists between the two users that is: `status=ACTIVE`, `expires_at IS NULL OR expires_at > now`. Returns `None` if no valid consent. Used by household and advisor endpoints.

- [x] `Owen` 🔴 **`log_event(event_type, outcome, ...)` audit service** *(SR-06 / SR-16)*
  > In `backend/app/services/audit.py`. INSERT only — never UPDATE or DELETE audit_logs rows. Parameters: `event_type` (VARCHAR), `outcome` (SUCCESS/FAILURE), `user_id` (nullable), `resource_id` (nullable UUID), `ip_address`, `user_agent`. Called from every endpoint that requires audit logging per SR-16.

- [x] `Owen` **Apply `@require_auth` to all authenticated routes**
  > Go through every blueprint registered in Phases 3–5 and confirm `@require_auth` is applied. No authenticated endpoint should be reachable without a valid session.

- [x] `Owen` **Apply `@require_role` to role-restricted routes**
  > Admin endpoints: `@require_role('ADMIN')`. Household view: `@require_role('HOUSEHOLD')`. Advisor view: `@require_role('ADVISOR')`. Individual-only actions (upload, log transaction): `@require_role('INDIVIDUAL')`. Applied `@require_role('INDIVIDUAL')` to all Phase 4/5 personal-finance endpoints (statements, transactions, categories, dashboard) — only INDIVIDUAL accounts own their own financial data. Admin/household/advisor role checks land with their Phase 7 endpoints.

---

## Phase 7 — Delegated access and admin
> **Shamik + Owen.** Depends on Phase 6 (RBAC + consent helper + audit service) being complete.

- [x] `Shamik` **`POST /api/consents/household`** *(FR-09 / SR-14)*
  > `@require_role('INDIVIDUAL')`. Accept: `grantee_email`. Look up user by email, confirm they have HOUSEHOLD role. Create `Consent` row: `access_level=SUMMARY_ONLY`, `status=ACTIVE`, `expires_at=NULL`. Log `CONSENT_GRANTED`. Send notification email to grantee. Implemented in `app/routes/consents.py` (`grant_household_consent`); re-grant reactivates a revoked row (respects `UNIQUE(grantor, grantee)`), blocks self-grant, requires an ACTIVE HOUSEHOLD grantee, emails via `send_consent_notification`. Shared IP/UA helpers extracted to `app/utils/request_meta.py`.

- [x] `Shamik` **`DELETE /api/consents/household/:id`** *(FR-09)*
  > `@require_auth`. Confirm `consent.grantor_id == current_user.id`. Set `status=REVOKED`, update `updated_at`. Log `CONSENT_REVOKED`. Implemented in `app/routes/consents.py` (`revoke_household_consent`); soft delete (row kept for re-grant), ownership enforced via `assert_owns_resource` (403 on foreign), scoped to SUMMARY_ONLY consents (advisor consents 404 here), idempotent on already-revoked. Covered by `tests/test_consents.py` (7 revoke cases).

- [x] `Shamik` **`POST /api/consents/advisor`** *(FR-10 / SR-14)*
  > `@require_role('INDIVIDUAL')`. Accept: `grantee_email`. Look up user, confirm ADVISOR role. Create `Consent`: `access_level=FULL_VIEW`, `expires_at = now + 90 days`, `status=ACTIVE`. Log `CONSENT_GRANTED`. Send notification. Implemented in `app/routes/consents.py` (`grant_advisor_consent`); shares the household grant flow via a common `_grant_consent(grantee_role, access_level, expires_at)` helper — re-grant reactivates a revoked row with a fresh 90-day expiry, blocks self-grant/non-advisor/conflicting-household-consent. Covered by `tests/test_consents.py` (7 advisor-grant cases; the 12 household cases still pass, proving the refactor is behavior-preserving).

- [x] `Shamik` **`DELETE /api/consents/advisor/:id`** *(FR-10)*
  > Same pattern as household revoke. Confirm ownership, set REVOKED, log. Implemented in `app/routes/consents.py` (`revoke_advisor_consent`); shares a common `_revoke_consent(consent_id, access_level)` helper with the household revoke — ownership via `assert_owns_resource` (403 on foreign), scoped to FULL_VIEW (household consents 404 here), idempotent on already-revoked, soft delete. Covered by `tests/test_consents.py` (7 advisor-revoke cases; household revoke tests still pass).

- [x] `Shamik` **`GET /api/household/summary`** *(FR-15 / SR-14)*
  > `@require_role('HOUSEHOLD')`. Find all ACTIVE SUMMARY_ONLY consents where `grantee_id = current_user.id`. For each grantor: return aggregated summary only (total spend by category, monthly trend). **Strip all raw account numbers from response** — `account_number_encrypted` must never appear. Use `get_valid_consent` to validate before returning each grantor's data. Implemented in `app/routes/consents.py` (`household_summary_view`); per-grantor aggregation via new `app/services/analytics.py` (`household_summary`, parameterised by `user_id`, SQL sums only, no merchant/account detail), re-validates each consent with `get_valid_consent`, audits `HOUSEHOLD_SUMMARY_ACCESS`. Covered by `tests/test_consents.py` (6 summary cases). NOTE: `dashboard.py` now delegates to `analytics.full_analytics()` (coordinated refactor completed) — the owner dashboard (FR-08), household summary (FR-15), and advisor analytics (FR-16) share this one implementation; `GET /api/dashboard` response is unchanged.

- [x] `Shamik` **`GET /api/advisor/clients`** *(FR-16)*
  > `@require_role('ADVISOR')`. List all grantors who have an ACTIVE FULL_VIEW consent to current advisor. Return: grantor `id`, `display_name` only. Implemented in `app/routes/consents.py` (`advisor_clients`); lists ACTIVE, unexpired FULL_VIEW consents granted to the advisor, returns `grantor_id` + `display_name` only (no email/financial data). Covered by `tests/test_consents.py` (5 cases).

- [x] `Shamik` **`GET /api/advisor/clients/:grantor_id/analytics`** *(FR-16 / SR-14)*
  > `@require_role('ADVISOR')`. Call `get_valid_consent(grantor_id, current_user.id)` — return 403 if None. Return full dashboard analytics for that grantor (same data as `GET /api/dashboard` but for the grantor). Log `ADVISOR_DATA_ACCESS` audit event. Implemented in `app/routes/consents.py` (`advisor_client_analytics`); consent-gated via `get_valid_consent` + FULL_VIEW check (uniform 403 on malformed id / missing / insufficient consent), returns dashboard's three datasets via new `analytics.full_analytics` (adds `top_merchants`), audits `ADVISOR_DATA_ACCESS`. Covered by `tests/test_consents.py` (6 cases).

- [x] `Owen` **`GET /api/admin/users`** *(FR-11 / SR-15)*
  > `@require_role('ADMIN')`. Return: `id`, `email`, `display_name`, `role`, `status`, `created_at`. **Must not return**: `password_hash`, `totp_secret`, `nric`, `account_number_encrypted`, `email_verification_token_hash`. Any field not in this explicit allowlist must be excluded.

- [x] `Owen` **`PATCH /api/admin/users/:id/status`** *(FR-11 / SR-15)*
  > `@require_role('ADMIN')`. Accept: `status` (ACTIVE or SUSPENDED). Cannot target `current_user.id` (admin cannot suspend themselves). Log `ADMIN_ACTION` with `resource_id = target_user.id`.

- [x] `Owen` **`DELETE /api/admin/users/:id`** *(FR-11)*
  > `@require_role('ADMIN')`. Cannot target self. Delete user (cascade handles dependent records). Log `ADMIN_ACTION` before deletion.

- [x] `Owen` **`PATCH /api/admin/users/:id/roles`** *(FR-11)*
  > `@require_role('ADMIN')`. Accept: `roles` (non-empty array of role names). Cannot target self. Sets the user's full role set (many-to-many via `user_roles`). Log `ADMIN_ACTION`.

- [x] `Owen` **`GET /api/admin/audit-logs`** *(SR-16)*
  > `@require_role('ADMIN')`. Return paginated audit log. Support filters: `event_type`, `user_id`, `from_date`, `to_date`, `outcome`. Return all columns except none (audit log has no sensitive fields). Limit page size to 100 rows max.

- [x] `Owen` **Enforce SR-15 across all admin responses**
  > Review every admin endpoint response. Confirm `totp_secret`, `nric`, `account_number_encrypted`, `password_hash`, `email_verification_token_hash`, `storage_path` never appear in any admin API response. Write a shared admin serialiser that enforces this allowlist. `_serialize_user` in `backend/app/routes/admin.py` is the single allowlist used by every admin endpoint that returns user data.

---

## Phase 8 — Security hardening
> **Abdillah + Saad.** Can begin in parallel with Phase 5–7 but must be fully done before Phase 10 testing.

- [x] `Saad` 🔴 **Security response headers middleware** *(SR-21)*
  > In `backend/app/middleware/security_headers.py`. Apply to every response: `Strict-Transport-Security: max-age=31536000; includeSubDomains`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'self'`, `Referrer-Policy: no-referrer`. Register as `@app.after_request`.

- [x] `Saad` 🔴 **CSRF protection on all state-changing routes** *(SR-22)*
  > Use Flask-WTF CSRF or implement: generate CSRF token per session, require it in `X-CSRF-Token` header on every POST, PATCH, DELETE. Return 403 if missing or invalid. React frontend must include this header on all mutating requests.

- [x] `Saad` **Generic JSON error handlers** *(SR-20)*
  > Register handlers for 400, 401, 403, 404, 405, 413, 415, 429, 500. Each returns `{"error": "<generic message>"}` with no stack trace, no file path, no SQL detail, no internal variable names. Log full error server-side only.

- [x] `Saad` **Production config: confirm `DEBUG=False` and strong `SECRET_KEY`** *(SR-23)*
  > `ProductionConfig.DEBUG = False`. `SECRET_KEY` loaded from env, minimum 32 bytes. If either condition fails at startup, raise an error and refuse to start.

- [x] `Saad` **Run Bandit SAST: `bandit -r backend/ -ll`** *(SR-23)*
  > Fix all HIGH severity findings. Review and document any MEDIUM findings. Zero HIGH findings required before Phase 10.

- [x] `Abdillah` **Confirm rate limiter active in production config** *(SR-07)*
  > Verify Flask-Limiter (or equivalent) is not disabled or overridden in `ProductionConfig`. Confirm limits apply per IP for login and per user for upload.

- [x] `Abdillah` **Confirm session `Secure` cookie flag enforces HTTPS** *(SR-17)*
  > `Secure=True` must be set in `ProductionConfig`. In `DevelopmentConfig`, `Secure=False` is acceptable for local HTTP. Confirm this is config-driven, not hardcoded.

- [x] `Abdillah` **Confirm file size limit cannot be bypassed** *(SR-08)*
  > Test with a chunked upload that omits `Content-Length`. Test with a file that is exactly 10 MB (should pass) and 10 MB + 1 byte (should reject). The check must read actual byte count, not trust the header alone.

---

## Phase 9 — Frontend integration
> **All — each person integrates their own backend endpoints into the React UI.**

- [x] `Daffa` **Auth pages: Register, Login (step 1 + MFA step 2 modal), Logout**
  > Register form with email + password + password-confirm. Login form with step 1 (email + password) and conditional TOTP code input. On 401 from any API call: redirect to `/login`.

- [x] `Daffa` **Email verification landing page**
  > Route `/verify-email?token=...`. On mount: call `GET /api/auth/verify-email?token=`. Show success or error state.

- [x] `Daffa` **Password reset pages: request form and confirm form**
  > `/password-reset`: email input, generic success message regardless. `/password-reset/confirm?token=...`: new password + confirm, call `/api/auth/password-reset/confirm`.

- [x] `Daffa` **Profile page: view, edit display name, change password, MFA management**
  > Show current profile. Edit display_name inline. Change password form. MFA enroll: show QR code from setup endpoint, confirm with code to enable. Disable MFA: confirm with code.

- [x] `Daffa` **Session timeout handler**
  > Global Axios interceptor (or equivalent): on any 401 response, clear auth context, show "session expired" toast, redirect to `/login`.

- [x] `Wen Yuan` **Dashboard page** *(FR-08)*
  > Category spending chart (doughnut or bar), monthly trend chart (line), top merchants list. Data from `GET /api/dashboard`. Loading and empty states. Implemented in `frontend/src/pages/user/Dashboard.tsx`: fetches `GET /api/dashboard`, doughnut (category), 6-month area (trend), top-merchants table, this-month stat cards; loading/error(retry)/empty states. Empty (first-time) state embeds `StatementUpload` (FR-07) to import the first statement and refetches on success.

- [x] `Wen Yuan` **Transactions page** *(FR-06/13)*
  > Table with filters (date range, category, type). Add transaction form (modal or inline). Delete with confirmation. Export CSV button calls `GET /api/transactions/export` and triggers browser download. Implemented `frontend/src/pages/user/Transactions.tsx`: table + filters (from/to → backend params, category/type client-side), add/edit modal (amount sent as string; category select drives type), delete-confirm modal, Export CSV via fetch→blob→object-URL download. Uses `GET/POST /api/transactions`, `PATCH/DELETE /api/transactions/:id`, `GET /api/categories`, `GET /api/transactions/export`. Route `/transactions` (INDIVIDUAL) + sidebar link. Added **`DELETE /api/transactions`** (bulk clear all own transactions, logs `TRANSACTIONS_CLEARED`, returns `deleted_count`) with a confirmation-modal "Delete all" button.

- [x] `Wen Yuan` **Upload page** *(FR-07)*
  > File picker (CSV or PDF only). Show upload progress. On success: show parsed transaction count. On failure: show error category (too large, wrong type, parse failed). Implemented as `frontend/src/pages/user/Upload.tsx` + reusable `components/StatementUpload.tsx` (drag/drop + picker, client size/ext pre-check, multipart `POST /api/statements/upload`, uploading state, shows imported/skipped counts, surfaces 413/415/400/parse errors). Route `/upload` (INDIVIDUAL) + sidebar link added. `api()` fixed to skip the JSON Content-Type override for `FormData` so multipart boundary is preserved. **Category wizard:** on `NEEDS_CATEGORIES` the component steps through create (per-category EXPENSE/INCOME toggle pre-filled from `suggested_type`, loops `POST /api/categories`) → confirm → `POST /api/statements/<id>/import` → dashboard refetch.

- [x] `Shamik` **Household sharing UI** *(FR-09/15)*
  > Individual users: invite form (email), list of granted household accesses with revoke button. Household members: summary view of shared data (aggregated, no account numbers). Implemented `pages/user/HouseholdSharing.tsx` (invite by email, Pending/Active list, revoke) + `pages/household/HouseholdSummary.tsx` (aggregated summary — spending-by-category + monthly trend, no raw data). Added **email-invitation onboarding**: `POST /api/consents/household/invite` pre-creates a PENDING INDIVIDUAL+HOUSEHOLD account claimed via `POST /api/auth/accept-invite` (public `/accept-invite` page); inviting an existing account shares immediately. Added `GET /api/consents/household` to list shares.

- [x] `Shamik` **Advisor consent UI** *(FR-10/16)*
  > Individual users: grant advisor form (email) with note "access expires in 90 days", list of granted advisor consents with revoke. Advisors: client list, click to view client analytics. Implemented `pages/user/AdvisorSharing.tsx` (invite advisor, 90-day note, Pending/Active list, revoke) + real `pages/advisor/ClientList.tsx` (client list → consent-gated analytics: category spend, top merchants, monthly trend). Shared invite flow via `POST /api/consents/advisor/invite` (invitee gets INDIVIDUAL+ADVISOR, FULL_VIEW 90-day expiry) + `GET /api/consents/advisor`.

- [x] `Shamik` **Admin panel** *(FR-11)*
  > User table: columns for email, role, status, created_at. Actions: suspend/reinstate toggle, delete (with confirmation), role change dropdown. Audit logs table with filters. Implemented `pages/admin/UserManagement.tsx` (user table; multi-role checkboxes → `PATCH /api/admin/users/:id/roles`; suspend/activate; delete-with-confirm; self-protection) + `pages/admin/AuditLogs.tsx` (paginated `GET /api/admin/audit-logs` with event_type / user_id / outcome / from_date / to_date filters + prev/next paging). Role editing is multi-select (many-to-many `user_roles`) rather than a single dropdown.

- [ ] `HC Y` **Confirm no sensitive fields leak into API responses reaching the frontend**
  > Review React network tab in browser DevTools for: `password_hash`, `totp_secret`, `nric`, `account_number_encrypted`, `storage_path`, `email_verification_token_hash`. If any appear in any API response, flag immediately to the owner of that endpoint.

---

## Phase 10 — Testing and sign-off
> **All.** Every phase must be complete before starting this phase.

- [ ] `All` **Auth flow end-to-end: no MFA**
  > Register → verify email → login → access protected route → logout → confirm protected route returns 401.

- [ ] `All` **Auth flow end-to-end: with MFA**
  > Login → enter TOTP code from authenticator app → access granted → logout → login again → TOTP required → wrong code → correct code → access granted.

- [ ] `Shifan` **Password reset end-to-end**
  > Request reset → receive email → click link → set new password → confirm old password no longer works → confirm link cannot be reused (second use returns error).

- [ ] `Abdillah` **Account lockout end-to-end**
  > Submit 5 wrong passwords in a row → confirm 403 lockout response → wait 10 min (or manually clear `locked_until`) → correct password works again → `failed_login_attempts` resets to 0.

- [ ] `Abdillah` **Session timeout end-to-end**
  > Log in → wait 15+ min without making a request (or manually backdate `last_active`) → make a request → confirm 401 → confirm redirect to login.

- [ ] `HC Y` **File upload validation end-to-end**
  > Upload valid CSV → transactions inserted → upload PDF → upload file > 10 MB → confirm 413. Upload wrong type (e.g. `.exe`) → confirm 415. Tamper with file in storage, then trigger retrieval → confirm integrity check rejects it.

- [ ] `Owen` **IDOR test: User A cannot access User B's data**
  > Log in as User A. Get the UUID of a transaction, statement, or consent belonging to User B. Make authenticated requests to `GET /api/transactions/<user_b_id>` etc. Confirm every attempt returns 403, not 200.

- [ ] `Shamik` **Consent flow end-to-end**
  > Individual grants advisor consent → advisor can call `/api/advisor/clients/:id/analytics` successfully → individual revokes → same advisor call returns 403 → individual re-grants → advisor access restored.

- [ ] `Owen` **Admin cannot see financial data**
  > Log in as Admin. Call `GET /api/admin/users`. Confirm response JSON contains none of: `password_hash`, `totp_secret`, `nric`, `account_number_encrypted`. Attempt to call `/api/transactions` as Admin → confirm 403.

- [ ] `Saad` **Security headers check**
  > `curl -I https://<deployed-host>/api/health` → confirm all 5 headers present: HSTS, X-Frame-Options, X-Content-Type-Options, Content-Security-Policy, Referrer-Policy.

- [ ] `Saad` **Bandit SAST final run**
  > `bandit -r backend/ --severity-level high` → zero HIGH findings. Document any remaining MEDIUM findings with justification.

- [ ] `All` 🔴 **Full end-to-end demo on deployed environment**
  > Each team member demos their feature working on the EC2 + Supabase deployment (not localhost). Auth → profile → upload → dashboard → sharing → admin all working end-to-end.

---

*10 phases · ~116 tasks · Last updated: see git log*
*Report checklist → see `WORKPLAN.md`*
