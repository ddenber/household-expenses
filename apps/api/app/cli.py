"""CLI: bootstrap-admin (real), seed-demo (demo only, refused in production), worker."""
import argparse
import os
import sys
from datetime import date, timedelta

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import Household, User
from .services import accounts as acc
from .services.security import hash_password


def bootstrap_admin(name, email, password, household):
    db = SessionLocal()
    if db.scalar(select(User).where(User.email == email.lower())):
        print("user exists")
        return
    h = Household(name=household)
    db.add(h)
    db.flush()
    acc.seed_default_categories(db, h.id)
    acc.create_bank_account(db, h.id, "Llogaria kryesore bankare")
    db.add(User(household_id=h.id, email=email.lower(), name=name, role="super_admin", password_hash=hash_password(password)))
    db.commit()
    print("created household and super admin")


def seed_demo():
    if get_settings().app_env == "production":
        print("refusing to seed demo data in production")
        sys.exit(1)
    from .services import operations as ops
    db = SessionLocal()
    if db.scalar(select(Household).where(Household.is_demo)):
        print("demo exists")
        return
    h = Household(name="DEMO - te dhena demonstrative", is_demo=True)
    db.add(h)
    db.flush()
    acc.seed_default_categories(db, h.id)
    bank = acc.create_bank_account(db, h.id, "DEMO Llogaria bankare")
    pw = os.environ.get("DEMO_PASSWORD", "demo-password-123")
    admin = User(household_id=h.id, email="admin@demo.local", name="Admin Demo", role="financial_admin", password_hash=hash_password(pw))
    emps = [User(household_id=h.id, email=f"punonjes{i}@demo.local", name=f"Punonjes Demo {i}", role="employee",
                 password_hash=hash_password(pw)) for i in (1, 2)]
    db.add_all([admin, *emps])
    db.flush()
    for e in emps:
        acc.wallet_for(db, h.id, e.id)
        acc.payable_for(db, h.id, e.id)
    d = date.today() - timedelta(days=5)
    ops.funding(db, admin, key="demo-fund", day=d, amount="2000", bank_id=bank.id)
    ops.atm_withdrawal(db, admin, key="demo-atm1", day=d, amount="500", bank_id=bank.id, user_id=emps[0].id)
    db.commit()
    print(f"demo seeded: admin@demo.local / punonjes1@demo.local (password from DEMO_PASSWORD or default)")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap-admin")
    b.add_argument("--name", required=True)
    b.add_argument("--email", required=True)
    b.add_argument("--household", default="Shtepia ime")
    b.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD"))
    sub.add_parser("seed-demo")
    a = p.parse_args()
    if a.cmd == "bootstrap-admin":
        if not a.password or len(a.password) < 10:
            sys.exit("password (>=10 chars) required via --password or ADMIN_PASSWORD")
        bootstrap_admin(a.name, a.email, a.password, a.household)
    else:
        seed_demo()


if __name__ == "__main__":
    main()
