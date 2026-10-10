# Menaxheri i Shpenzimeve të Shtëpisë — Household Expense Manager (Phase 1 MVP)

Digital control of household **cash**: a financial admin funds a bank account, employees withdraw cash at ATMs, buy things, photograph receipts; the admin approves, posts to a double-entry ledger, and reconciles each employee's cash every month. It is a financial control system, not a receipt scanner. UI is Albanian (strings in `apps/web/src/i18n/sq.ts`), mobile-first, EUR, light/dark.

```
apps/web   Next.js 16 + TypeScript + Tailwind + shadcn/ui, installable PWA, IndexedDB offline queue
apps/api   FastAPI + SQLAlchemy 2 + Alembic, RQ worker for OCR
docs/      architecture, accounting rules, DB, security, OCR, API, deployment, tests, failure modes, role matrix
tests/e2e  Playwright scenario (admin funds 2000 ... cross-employee access denied) + offline spec
```

## Run it (no Docker, as developed)
```bash
# prerequisites: Python 3.12, Node 22, PostgreSQL 16, Redis, tesseract-ocr (+ eng, sqi)
cd apps/api && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
cat > .env <<'ENV'
DATABASE_URL=postgresql+psycopg://hem:hem_dev_pw@localhost:5432/hem
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me
STORAGE_BACKEND=local
OCR_PROVIDER=tesseract
ENV
alembic upgrade head
python -m app.cli bootstrap-admin --name "Admin" --email admin@hem.local --password 'choose-a-password'
python -m app.cli seed-demo           # OPTIONAL demo household "DEMO" (refused when APP_ENV=production)
uvicorn app.main:app --port 8431 & rq worker ocr &
cd ../web && npm ci --legacy-peer-deps && npm run dev     # http://localhost:3417
```
Or `docker compose up --build` (see `docs/DEPLOYMENT.md`; **not executed** in the build environment).

Demo logins (only after `seed-demo`): `admin@demo.local`, `punonjes1@demo.local`, `punonjes2@demo.local`, password `demo-password-123` (override with `DEMO_PASSWORD`). Demo data lives in its own household with a visible "DEMO" banner; real households never contain it.

## Tests
```bash
cd apps/api
export TEST_DATABASE_URL='postgresql+psycopg://hem:...@localhost:5432/hem_test'
export HEM_ALLOW_TEST_DB_RESET=1
python -m pytest -q                         # requires a disposable PostgreSQL test database
cd apps/web && npm test && npm run e2e     # 11 unit tests, 10 Playwright tests (needs the stack running)
```

## What is real vs simulated
- **Real**: ledger, constraints/triggers, approvals, reconciliation, PDF/CSV/XLSX, RBAC, sessions/CSRF, uploads + validation, local OCR via Tesseract (heuristic field extraction), offline queue.
- **Simulated (clearly labelled "Simuluar" in the UI)**: the `simulated` OCR provider (`OCR_PROVIDER=simulated`), used only in unit tests.
- **Not verified**: Docker stack, MinIO/S3 backend against a live server, camera/HEIC on real phones, other browsers.

See `docs/` for details and `AGENTS.md` for contributor/agent rules.
