# AGENTS.md — rules for contributors and coding agents

Product owner: Denis (non-programmer). Decide routine technical matters yourself; **ask** only about financial rules, security, privacy, external cost, irreversible operations, or major scope.

## Non-negotiable invariants
1. All financial writes go through `apps/api/app/services/ledger.py` (`post_transaction`, `reverse_transaction`). Never insert `journal_lines` elsewhere. Never store balances; derive from the ledger.
2. Money is `Decimal`/`NUMERIC(18,4)`; JSON money is a string; never use floats (backend or frontend). The frontend contains **no** financial logic.
3. Posted entries are immutable; correct by reversal. Every operation needs an idempotency key. Keep DB triggers (`alembic/versions/0002_*`) intact.
4. ATM withdrawals, funding, cash returns and employee transfers are **not** expenses. Card/transfer purchases do not touch employee wallets. See `docs/ACCOUNTING_RULES.md` before changing posting rules.
5. OCR/AI only suggests. It must never import the ledger or post. Low-confidence fields need human confirmation. Never invent totals.
6. RBAC is server-side with object-level ownership (employees: 404 on foreign ids). No self-approval. Update `docs/ROLE_PERMISSION_MATRIX.md` and tests when permissions change.
7. UI strings only in `apps/web/src/i18n/sq.ts` (Albanian). No fake data in production views; demo data only via `python -m app.cli seed-demo`. No decorative buttons.
8. No secrets in git, no PII (names, emails, receipt text, amounts) in logs.

## Workflow
- Backend: `cd apps/api && . .venv/bin/activate && python -m pytest -q`. New migration: `alembic revision --autogenerate -m ...` (never edit applied revisions).
- Frontend: `cd apps/web && npm test && npm run typecheck && npx eslint src`. Next.js here is v16 (read `node_modules/next/dist/docs/` for API changes).
- E2E: `npm run e2e` in `apps/web` (needs running api/worker/web + bootstrap super admin).
- Ports used locally: web 3417, api 8431, Redis 6389 (dev box), Postgres 5432.
- Be honest in summaries: say what was tested and what was not.
