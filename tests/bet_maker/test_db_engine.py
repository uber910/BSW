"""Wave 0 stub — implemented in plan 03-05.

BM-02 / D-15 / D-16: create_engine_and_sessionmaker returns engine + sessionmaker
with locked params (pool_size=10, max_overflow=20, pool_pre_ping=True,
pool_recycle=1800, expire_on_commit=False).
BM-08 / D-26 / D-29: ping_postgres returns True on healthy PG, False on
SQLAlchemyError; never raises.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(reason="Wave 0 stub: implemented in plan 03-05")
