"""bet_status -- rename 'cancelled' to 'CANCELLED'

Make all BetStatus ENUM labels consistent (upper-case).

Revision ID: 0004_bet_status_cancel_upper
Revises: 0003_bet_status_cancelled
Create Date: 2026-05-18
"""

from __future__ import annotations

from alembic import op

revision = "0004_bet_status_cancel_upper"
down_revision = "0003_bet_status_cancelled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE bet_status RENAME VALUE 'cancelled' TO 'CANCELLED'")


def downgrade() -> None:
    op.execute("ALTER TYPE bet_status RENAME VALUE 'CANCELLED' TO 'cancelled'")
