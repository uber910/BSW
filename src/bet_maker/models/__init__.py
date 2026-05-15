"""SQLAlchemy ORM models for bet_maker.

Re-exports Base so alembic/env.py can write `from bet_maker.models import Base`.
"""

from __future__ import annotations

from bet_maker.models.bet import Base, Bet

__all__ = ["Base", "Bet"]
