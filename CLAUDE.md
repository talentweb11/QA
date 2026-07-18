# FinTrack — Claude Code Guidelines

ICT2216 Secure Software Development · Lab P2 Team 23
Stack: React + TypeScript (Vercel) · Flask + Python 3.11 (EC2) · PostgreSQL (Supabase)

---

## Before writing any code

1. Read `docs/devlplan.md` — find your name, find your phase, find your tasks
2. Read every file you plan to touch
3. Search for functions related to your task before implementing them — they may already exist
4. If you need something owned by another team member that is not yet implemented, call it by its expected name and leave a `# TODO: <owner> — Phase X` comment. Do not implement it yourself
5. Only implement tasks assigned to your name. Checked-off tasks `[x]` are done — do not rewrite them

---

## Architecture

```
backend/
├── app/
│   ├── __init__.py          # App factory — create_app(config_name)
│   ├── config.py            # DevelopmentConfig / ProductionConfig
│   ├── extensions.py        # Shared instances: db, cors, limiter
│   ├── models.py            # All 9 SQLAlchemy ORM models
│   ├── routes/              # One blueprint per feature area
│   ├── middleware/          # auth.py (require_auth), session.py (validate_session)
│   ├── services/            # audit.py (log_event), mail.py (send_*), statement_parser.py, storage.py
│   └── utils/               # crypto.py, encryption.py, lockout.py
├── scripts/                 # seed_demo_user.py (local demo account)
├── tests/
└── run.py

frontend/
├── src/
│   ├── context/AuthContext.tsx
│   ├── components/ProtectedRoute.tsx
│   └── pages/
```

**The schema is owned by `db/init.sql` — never call `db.create_all()`.**
**ENUMs are defined in SQL — always use `create_type=False` in ORM models.**

---

## Where to find common utilities

Before implementing anything, check if it already exists:

| You need | Look in |
|---|---|
| Password hash / verify | `app/utils/crypto.py` → `hash_password`, `verify_password` |
| Password complexity check | `app/utils/crypto.py` → `validate_password_complexity` |
| TOTP generate / verify | `app/utils/crypto.py` → `generate_totp_secret`, `verify_totp_code` |
| Secure token (email links) | `app/utils/crypto.py` → `generate_secure_token` |
| Field encryption / decryption | `app/utils/encryption.py` → `encrypt_field`, `decrypt_field` |
| File integrity hash | `app/utils/encryption.py` → `hash_file_sha256` |
| Parse bank statement (CSV/PDF) | `app/services/statement_parser.py` → `parse_csv`, `parse_pdf` (returns `(rows, skipped)`; raises `ParseError`) |
| Store uploaded file (Supabase) | `app/services/storage.py` → `upload_statement(object_path, bytes, content_type)` (raises `StorageError`) |
| Audit logging | `app/services/audit.py` → `log_event(event_type, outcome, ip, ...)` |
| Send email | `app/services/mail.py` → `send_verification_email`, `send_password_reset_email` |
| Protect a route | `app/middleware/auth.py` → `@require_auth` (binds `g.current_user`, `g.session`) |
| Rate limiting | `app/extensions.py` → `limiter` → `@limiter.limit('N per minute')` |
| Account lockout | `app/utils/lockout.py` → `check_lockout`, `record_failed_attempt`, `clear_lockout` |

---

## Security rules — non-negotiable

- **Never log, print, or return**: `password_hash`, `totp_secret`, `nric`, `account_number_encrypted`, `storage_path`, `email_verification_token_hash`
- **Never commit `.env`** — secrets live in GitHub Secrets and are injected at deploy time
- **`audit_logs` is append-only** — never UPDATE or DELETE rows from it, ever
- **Every state-changing route** must write an audit log entry via `log_event`
- **Every authenticated route** must use `@require_auth`
- **NRIC** is stored encrypted — call `encrypt_field` on write, `decrypt_field` on read, never return the raw value in an API response
- **Session cookie** is set with `HttpOnly=True`, `Secure=True` (prod), `SameSite='Lax'` — do not change these

---

## Code conventions

- Routes are thin — validate input, call services/utils, return JSON. No business logic inline
- Use `db.session.commit()` once per request, at the end. Do not scatter multiple commits unless audit logging requires isolation
- IP address: `request.headers.get('X-Real-IP', request.remote_addr)` — nginx sets X-Real-IP
- All datetime values stored as naive UTC (`datetime.utcnow()`) — do not mix with timezone-aware datetimes
- Blueprint URL prefix is set in the blueprint definition, not in `__init__.py`
- Import `db` from `app.extensions`, not from `app` or `flask_sqlalchemy` directly

---

## Branch and PR rules

- Branch off `dev`, never off `main`
- Branch name: `feature/FR-XX-short-description` or `feature/SR-XX-short-description`
- Every PR must state which devplan tasks it checks off
- Update `docs/devlplan.md` checkboxes in the same PR as the implementation
- Never push directly to `main` or `dev`
