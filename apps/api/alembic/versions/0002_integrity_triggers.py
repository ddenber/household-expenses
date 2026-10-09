"""immutability, append-only and balance triggers

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APPEND_ONLY = ["audit_log", "expense_status_history", "ocr_corrections", "reconciliation_events"]


def upgrade() -> None:
    op.execute("""
    CREATE FUNCTION hem_forbid_change() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'table % is append-only/immutable', TG_TABLE_NAME USING ERRCODE = '23000';
    END; $$ LANGUAGE plpgsql;
    """)
    for t in APPEND_ONLY + ["journal_lines"]:
        op.execute(
            f"CREATE TRIGGER trg_{t}_immutable BEFORE UPDATE OR DELETE ON {t} "
            "FOR EACH ROW EXECUTE FUNCTION hem_forbid_change();"
        )
    op.execute("""
    CREATE FUNCTION hem_txn_guard() RETURNS trigger AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'financial_transactions cannot be deleted' USING ERRCODE = '23000';
      END IF;
      IF OLD.status = 'posted' AND NEW.status = 'reversed' AND NEW.reversed_by_id IS NOT NULL
         AND OLD.id = NEW.id AND OLD.household_id = NEW.household_id AND OLD.type = NEW.type
         AND OLD.occurred_at = NEW.occurred_at AND OLD.idempotency_key = NEW.idempotency_key
         AND OLD.payload_hash = NEW.payload_hash AND OLD.currency = NEW.currency
         AND OLD.description = NEW.description
         AND OLD.reverses_id IS NOT DISTINCT FROM NEW.reverses_id
         AND OLD.expense_id IS NOT DISTINCT FROM NEW.expense_id
         AND OLD.reversed_by_id IS NULL THEN
        RETURN NEW;
      END IF;
      RAISE EXCEPTION 'posted financial transactions are immutable (reverse instead)' USING ERRCODE = '23000';
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER trg_txn_guard BEFORE UPDATE OR DELETE ON financial_transactions
      FOR EACH ROW EXECUTE FUNCTION hem_txn_guard();
    """)
    op.execute("""
    CREATE FUNCTION hem_check_balanced() RETURNS trigger AS $$
    DECLARE d numeric; c numeric; n int;
    BEGIN
      SELECT COALESCE(SUM(base_debit),0), COALESCE(SUM(base_credit),0), COUNT(*)
        INTO d, c, n FROM journal_lines WHERE transaction_id = NEW.transaction_id;
      IF n < 2 OR d <> c THEN
        RAISE EXCEPTION 'unbalanced journal for transaction % (debit %, credit %, lines %)', NEW.transaction_id, d, c, n
          USING ERRCODE = '23514';
      END IF;
      RETURN NULL;
    END; $$ LANGUAGE plpgsql;
    CREATE CONSTRAINT TRIGGER trg_journal_balanced AFTER INSERT ON journal_lines
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION hem_check_balanced();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_journal_balanced ON journal_lines; DROP FUNCTION IF EXISTS hem_check_balanced();")
    op.execute("DROP TRIGGER IF EXISTS trg_txn_guard ON financial_transactions; DROP FUNCTION IF EXISTS hem_txn_guard();")
    for t in APPEND_ONLY + ["journal_lines"]:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{t}_immutable ON {t};")
    op.execute("DROP FUNCTION IF EXISTS hem_forbid_change();")
