# Database

PostgreSQL 16, managed by Alembic (`apps/api/alembic`). All ids are UUIDs. Money is `NUMERIC(18,4)`.

## Tables

- `households(id, name, base_currency='EUR')`
- `users(id, household_id, email unique, name, role, password_hash, is_active, failed_logins, locked_until)`
- `sessions(id, user_id, token_hash, csrf_token, expires_at, revoked_at)`
- `categories(id, household_id, name, is_active, account_id)` – each category owns an expense account.
- `suppliers(id, household_id, name, normalized_name)` unique per household.
- `accounts(id, household_id, code, name, type, kind, owner_user_id?, currency, is_active)`
  - `type`: asset | liability | expense | equity | suspense
  - `kind`: bank | employee_wallet | expense_category | bank_fees | reimbursement_payable | suspense | opening_equity | owner_funding
- `financial_transactions(id, household_id, type, description, occurred_at, currency, idempotency_key, payload_hash, expense_id?, reverses_id?, reversed_by_id?, status posted|reversed, reason, created_by, created_at)`
  - unique `(household_id, idempotency_key)`.
- `journal_lines(id, transaction_id, account_id, debit, credit, currency, fx_rate, amount_base_debit, amount_base_credit)` with CHECK exactly one side > 0.
- `expenses(id, household_id, user_id, created_by, client_ref?, category_id?, supplier_id?, supplier_name, expense_date, total, currency, payment_method, status, notes, rejection_reason, ocr_needs_confirmation, bank_account_id?, submitted_at, approved_by, approved_at, posted_txn_id, refund_of_id?, is_refund)` unique `(user_id, client_ref)`.
- `expense_status_history(id, expense_id, from_status, to_status, actor_id, note, at)`
- `documents(id, household_id, expense_id, owner_user_id, page_no, filename, mime, size, sha256, storage_key, ocr_status)`
- `ocr_results(id, document_id, expense_id, provider, provider_real, schema_version, raw_text, extraction JSONB, confidence JSONB, status, error, created_at)`
- `ocr_corrections(id, expense_id, field, old_value, new_value, user_id, at)`
- `reconciliations(id, household_id, user_id, year, month, status open|closed, declared_count, expected_closing, difference, difference_txn_id, closed_by, closed_at, note)` unique `(user_id,year,month)`.
- `reconciliation_events(id, reconciliation_id, action close|reopen|declare, reason, actor_id, at)`
- `audit_log(id bigserial, household_id, actor_id, action, entity_type, entity_id, details JSONB, at)`

## DB-level guarantees (migration triggers)

- `journal_lines`: UPDATE and DELETE rejected.
- `financial_transactions`: DELETE rejected; UPDATE allowed **only** to set `status='reversed'` + `reversed_by_id` (all other columns must be unchanged).
- `audit_log`, `expense_status_history`, `ocr_corrections`, `reconciliation_events`: UPDATE/DELETE rejected.
- Deferred constraint trigger on `journal_lines` verifying each transaction balances (sum base debit = sum base credit, >= 2 lines) at commit.
- `financial_transactions.type` values: opening_balance, funding, atm_withdrawal, bank_fee, cash_return, employee_transfer, cash_expense, card_expense, transfer_expense, personal_funds_expense, refund, reimbursement, cash_difference (a reversal reuses the original type with `reverses_id` set).

## Indexes
`journal_lines(account_id)`, `financial_transactions(household_id, occurred_at)`, `expenses(household_id,status)`, `expenses(user_id, expense_date)`, `documents(sha256)`.
