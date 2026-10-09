import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String,
    Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(18, 4)


def uid() -> uuid.UUID:
    return uuid.uuid4()


def now() -> datetime:
    return datetime.now(timezone.utc)


def pk():
    return mapped_column(primary_key=True, default=uid)


class Household(Base):
    __tablename__ = "households"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    base_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = pk()
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id"), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(30))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("household_id", "code"),)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[uuid.UUID] = pk()
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    __table_args__ = (UniqueConstraint("household_id", "name"),)


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[uuid.UUID] = pk()
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    __table_args__ = (UniqueConstraint("household_id", "normalized_name"),)


class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"
    id: Mapped[uuid.UUID] = pk()
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id"))
    type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(500), default="")
    occurred_at: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    idempotency_key: Mapped[str] = mapped_column(String(200))
    payload_hash: Mapped[str] = mapped_column(String(64))
    expense_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expenses.id", use_alter=True, name="fk_txn_expense"))
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("financial_transactions.id"))
    reversed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("financial_transactions.id"))
    status: Mapped[str] = mapped_column(String(20), default="posted")
    reason: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lines: Mapped[list["JournalLine"]] = relationship(back_populates="transaction", order_by="JournalLine.id")
    __table_args__ = (
        UniqueConstraint("household_id", "idempotency_key", name="uq_txn_idem"),
        Index("ix_txn_household_date", "household_id", "occurred_at"),
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"
    id: Mapped[uuid.UUID] = pk()
    transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("financial_transactions.id"), index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    fx_rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal("1"))
    base_debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    base_credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    transaction: Mapped[FinancialTransaction] = relationship(back_populates="lines")
    __table_args__ = (
        CheckConstraint("(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)", name="ck_line_one_side"),
    )


class Expense(Base):
    __tablename__ = "expenses"
    id: Mapped[uuid.UUID] = pk()
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    client_ref: Mapped[str | None] = mapped_column(String(100))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"))
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    expense_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    payment_method: Mapped[str] = mapped_column(String(20), default="cash")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    notes: Mapped[str | None] = mapped_column(String(1000))
    rejection_reason: Mapped[str | None] = mapped_column(String(500))
    ocr_needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_txn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("financial_transactions.id", use_alter=True, name="fk_exp_txn"))
    refund_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expenses.id"))
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    documents: Mapped[list["Document"]] = relationship(back_populates="expense", order_by="Document.page_no")
    __table_args__ = (
        UniqueConstraint("user_id", "client_ref", name="uq_expense_client_ref"),
        Index("ix_expense_hh_status", "household_id", "status"),
        CheckConstraint("total IS NULL OR total > 0", name="ck_expense_total_positive"),
    )


class ExpenseStatusHistory(Base):
    __tablename__ = "expense_status_history"
    id: Mapped[uuid.UUID] = pk()
    expense_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expenses.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(String(500))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = pk()
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id"))
    expense_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expenses.id"), index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    page_no: Mapped[int] = mapped_column(Integer, default=1)
    filename: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(60))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    ocr_status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expense: Mapped[Expense] = relationship(back_populates="documents")
    __table_args__ = (UniqueConstraint("expense_id", "sha256", name="uq_doc_expense_sha"),)


class OcrResult(Base):
    __tablename__ = "ocr_results"
    id: Mapped[uuid.UUID] = pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    expense_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expenses.id"), index=True)
    provider: Mapped[str] = mapped_column(String(40))
    provider_real: Mapped[bool] = mapped_column(Boolean, default=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="v1")
    raw_text: Mapped[str | None] = mapped_column(Text)
    extraction: Mapped[dict | None] = mapped_column(JSONB)
    confidence: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OcrCorrection(Base):
    __tablename__ = "ocr_corrections"
    id: Mapped[uuid.UUID] = pk()
    expense_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expenses.id"), index=True)
    field: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(String(500))
    new_value: Mapped[str | None] = mapped_column(String(500))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Reconciliation(Base):
    __tablename__ = "reconciliations"
    id: Mapped[uuid.UUID] = pk()
    household_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("households.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="open")
    declared_count: Mapped[Decimal | None] = mapped_column(Money)
    expected_closing: Mapped[Decimal | None] = mapped_column(Money)
    difference: Mapped[Decimal | None] = mapped_column(Money)
    difference_txn_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("financial_transactions.id"))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (UniqueConstraint("user_id", "year", "month", name="uq_recon_period"),)


class ReconciliationEvent(Base):
    __tablename__ = "reconciliation_events"
    id: Mapped[uuid.UUID] = pk()
    reconciliation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reconciliations.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(500))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    household_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("households.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(60))
    details: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
