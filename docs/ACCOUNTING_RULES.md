# Accounting rules

Lightweight double entry. Debit increases assets/expenses; credit increases liabilities/equity. Balance of any account = `SUM(debit) - SUM(credit)` (for liabilities the UI shows the negation).

## Accounts
Bank (asset) · Employee Cash Wallet (asset, one per employee) · Expense account per category (expense) · Bank Fees (expense) · Reimbursement Payable (liability, one per employee) · Opening Equity (equity) · Owner Funding (equity) · **Suspense / Unexplained difference** (suspense).

## Posting table

| Event | Debit | Credit | Expense? |
|---|---|---|---|
| Opening balance (bank) | Bank | Opening Equity | no |
| Opening balance (wallet) | Wallet | Opening Equity | no |
| Funding transfer (owner -> bank) | Bank | Owner Funding (equity) | no |
| ATM withdrawal | Employee Wallet | Bank | no |
| ATM fee (separate txn) | Bank Fees | Bank | **yes** (bank-fee expense) |
| Cash return (employee -> bank) | Bank | Employee Wallet | no |
| Employee-to-employee transfer | Wallet B | Wallet A | no |
| Cash expense | Category expense | Employee Wallet | yes |
| Direct card purchase | Category expense | Bank | yes (wallet untouched) |
| Bank-transfer purchase | Category expense | Bank | yes (wallet untouched) |
| Personal-funds purchase | Category expense | Reimbursement Payable (employee) | yes (wallet untouched) |
| Reimbursement paid | Reimbursement Payable | Bank | no |
| Refund (cash) | Employee Wallet | Category expense | reduces expense |
| Refund (card/transfer) | Bank | Category expense | reduces expense |
| Refund (personal funds) | Reimbursement Payable | Category expense | reduces expense |
| Cash count difference (shortage) | Suspense | Employee Wallet | no |
| Cash count difference (surplus) | Employee Wallet | Suspense | no |
| Reversal | mirror of original | mirror of original | undoes original |

## Invariants (all enforced in code; the first three also in DB)
1. Every transaction has >= 2 lines and `sum(debit_base) == sum(credit_base)`.
2. Posted journal lines are immutable. Corrections are **reversals** (a new transaction with swapped sides, `reverses_id` set, original marked `reversed`). A transaction can be reversed once.
2b. Assets (bank, wallets) can never go negative: a posting that would overdraw is rejected with `insufficient_funds` (checked under row locks).
3. Posting is atomic (one DB transaction) and idempotent: `(household_id, idempotency_key)` unique. Same key + same payload hash -> returns the existing transaction (`replayed=true`); same key + different payload -> 409. Concurrent duplicates are resolved by the unique constraint + row locks.
4. ATM withdrawals, funding, cash returns and transfers never touch an expense account.
5. Only `approved` expenses can be posted; `rejected`, `submitted`, etc. never create ledger lines. A posted expense has exactly one live posting.
6. Refund total for an original expense can never exceed the original total; refund must have same payment method and links to the original.
7. Posting/reversing into a month where an affected employee's reconciliation is **closed** is rejected until the period is reopened (with reason, audited).
8. Only EUR is accepted in Phase 1 (`fx_rate = 1`); schema keeps currency + rate for later.
9. Rounding: amounts have max 2 decimals at input (Decimal, `ROUND_HALF_EVEN` never applied silently — values with >2 decimals are rejected).

## Reconciliation formula (per employee, per month)
`expected closing = opening + withdrawals + received transfers + other sources + refunds - approved(posted) cash expenses - returns to bank - transfers out - other outflows`

Computed from wallet journal lines grouped by transaction type (reversals net out automatically). `opening` = wallet balance as of start of month (so carry-forward is automatic and derived). `difference = declared physical count - expected closing`. Reported separately and never mixed into expected: **pending** (submitted / needs review / processing / uploaded), **approved but not posted**, **rejected**, **missing receipts**, **suspense** balance. On closing the admin may post the difference to Suspense so the wallet equals the physical count.
