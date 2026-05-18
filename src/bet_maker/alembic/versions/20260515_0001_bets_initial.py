"""bets initial schema -- bet_status ENUM + bets table

Phase 3 / D-09: PostgreSQL native ENUM bet_status('PENDING','WON','LOST')
+ bets table with Numeric(12,2) amount, server_default=func.now() timestamps.

Idempotency (success criterion #5):
- ENUM.create(bind, checkfirst=True) -- DO NOTHING IF EXISTS (Pitfall 2 mitigation)
- sa.Enum(..., create_type=False) inside create_table -- Alembic must NOT
  re-create the type that .create() already handled.

Revision ID: 0001_bets_initial
Revises: None
Create Date: 2026-05-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_bets_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bet_status = postgresql.ENUM(
        "PENDING",
        "WON",
        "LOST",
        name="bet_status",
        create_type=False,
    )
    bet_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "amount",
            sa.Numeric(12, 2),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "WON",
                "LOST",
                name="bet_status",
                create_type=False,
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("bets")
    bet_status = postgresql.ENUM(
        "PENDING",
        "WON",
        "LOST",
        name="bet_status",
        create_type=False,
    )
    bet_status.drop(op.get_bind(), checkfirst=True)
