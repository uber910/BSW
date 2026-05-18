"""bet_status -- add CANCELLED value

Phase 6 / D-03: extend PG bet_status ENUM with a fourth value 'cancelled'.
Reconciler (Plan 06-07) flips bets to status='cancelled' when line-provider
returns 404 for an event_id (event deleted / LP recreated).

autocommit_block (RESEARCH.md Pattern 4 / Pitfall 1): PostgreSQL forbids
ALTER TYPE ... ADD VALUE inside a transaction block; Alembic's async env
wraps every migration in a transaction. op.get_context().autocommit_block()
commits the surrounding transaction, runs the DDL with autocommit, and
restarts a fresh transaction for any subsequent statements.

Idempotency: IF NOT EXISTS clause (PG 9.6+) makes rerun safe.
Downgrade: PG does not support DROP VALUE without recreating the type;
intentionally no-op for the test-task scope.

Note on value casing: existing labels are upper-case ('PENDING','WON','LOST').
The new value 'cancelled' is lower-case per D-03 verbatim -- distinct visual
marker for the recovery status (cancelled != terminal outcome).

Revision ID: 0003_bet_status_cancelled
Revises: 0002_bets_settled_columns
Create Date: 2026-05-18
"""

from __future__ import annotations

from alembic import op

revision = "0003_bet_status_cancelled"
down_revision = "0002_bets_settled_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    pass
