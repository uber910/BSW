"""Abstract UnitOfWork contract.

ABC (not Protocol): explicit inheritance gives mypy strict the leverage to
flag missing methods at concrete instantiation.

No public ``commit()`` / ``rollback()`` / ``execute()`` / ``fetch()`` --
the concrete class owns the transaction through ``__aenter__`` / ``__aexit__``.
Interactors write to ``uow.session`` directly via the SQLAlchemy 2.0 API
(``session.add``, ``session.execute(update(...))``, ``session.flush()``).
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
