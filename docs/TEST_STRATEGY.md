# Test strategy

Pyramid: DB/ledger invariants (pytest, real PostgreSQL) > API behaviour/RBAC (pytest) > frontend units (vitest) > end-to-end (Playwright against the running stack with real worker + real Tesseract).

## Run
```bash
cd apps/api && . .venv/bin/activate && python -m pytest -q          # needs PostgreSQL db `hem_test` (see tests/conftest.py)
cd apps/web && npm test && npm run typecheck && npx eslint src
cd apps/web && npm run e2e                                          # needs api :8431, worker, web :3417, bootstrap super admin
```
`TEST_DATABASE_URL` overrides the test DB. The pytest session drops and recreates the `public` schema of the test DB and runs Alembic migrations (so migrations are exercised on every run).

## Coverage map (financial invariants)
| Rule | Test |
|---|---|
| ATM withdrawal is not an expense; moves bank -> specific wallet | `test_atm_withdrawal_is_not_an_expense...` |
| ATM fee is a separate bank-fee expense | `test_atm_fee_is_separate_bank_fee_expense` |
| Card/bank-transfer purchase reduces bank, not wallet | `test_card_purchase_hits_bank_not_wallet`, `test_bank_transfer_*` |
| Personal-funds purchase = expense + payable | `test_personal_funds_creates_payable...` |
| Journals balanced; exact decimals; DB-level enforcement | `test_every_transaction_is_balanced...`, `test_db_rejects_unbalanced...` |
| Immutability of posted entries / append-only audit | `test_posted_lines_and_transactions_are_immutable_in_db` |
| Idempotent posting; conflicting payload rejected | `test_idempotent_posting_*` |
| Concurrent posting (same key, same expense, withdrawals) | `test_concurrent_*`, `test_double_post_*` |
| Closed periods reject postings; reopen audited | `test_close_period_*`, `test_reopen_*` |
| Reconciliation formula, carry-forward, separate pending/rejected/missing | `test_reconciliation.py` |
| Rejected/pending never posted; no self-approval | `test_employee_cannot_approve_own_and_rejected_never_posts` |
| Refund limits, reversal ordering | `test_reversal_and_refund` |
| RBAC + object-level ownership, CSRF, lockout, uploads, signed URLs | `test_security_rbac.py` |
| OCR: extraction, schema, no invented totals, failure keeps document, real Tesseract, no ledger import | `test_ocr.py` |
| Offline queue, resume, idempotent replay | `offline-queue.test.ts`, `offline.spec.ts` |
| Full business scenario (admin funds 2000, A 500, B 400, A 85 cash, B 120 card, admin 100 cash, counts, export, analytics, cross-employee denial) | `tests/e2e/scenario.spec.ts` |

## Known gaps
No load/performance tests, no cross-browser (Chromium only), no real-phone camera/HEIC test, no visual regression, no MinIO integration test (S3 backend untested live), Docker stack unexecuted, no mutation testing.
