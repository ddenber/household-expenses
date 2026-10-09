# Business workflows

## Expense state machine
States: `draft, uploaded, processing, needs_review, submitted, approved, rejected, posted, reversed`.

| From | To | Who | Trigger |
|---|---|---|---|
| draft | uploaded | system | first document stored |
| draft | submitted | owner/admin | manual entry without receipt (flagged "missing receipt") |
| uploaded | processing | worker | OCR started |
| uploaded | needs_review | system | OCR disabled / skipped |
| processing | needs_review | worker | OCR finished **or failed** (document is kept) |
| needs_review | submitted | owner/admin | user confirmed fields (+ confirmation of low-confidence fields) |
| uploaded | submitted | owner/admin | user submits |
| submitted | approved | admin (not the owner) | approve |
| submitted | rejected | admin (not the owner) | reject with reason |
| submitted | needs_review | admin | return for correction |
| approved | rejected | admin | revoke before posting |
| rejected | draft | owner | reopen to fix |
| approved | posted | admin | post -> ledger transaction |
| posted | reversed | admin | reversal with reason |

Any other transition returns HTTP 409. Employees can never approve/reject their own expenses (also blocked if an admin is the owner).

## Flows
1. **Shto Fature**: employee taps the big button -> camera/file pick (multi-page) -> client compresses + fixes orientation -> expense draft is created with a `client_ref` (idempotent) -> pages upload with progress/retry; double taps are ignored -> API answers immediately; OCR runs async -> employee reviews suggested fields, confirms, submits. If offline, the capture is stored in IndexedDB and synced when online.
2. **Approval**: admin queue lists `submitted`; approve/reject; then "Posto" creates the ledger transaction (separate action).
3. **Admin-recorded expense**: admin creates an expense for an employee (e.g. EUR 100 cash), submits, approves, posts (admin != owner).
4. **Cash lifecycle**: funding -> ATM withdrawal (+ optional fee) -> purchases -> returns/transfers -> monthly reconciliation.
5. **Reconciliation**: employee declares counted cash; system shows expected vs declared and the separate categories; admin closes (optionally posts the difference to suspense); reopening needs a reason and is audited.
6. **Refund**: created from a posted expense, links to original, posted as its own transaction.
