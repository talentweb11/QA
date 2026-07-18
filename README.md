# ICT2216 Secure Software Development — Group 23

## Stack
- **Frontend**: React + TypeScript + Vite, deployed on Vercel
- **Backend**: Python 3.11 + Flask, deployed on EC2 via Docker + Gunicorn
- **Database**: Supabase (PostgreSQL)
- **Orchestration**: Docker Compose (production backend only)
- **Reverse Proxy**: Nginx on EC2 (routes `/api/` to backend container)

---

## New Collaborator Setup

If you just got access to this repo, follow these steps before anything else.

### 1. Clone the repo
```bash
git clone https://github.com/<org>/ICT2216-Secure-Software-Dev.git
cd ICT2216-Secure-Software-Dev
git checkout dev
```

### 2. Get the `.env` file
The `.env` file is not in the repo. Get it from a teammate over a secure channel and place it at the project root:
```
ICT2216-Secure-Software-Dev/.env
```
See `.env.example` for the full list of required values.

### 3. Set up the backend
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Set up the frontend
```bash
cd frontend
npm install
```

### 5. Run locally
Open two terminals:
```bash
# Terminal 1 — backend (http://localhost:5000)
cd backend && source venv/bin/activate && python run.py

# Terminal 2 — frontend (http://localhost:5173)
cd frontend && npm run dev
```

Open `http://localhost:5173`. API calls are automatically proxied to the local Flask backend via Vite — no extra config needed.

---

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production. Protected — no direct pushes. |
| `dev` | Integration branch. All feature PRs target here. |
| `feature/xxx` | Individual features. Branch off `dev`. |

**Never push directly to `main` or `dev`.**

```bash
# Always start a new feature like this
git checkout dev
git pull origin dev
git checkout -b feature/your-feature-name
```

`dev` → `main` is done by the team lead when ready to release, via a reviewed PR.

---

## Local Development Flow

```
git checkout -b feature/your-feature (from dev)
         │
         ▼
┌─────────────────────────────────┐
│         Terminal 1 — Backend    │
│  cd backend                     │
│  source venv/bin/activate       │
│  python run.py                  │
│  → Flask on localhost:5000      │
└─────────────────────────────────┘
┌─────────────────────────────────┐
│         Terminal 2 — Frontend   │
│  cd frontend                    │
│  npm run dev                    │
│  → Vite on localhost:5173       │
│  → /api/* proxied to :5000      │
└─────────────────────────────────┘
         │
         ▼
  Develop and test at http://localhost:5173
         │
         ▼
  git add / commit / push feature branch
         │
         ▼
  Open PR → dev (CI runs, no deploy)
```

---

## Production CI/CD Flow

```
feature/xxx → PR → dev → PR → main
                              │
                              ├──► Vercel auto-deploys frontend
                              │
                              └──► GitHub Actions (deploy-prod.yml)
                                   SSH into EC2
                                   → git pull
                                   → rewrite .env
                                   → docker compose up (backend only)
                                   → nginx serves /api/ → backend
```

Every PR triggers CI automatically:
- Backend: `pytest`
- Frontend: ESLint + Vitest + TypeScript build
- Docker: image build check

Merges to `main` only happen through a reviewed PR that passed CI.

---

## Local vs Production

| | Local | Production |
|---|---|---|
| Frontend | Vite dev server (`:5173`) | Vercel |
| Backend | Flask directly (`:5000`) | Docker + Gunicorn on EC2 |
| API routing | Vite proxy | Nginx → backend container |
| Database | Supabase (shared) | Supabase |
| HTTPS | No | Yes (Certbot + DuckDNS) |
| Triggered by | Manual | Merge to `main` |

---

## What Collaborators Do NOT Need to Touch
- EC2 or SSH keys
- Vercel — auto-deploys on merge to `main`, nothing to configure
- GitHub Secrets — already set up
- Docker — only needed to test the prod build locally (`docker compose up --build`)

---

## Running with Docker (optional, prod-like local test)
```bash
cp .env.example .env  # fill in real values
docker compose up --build
```
App will be available at `http://localhost`.

---

## Development Plan

All feature work is tracked in [`docs/devlplan.md`](docs/devlplan.md). Read this before picking up any task.

### How to work against the devplan

**1. Find your task**
Each task in `devlplan.md` is assigned to a team member by name and maps to specific FR/SR references (e.g. `FR-01`, `SR-09`). Find your name and your current phase.

**2. Check dependencies**
Phases run top-to-bottom. Do not start a phase until all tasks in the previous phase are checked off. Tasks marked `⚠️ Has deps` have a note — read it before starting.

**3. Branch naming**
Name your branch after the FR or SR you are implementing:
```bash
git checkout -b feature/FR-01-login
git checkout -b feature/SR-09-bcrypt
```

**4. Check off tasks as you complete them**
When a task is done, update `docs/devlplan.md`:
```
- [ ] → - [x]
```
Commit the devplan update in the same PR as the implementation — not separately.

**5. PR description**
Every PR must state:
- Which FR/SR items it implements
- Which devplan tasks it checks off
- Any linked tasks in other phases that are now unblocked

### Backend structure

```
backend/
├── app/
│   ├── __init__.py        # App factory — create_app(config_name)
│   ├── config.py          # DevelopmentConfig / ProductionConfig
│   ├── extensions.py      # Shared db and cors instances
│   ├── models.py          # SQLAlchemy ORM models (9 tables)
│   ├── routes/
│   │   ├── auth.py        # FR-01/02/14 — authentication
│   │   ├── users.py       # FR-03/04/05 — profile management
│   │   ├── statements.py  # FR-07 — file upload
│   │   ├── transactions.py# FR-06/08/13 — transactions + dashboard
│   │   ├── consents.py    # FR-09/10/15/16 — delegated access
│   │   ├── admin.py       # FR-11 — admin panel
│   │   └── health.py      # GET /api/health
│   ├── middleware/        # Auth, session, security headers (add here)
│   ├── services/          # Audit service and shared logic (add here)
│   └── utils/             # crypto.py, encryption.py (Phase 1 — Shifan/HC Y)
├── tests/
└── run.py
```

Add new files under the relevant directory. Do not put business logic in `routes/` — keep routes thin and delegate to `services/` or `utils/`.

### Key rules
- **Never call `db.create_all()`** — schema is owned by `db/init.sql`, not the ORM
- **Never log or return** `password_hash`, `totp_secret`, `nric`, `account_number_encrypted`, or `storage_path`
- **Every authenticated route** must use `@require_auth` (Phase 6 — Owen)
- **Every state-changing route** must be covered by CSRF protection (Phase 8 — Saad)
- **Every security event** must call `log_event()` from the audit service (Phase 6 — Owen)

---

## Notes
- **Never commit directly to `main` or `dev`.** All work goes through a feature branch and a reviewed PR. Direct pushes to `main` are blocked — pushing to `dev` is not blocked but doing so bypasses CI and code review, which is not allowed.
- Never commit `.env` to Git.
- If you touch frontend dependencies, regenerate the lockfile using Linux Node to keep it CI-compatible:
  ```bash
  docker run --rm -v "$(pwd)":/app -w /app node:20-alpine npm install --package-lock-only --no-audit --no-fund
  ```
