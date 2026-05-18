"""bets settled columns -- add settled_at + settled_via

Phase 5 / D-13: observability columns for bet settlement.
settled_at: when the bet was settled (PG func.now() filled by UPDATE
statement inside settle_bets_for_event interactor -- D-14).
settled_via: 'consumer' (Phase 5) or 'reconciler' (Phase 6).

Revision ID: 0002_bets_settled_columns
Revises: 0001_bets_initial
Create Date: 2026-05-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_bets_settled_columns"
down_revision = "0001_bets_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bets",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bets",
        sa.Column("settled_via", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bets", "settled_via")
    op.drop_column("bets", "settled_at")
