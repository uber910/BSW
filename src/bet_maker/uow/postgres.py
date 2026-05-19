"""Concrete PostgresUnitOfWork over async_sessionmaker.begin().

Key properties:

1. Inherits from ``AbstractUnitOfWork``.
2. ``session`` is a property over a private ``_session: AsyncSession | None``
   that raises ``UnitOfWorkNotStartedError`` if accessed outside the
   ``async with`` context.
3. Write interactors call ``uow.session.add(bet)`` directly; reads live in
   ``src/bet_maker/selectors/get_pending_locked.py`` and
   ``src/bet_maker/selectors/get_pending_event_ids.py``.

The ``_cm: Any`` idiom is intentional -- ``async_sessionmaker.begin()``
returns ``_AsyncSessionContextManager`` (private SQLAlchemy type, not part
of the public API). ``Any`` is the documented mypy-strict-safe wrapper.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import Self

from bet_maker.uow.abstract import AbstractUnitOfWork


class UnitOfWorkNotStartedError(RuntimeError):
    """Raised when ``.session`` is accessed outside ``async with uow:`` context."""


class PostgresUnitOfWork(AbstractUnitOfWork):
    """Concrete UoW over ``async_sessionmaker.begin()``.

    SQLAlchemy auto-commits on clean ``__aexit__`` and auto-rolls-back on
    exception -- no public ``commit()`` / ``rollback()`` method is exposed.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._cm: Any = None
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise UnitOfWorkNotStartedError("UnitOfWork not started. Use `async with uow:`.")
        return self._session

    async def __aenter__(self) -> Self:
        self._cm = self._sessionmaker.begin()
        self._session = await self._cm.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        tb: object,
    ) -> None:
        assert self._cm is not None
        await self._cm.__aexit__(exc_type, exc, tb)
        self._cm = None
        self._session = None
