SUPER_ADMIN = "super_admin"
FINANCIAL_ADMIN = "financial_admin"
EMPLOYEE = "employee"
AUDITOR = "auditor"
ROLES = {SUPER_ADMIN, FINANCIAL_ADMIN, EMPLOYEE, AUDITOR}
ADMIN_ROLES = {SUPER_ADMIN, FINANCIAL_ADMIN}

# Permission -> roles. "own" scoping for employees is enforced separately in services/routers.
PERMISSIONS: dict[str, set[str]] = {
    "household.create": {SUPER_ADMIN},
    "user.manage": {SUPER_ADMIN, FINANCIAL_ADMIN},
    "user.manage_privileged": {SUPER_ADMIN},
    "user.list": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
    "category.manage": {SUPER_ADMIN, FINANCIAL_ADMIN},
    "account.view_all": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
    "ledger.write": {SUPER_ADMIN, FINANCIAL_ADMIN},
    "ledger.read": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
    "expense.create_own": {EMPLOYEE, FINANCIAL_ADMIN, SUPER_ADMIN},
    "expense.create_for_others": {SUPER_ADMIN, FINANCIAL_ADMIN},
    "expense.read_all": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
    "expense.approve": {SUPER_ADMIN, FINANCIAL_ADMIN},
    "expense.post": {SUPER_ADMIN, FINANCIAL_ADMIN},
    "reconciliation.read_all": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
    "reconciliation.close": {SUPER_ADMIN, FINANCIAL_ADMIN},
    "dashboard.admin": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
    "export": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
    "audit.read": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
    "document.read_all": {SUPER_ADMIN, FINANCIAL_ADMIN, AUDITOR},
}


def can(role: str, perm: str) -> bool:
    return role in PERMISSIONS.get(perm, set())
