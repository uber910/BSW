from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from typing_extensions import Self

from bet_maker.repositories.bets import BetRepository


class AsyncUnitOfWork:
    """Async UoW over `async_sessionmaker.begin()`.

    D-17 (RESEARCH §Pattern 2): __aenter__ enters `sessionmaker.begin()`
    context — SQLAlchemy auto-commits on clean __aexit__ and auto-rollback
    on exception. No manual `session.commit()` / `session.rollback()` calls
    anywhere in bet_maker code — UoW owns the transaction.

    Usage (Plan 03-07 interactor):
        async with AsyncUnitOfWork(sessionmaker) as uow:
            uow.bets.add(bet)
            await uow.session.flush()
            await uow.session.refresh(bet)
            # exit -> commit

    _cm is typed as Any because `async_sessionmaker.begin()` returns
    `_AsyncSessionContextManager[AsyncSession]` — a private SQLAlchemy type
    that is not exported from the public API surface. Using Any is the
    documented idiom for wrapping private async context managers in strict mypy
    mode (RESEARCH §Pattern 2 note).
    """

    bets: BetRepository
    session: AsyncSession

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._cm: Any = None

    async def __aenter__(self) -> Self:
        self._cm = self._sessionmaker.begin()
        self.session = await self._cm.__aenter__()
        self.bets = BetRepository(self.session)
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
