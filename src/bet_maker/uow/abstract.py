"""Abstract UnitOfWork contract.

Async mirror of ``~/Interexy/Metrikus/metrikus-app/api_common/unit_of_work/abstract.py``.
Decision D-01 (CONTEXT.md): ABC, not Protocol -- explicit inheritance gives
mypy strict the leverage to flag missing methods at concrete instantiation.

Decision D-03 (CONTEXT.md): no public ``commit()`` / ``rollback()`` /
``execute()`` / ``fetch()`` etc. -- the concrete class owns the transaction
through ``__aenter__`` / ``__aexit__``. Interactors write to ``uow.session``
directly via the SQLAlchemy 2.0 API (``session.add``, ``session.execute(update(...))``,
``session.flush()``). Verified by tests/bet_maker/test_uow.py::TestShape::
test_uow_has_no_public_commit_or_rollback.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Self


class AbstractUnitOfWork(ABC):
    """Async UnitOfWork contract. Concrete subclasses manage the transaction.

    Usage (interactor):

    .. code-block:: python

        async with uow:
            uow.session.add(entity)
            await uow.session.flush()
        # exit -> auto-commit (concrete impl)

    On exception inside the ``async with``: auto-rollback.
    """

    @property
    @abstractmethod
    def session(self) -> AsyncSession:
        """The active AsyncSession. Valid only inside ``async with uow:``."""

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        tb: object,
    ) -> None: ...
