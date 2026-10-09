# Role / permission matrix

Enforced server-side in `apps/api/app/rbac.py` + object-level checks in services. The UI only hides controls; it is never the control.

| Capability | Super Admin | Financial Admin | Employee | Auditor |
|---|---|---|---|---|
| Create households / first admin | yes | – | – | – |
| Create employees | yes | yes | – | – |
| Create privileged users (admin/auditor) | yes | – | – | – |
| (De)activate users | yes | employees only | – | – |
| Manage categories / bank accounts | yes | yes | – | – |
| Funding, ATM, cash return, transfer, reimbursement, opening balances | yes | yes | – | – |
| Reverse ledger transactions | yes | yes | – | – |
| View ledger, accounts, all balances | yes | yes | own wallet only | read-only |
| Create expense / upload receipt | yes (own or for others) | yes (own or for others) | own only | – |
| Edit / submit expense | own or any (while editable) | own or any (while editable) | own only (while editable) | – |
| Approve / reject / return expense | yes, **never own** | yes, **never own** | – | – |
| Post / reverse / refund expense | yes (not own) | yes (not own) | – | – |
| View expenses & documents | all in household | all in household | own only | all (read-only) |
| Declare cash count | any employee | any employee | own only | – |
| Close / reopen reconciliation period | yes | yes | – | – |
| View reconciliation / statement PDF | all | all | own only | all |
| Admin dashboard, analytics | yes | yes | – | yes |
| Exports (CSV/XLSX) | yes | yes | – | yes |
| Audit log | yes | yes | – | yes |

Notes
- All data is scoped to the caller's household. Cross-household and cross-employee lookups return **404**.
- "Never own": approval/posting of an expense whose `user_id` equals the actor is rejected even for admins.
- Auditor sees documents (read) but every access is audit-logged.
