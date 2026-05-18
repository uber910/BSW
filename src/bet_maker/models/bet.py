"""SQLAlchemy 2.0 typed Bet model + DeclarativeBase registry.

D-09 (Phase 3 CONTEXT.md): bets table schema with PG native ENUM bet_status,
Numeric(12,2) amount, UUID primary key (Python-side uuid.uuid4 default),
server_default=func.now() timestamps.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bet_maker.schemas.bets import BetStatus


class Base(DeclarativeBase):
    """Declarative base for all bet_maker ORM models.

    Single registry — Alembic env.py reads `Base.metadata` for autogenerate
    and for runtime SELECT/INSERT shape inference. P5 may add new tables
    (e.g., outbox or settle audit) to this same Base.
    """


class Bet(Base):
    """Bet entity. TZ page 3: event_id + amount + status.

    D-09 (Phase 3 CONTEXT.md):
    - id: UUID PK, Python-generated via uuid.uuid4 (mirrors event_id pattern from P2)
    - event_id: UUID, NO FK (events live in line-provider, separate service)
    - amount: Numeric(12, 2) -- Pitfall A4/A5 mitigation (Decimal precision)
    - status: PG native ENUM bet_status('PENDING','WON','LOST'), default PENDING
    - created_at: server_default=func.now() -- PG fills at INSERT time
    - updated_at: server_default + onupdate -- DB-portable + ORM-aware

    D-01: NO coefficient column -- coefficient is an event attribute, lives
    in line-provider. TZ page 3 POST /bet body = event_id + amount.

    D-13 / D-14 (Phase 5):
    - settled_at: Mapped[datetime | None] -- server-filled by PG func.now() in the
      settle UPDATE statement; NULL while bet is PENDING (D-13/D-14).
    - settled_via: Mapped[str | None] -- 'consumer' (Phase 5) or 'reconciler'
      (Phase 6); NULL while PENDING.
    """

    __tablename__ = "bets"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    status: Mapped[BetStatus] = mapped_column(
        SqlEnum(
            BetStatus,
            name="bet_status",
            create_type=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=BetStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    settled_via: Mapped[str | None] = mapped_column(
        sa.Text(),
        nullable=True,
    )
