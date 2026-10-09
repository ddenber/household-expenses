# Failure-mode analysis

| # | Failure | Effect | Mitigation | Verified by |
|---|---|---|---|---|
| 1 | User double-taps submit / posting button | Duplicate expense or double posting | Client lock + `client_ref` idempotent create; posting keyed `expense-post:{id}`; row lock + state check | `test_double_post_fails_safely_and_concurrent_post_once`, `test_create_is_idempotent_by_client_ref`, e2e offline spec (double click) |
| 2 | Retry of a financial request after timeout | Double posting | Required `idempotency_key`; same key+payload replays, different payload -> 409 | `test_idempotent_posting_*` |
| 3 | Two admins post concurrently / concurrent withdrawals | Overdraw, duplicate | Account rows locked `FOR UPDATE` in id order; non-negative asset check inside the transaction | `test_concurrent_*` |
| 4 | Bug or direct SQL writes unbalanced/changed journal | Corrupt books | DB triggers: immutable lines/transactions, deferred balance check, append-only audit | `test_db_rejects_unbalanced...`, `test_posted_lines_*_immutable_in_db` |
| 5 | OCR engine crashes / returns garbage | No data, or wrong data | Document kept; status `failed`; manual entry; schema validation; low-confidence flag; AI never posts | `test_failed_ocr_keeps_document...`, `test_extractor_never_invents_total` |
| 6 | OCR misreads a total | Wrong expense amount | Human must confirm low-confidence; admin approval; corrections stored; totals never inferred | `test_low_confidence_requires_confirmation...` |
| 7 | Redis / worker down | OCR not processed | Upload still succeeds (202); document stays `pending`; retry endpoint; ledger unaffected. Rate limiting degrades to in-memory | manual (see Deployment) |
| 8 | Object storage down | Upload fails | Upload returns error before DB commit of the document row is visible (storage put precedes commit); client retries from IndexedDB queue | offline queue unit tests |
| 9 | Network loss on phone | Lost receipt | IndexedDB queue stores files; resumes per page; idempotent server calls | vitest + Playwright offline spec |
| 10 | Employee tries to read/alter another's data | Privacy / fraud | Object-level ownership, 404 on foreign ids, signed URLs only after authz | `test_employee_cannot_see_or_touch_other_employees_data`, e2e step 9 |
| 11 | Employee approves own expense | Fraud | Server blocks `self_approval` for everyone | `test_employee_cannot_approve_own...` |
| 12 | Edit in a closed month | Reconciled figures change silently | Ledger rejects postings touching a closed employee-month; reopen needs reason + audit, reverses suspense posting | `test_close_period...`, `test_reopen_...` |
| 13 | Cash count differs from ledger | Unexplained cash | Difference computed, shown separately, optionally parked in Suspense; never hidden in expenses | reconciliation tests |
| 14 | Brute-force login | Account takeover | Per-IP rate limit, per-account lockout, argon2 | `test_brute_force_lockout` |
| 15 | Malicious upload (wrong type, huge, polyglot) | Stored XSS / DoS | Magic-byte allowlist, Pillow/PyMuPDF decode, size/page caps, random keys, served with fixed content-type + nosniff | `test_upload_validation` |
| 16 | Leaked signed URL | Receipt exposure | 5-minute expiry, HMAC; access audited | `test_signed_url_roundtrip_and_tamper` |
| 17 | Float rounding | Cent drift | NUMERIC + Decimal, 2-decimal input only, money as strings in JSON, frontend never parses floats for money | `test_every_transaction_is_balanced_and_decimal_exact`, vitest |
| 18 | Clock / date edge (future dates, month boundary) | Wrong period | Future dates rejected; month bounds computed server-side | validation tests |
| 19 | DB restore / migration mishap | Data loss | Alembic migrations tested up/down on CI DB; backups are an operator duty (documented) | – |
| 20 | Single financial admin unavailable | Blocked approvals | Multiple admins supported; super admin can add admins | – |
