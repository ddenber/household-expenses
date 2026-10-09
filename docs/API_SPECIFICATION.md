# API specification

Base path `/api/v1`. Live, authoritative OpenAPI: `GET /api/openapi.json`, UI at `/api/docs`.
Auth: HttpOnly cookie `hem_session`; every non-GET request needs header `X-CSRF-Token` (value from login / `GET /auth/me`).
Money: JSON strings with <= 2 decimals (`"85.00"`). Errors: `{"error": {"code": "...", "message": "...", ...}}` with HTTP 401/403/404/409/422/429.
Ledger operations require `idempotency_key` in the body.

| Method & path | Role | Purpose |
|---|---|---|
| POST `/auth/login` · POST `/auth/logout` · GET `/auth/me` | all | session |
| GET/POST `/users` · PATCH `/users/{id}` | admin(+auditor read) | users |
| POST `/households` | super admin | new household + first financial admin |
| GET/POST `/categories` · DELETE `/categories/{id}` | all read / admin write | categories (archive) |
| GET `/accounts` · POST `/bank-accounts` | admin/auditor; employee sees own wallet | accounts with ledger-derived balances |
| POST `/ledger/opening-balance` `/funding` `/atm-withdrawal` `/cash-return` `/employee-transfer` `/reimbursement` | admin | cash operations (never expenses; ATM `fee` posts a separate bank-fee txn) |
| POST `/ledger/transactions/{id}/reverse` | admin | reversal with reason |
| GET `/ledger/transactions` (filters `type, account_id, expense_id, date_from, date_to`) · GET `/ledger/transactions/{id}` | admin/auditor | ledger |
| POST `/expenses` (idempotent by `client_ref`) · GET `/expenses` (filters) · GET/PATCH `/expenses/{id}` | owner / admin | expenses |
| POST `/expenses/{id}/documents` (multipart `file`, **202**) | owner / admin | upload page; OCR async |
| POST `/expenses/{id}/ocr/retry` | owner / admin | re-run OCR |
| POST `/expenses/{id}/submit` `{confirm_low_confidence}` | owner / admin | -> submitted |
| POST `/expenses/{id}/approve` `/reject` `/return` | admin (not owner) | approval |
| POST `/expenses/{id}/post` · `/reverse` · `/refund` | admin (not owner) | ledger posting |
| POST `/expenses/{id}/reopen` | owner / admin | rejected -> draft |
| GET `/documents/{id}/url` | owner / admin / auditor | short-lived signed URL (audited) |
| GET `/files?k&exp&sig` | signed | local-storage file download |
| GET `/reconciliation?year&month[&user_id]` · `/reconciliation/overview` | own / admin | computed reconciliation |
| POST `/reconciliation/declare` · `/close` · `/reopen` | own (declare) / admin | period lifecycle |
| GET `/reconciliation/statement.pdf` | own / admin | PDF statement |
| GET `/dashboard/admin` · `/dashboard/employee` | admin·auditor / employee | KPIs (each admin KPI carries a `link` to its source records) |
| GET `/analytics/spend?group=supplier\|category` | admin/auditor | ledger-derived spend |
| GET `/exports/expenses` · `/exports/transactions` (`format=csv\|xlsx`) | admin/auditor | exports |
| GET `/audit` | admin/auditor | append-only audit log |
| GET `/api/health` | public | liveness |

Notable error codes: `insufficient_funds`, `period_closed`, `invalid_transition`, `self_approval`, `idempotency_conflict`, `needs_confirmation`, `refund_exceeds_original`, `too_many_decimals`, `csrf`, `rate_limited`, `locked`.
