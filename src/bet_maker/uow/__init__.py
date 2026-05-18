"""bet_maker.uow -- UnitOfWork package (Phase 9, REFACTOR-03).

Public surface:

* ``AbstractUnitOfWork`` -- ABC interactors and tests depend on.
* ``PostgresUnitOfWork`` -- concrete implementation; instantiated only in
  the FastAPI DI provider (``facades/deps.py``) and the two non-DI
  construction sites (``api/messaging.py``, ``jobs/reconciler.py``).
* ``UnitOfWorkNotStartedError`` -- raised by ``PostgresUnitOfWork.session``
  if accessed outside ``async with uow:``.
"""

from __future__ import annotations

from bet_maker.uow.abstract import AbstractUnitOfWork
from bet_maker.uow.postgres import PostgresUnitOfWork, UnitOfWorkNotStartedError

__all__ = ["AbstractUnitOfWork", "PostgresUnitOfWork", "UnitOfWorkNotStartedError"]
