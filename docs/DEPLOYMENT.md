# Deployment

## Docker Compose (db, redis, minio, api, worker, web)
```bash
cp .env.example .env        # set SECRET_KEY, POSTGRES_PASSWORD, S3_SECRET_KEY, ADMIN_PASSWORD
docker compose up --build -d
docker compose exec api python -m app.cli bootstrap-admin --name "Admin" --email you@example.com --household "Shtepia"   # uses ADMIN_PASSWORD
# optional, NEVER in production:
docker compose exec api python -m app.cli seed-demo
```
Web: http://localhost:3417 · API/OpenAPI: http://localhost:8431/api/docs · MinIO console: http://localhost:9001.
`api` runs `alembic upgrade head` on start (`RUN_MIGRATIONS=1`). `worker` runs `rq worker ocr`.
**Status of this stack:** the Compose/Docker files were written and the production Next build was verified, but Docker was **not available in the build environment**, so `docker compose up` was never executed. Treat the first run as a smoke test.

## Local development without Docker (what was actually used)
Requirements: Python 3.12, Node 22, PostgreSQL 16, Redis, Tesseract (`eng`, `sqi`).
```bash
cd apps/api && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
cp ../../.env.example .env   # then use localhost URLs and STORAGE_BACKEND=local
alembic upgrade head
python -m app.cli bootstrap-admin --name Admin --email admin@hem.local --password '...'
uvicorn app.main:app --port 8431 &        rq worker ocr &
cd ../web && npm ci --legacy-peer-deps && npm run dev      # http://localhost:3417 (proxies /api to :8431)
```

## Production checklist
- Set `APP_ENV=production` (refuses default `SECRET_KEY`, disables demo seeding), `COOKIE_SECURE=true`, serve via HTTPS reverse proxy.
- `STORAGE_BACKEND=s3`; keep the bucket private. `S3_PUBLIC_ENDPOINT_URL` must be reachable from browsers (for signed URLs).
- Back up PostgreSQL (the ledger) and the bucket; test restores.
- Rotate `SECRET_KEY` only with awareness that outstanding signed local URLs become invalid.
- Run a single `web` build per API hostname (the `/api` rewrite target is compiled at build time via `API_INTERNAL_URL`).
- Not included in Phase 1: MFA, email delivery, virus scanning, centralized log shipping, HA.
