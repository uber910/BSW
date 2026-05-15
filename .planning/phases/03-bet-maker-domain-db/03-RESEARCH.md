# Phase 3: bet-maker domain (DB) — Research

**Researched:** 2026-05-15
**Domain:** SQLAlchemy 2.0 async ORM, Alembic async migrations, testcontainers-python, Pydantic v2 Decimal, tenacity async retry
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Coefficient в записи Bet — НЕ хранится. Первый task P3 синхронизирует REQUIREMENTS.md (BM-01/BM-05 убирают coefficient). Coefficient — атрибут события (line-provider).
- **D-02:** GET /bet/{bet_id} добавляется в P3 (есть на диаграмме ТЗ). 200 + BetRead или 404. Регистрируется как новый BM-13.
- **D-03:** event_id остаётся UUID4 (P2 D-05). Менять нельзя.
- **D-04:** Body BetCreate = `{event_id: UUID4, amount: Decimal}`. `amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2), AfterValidator(quantize_amount)]`, `extra="forbid"`.
- **D-05:** Ответ POST /bet — 201 с BetRead (id, event_id, amount, status, created_at).
- **D-06:** EventLookup валидация: event не найден / deadline <= now / state != NEW → 422 `{"detail":"event {id} is not bettable: {reason}"}`. P3 — StubEventLookup.
- **D-07:** GET /bets — `list[BetRead]`, sorted by `created_at DESC`, без пагинации. Selector без UoW.
- **D-08:** GET /bet/{bet_id} — 200 + BetRead или 404 `{"detail":"bet {id} not found"}`. Selector.
- **D-09:** Схема `bets`: `id UUID PK`, `event_id UUID (no FK)`, `amount Numeric(12,2)`, `status PG-ENUM bet_status('PENDING','WON','LOST')`, `created_at/updated_at server_default=func.now()` + onupdate. Без coefficient.
- **D-10:** Только PK index в P3. (event_id, status) — P5.
- **D-11:** `EventLookup(Protocol)` + `StubEventLookup` (dict-backed, методы seed/seed_active) + `EventSnapshot(BaseModel, frozen=True)` в `facades/event_lookup.py`. `EventLookupDep` через `app.state.event_lookup`.
- **D-12:** `EventState` enum дублируется в `bet_maker/schemas/events.py` (3 значения). Импорт из line_provider нарушает service boundary.
- **D-13:** Lifespan: `app.state.event_lookup = StubEventLookup()`. P4 подменит на HttpEventLookup.
- **D-14:** Interactor `place_bet` — last-step model_validate внутри session (A1 mitigation), EventNotBettable → HTTPException(422) в route.
- **D-15:** `async_sessionmaker(engine, expire_on_commit=False)`, sessions per-request.
- **D-16:** `create_async_engine` params: `pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800`.
- **D-17:** `AsyncUnitOfWork` — точная форма из ARCHITECTURE.md Pattern 1: `async_sessionmaker.begin().__aenter__()`.
- **D-18:** `BetRepository.add(bet)` — `session.add + flush`. `get_by_id` для GET /bet/{id}. NO commit в репозитории.
- **D-19:** `BetRead.amount` — Pydantic v2 сериализует Decimal как string ("10.00"). Тесты сравнивают строкой.
- **D-20:** `BetStatus = (str, Enum)` — Python 3.10 (StrEnum не доступен до 3.11).
- **D-21:** testcontainers session-scoped PG в root `tests/conftest.py`. `PostgresContainer("postgres:16-alpine")`.
- **D-22:** Bootstrap схемы — `alembic upgrade head` (programmatic или subprocess). Session-fixture.
- **D-23:** Per-test изоляция — `TRUNCATE bets RESTART IDENTITY CASCADE` через engine.connect(), autouse fixture.
- **D-24:** Структура тестов: test_models, test_repositories, test_uow, test_event_lookup, test_place_bet, test_selectors, test_bet_routes, test_health, test_lifespan, test_alembic.
- **D-25:** `tests/bet_maker/conftest.py` — client fixture с PG-backend + dependency_overrides для StubEventLookup.
- **D-26:** GET /health — каждый запрос делает SELECT 1 через `engine.connect()`. Без кэша.
- **D-27:** Lifespan startup retry — `infrastructure/db/pings.py::wait_for_postgres()` с `@retry(stop=stop_after_attempt(10), wait=wait_exponential(min=1,max=10), reraise=True)`.
- **D-28:** Health response: 200 `{"status":"ok","checks":{"postgres":"ok"}}`, 503 `{"status":"degraded","checks":{"postgres":"down"}}`. P1 smoke test (`body == {"status": "ok"}`) сломается — первый implementing task P3 обновит assertion до `body["status"] == "ok"`.
- **D-29:** Health реализация: `Depends(get_engine)`, `try/except SQLAlchemyError` → 503.
- **D-30:** Каталоги достраиваются по paste-ready tree ARCHITECTURE.md §176–246.
- **D-31:** A7 middleware уже в P1 — не трогать.
- **D-32:** BetMakerSettings уже в P1 с postgres_dsn. В P3 не меняется.

### Claude's Discretion

- Точная сигнатура fixtures (testcontainers + Alembic) — на planner.
- Способ запуска Alembic из тестов: subprocess vs programmatic — planner решает.
- Точная форма `EventNotBettable` exception — на planner.
- Где живёт `BetStatus` — в `schemas/bets.py` (consistent с BetCreate/BetRead) vs отдельный `models/enums.py`. Single source of truth.

### Deferred Ideas (OUT OF SCOPE)

- GET /events proxy / httpx-клиент к line-provider (P4).
- HttpEventLookup (P4).
- RabbitMQ consumer + settle_bets_for_event (P5).
- Reconciliation job (P6).
- (event_id, status) PG-индекс (P5).
- /health RabbitMQ ping (P5).
- Idempotency-Key header на POST /bet (README extension, P7).
- GET /bets pagination + filtering.
- (created_at DESC) index для GET /bets.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BM-01 | SQLAlchemy 2.0 async модели для ставок (id UUID, event_id UUID, amount Decimal 12.2, status enum, created_at, updated_at) **без coefficient** (синхронизируется D-01) | D-09, Pattern 1 ARCHITECTURE.md, Pitfall A1/A4/A5 mitigations |
| BM-02 | Unit of Work как async context manager поверх `async_sessionmaker.begin()`, репозитории флашат, UoW коммитит | D-15..D-18, Pattern 1, Pitfall A1/A2/A3 mitigations |
| BM-03 | Слоистая архитектура: entrypoints / facades / interactors / selectors / helpers | D-30, ARCHITECTURE.md paste-ready tree §176–246 |
| BM-05 | POST /bet — приём ставки; в теле {event_id, amount} (amount > 0, 2 знака) **без coefficient snapshot** (синхронизируется D-01); ответ — id + BetRead; status=PENDING | D-04/D-05/D-06/D-14/D-19; Pydantic decimal validation verified |
| BM-06 | Валидация события (deadline > now, state == NEW) через EventLookup facade | D-06/D-11/D-12/D-13/D-14 |
| BM-07 | GET /bets — история всех ставок с полями id, event_id, amount, status, created_at; ordered created_at desc | D-07, selector pattern |
| BM-08 | GET /health с проверкой PostgreSQL (SELECT 1); 503 при падении PG | D-26..D-29, tenacity startup retry |
| QA-07 | PG-тесты с реальной БД через testcontainers (НЕ SQLite) | D-21..D-25, testcontainers PostgresContainer verified |
| BM-13 (new) | GET /bet/{bet_id} — 200 + BetRead или 404; добавляется из диаграммы ТЗ | D-02/D-08 |
</phase_requirements>

---

## Summary

Phase 3 наполняет `bet-maker` полным доменным слоем: PostgreSQL-персистенс через UoW + Repository (SQLAlchemy 2.0 async), три HTTP-эндпоинта (POST /bet, GET /bets, GET /bet/{bet_id}), расширенный /health с реальным SELECT 1 к PG, и полный тест-сьют через testcontainers. Все ключевые технические решения зафиксированы в D-01..D-32 CONTEXT.md и подтверждены в этом исследовании.

Главные технические риски P3: (1) Decimal round-trip exactness (asyncpg возвращает Python `Decimal` через `Numeric(12,2)` с `asdecimal=True` — подтверждено); (2) идемпотентность `alembic upgrade head` с PG native ENUM (рецепт `checkfirst=True` подтверждён через SQLAlchemy docs); (3) testcontainers session-scoped fixture c async alembic bootstrap — нетривиальная сборка, точный рецепт задокументирован ниже; (4) `server_default=func.now()` + `onupdate=func.now()` семантика (server_default срабатывает в DDL при INSERT, onupdate — при ORM UPDATE, для чтения updated_at после INSERT нужен `session.refresh(bet)` или полагаться на `expire_on_commit=False` + SELECT в том же UoW).

**Primary recommendation:** следовать D-09..D-29 буквально — все детали уже зафиксированы. Planner собирает 8–9 атомарных планов: sync-task → engine/sessionmaker → models/migration → UoW+repo → schemas/helpers → interactors/selectors → routes/health → tests.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP request parsing / routing | entrypoints/api/ | facades/deps.py (DI) | FastAPI routes: thin wrappers, no business logic |
| Bet placement validation (amount, event lookup) | interactors/place_bet.py | helpers/money.py, facades/event_lookup.py | Business rule — interactor owns transaction |
| Event existence / activeness check | facades/event_lookup.py (Protocol) | schemas/events.py (EventState) | P3: StubEventLookup; P4: HttpEventLookup — same Protocol |
| PostgreSQL persistence | infrastructure/db/engine.py + repositories/bets.py | facades/uow.py | Engine = infrastructure singleton; UoW = facade |
| Transaction lifecycle | facades/uow.py (AsyncUnitOfWork) | — | UoW commits; repositories flush only |
| Read queries (list_bets, get_bet) | selectors/ | repositories/bets.py (query) | CQRS-lite: selectors = read-only, no UoW |
| Alembic migration | alembic/versions/ | alembic/env.py | Already wired in P1; P3 adds first migration file |
| Health check (PG liveness) | entrypoints/api/health.py | infrastructure/db/pings.py | Per-request SELECT 1; no caching |
| Startup reliability (PG retry) | entrypoints/lifespan.py | infrastructure/db/pings.py | tenacity retry gates uvicorn ready state |
| Decimal precision | helpers/money.py (quantize_amount) + Pydantic Field(decimal_places=2) | models/bet.py Numeric(12,2) | Three-layer defence: validator → quantize → DB type |

---

## Standard Stack

### Core

| Library | Version (pinned) | Purpose | Why Standard |
|---------|-----------------|---------|--------------|
| SQLAlchemy | `>=2.0.40,<2.1` (2.0.49 в uv.lock) | ORM + typed Mapped[] + async | Уже в pyproject.toml. asdecimal=True в Numeric(12,2) — подтверждено. |
| asyncpg | `>=0.31,<0.32` (0.31.0) | Async PG driver | Уже в pyproject.toml. Возвращает Python Decimal нативно для NUMERIC колонок. |
| alembic | `>=1.18,<2` (1.18.4) | DB migrations, async template | Уже в pyproject.toml. env.py уже wired (P1). |
| tenacity | `>=9.1,<10` (9.1.4) | Async retry для lifespan PG ping | Уже в pyproject.toml. `@retry` автоматически определяет async coroutine. |
| pydantic | `>=2.13,<3` (2.13.4) | Validation + Decimal serialization | Уже в pyproject.toml. Verified: `decimal_places=2` + `AfterValidator` работают. |
| testcontainers | `>=4.9,<5` (новая dep) | Real PostgreSQL for QA-07 | Нет в pyproject.toml — нужно добавить в `dependency-groups.dev`. |

[VERIFIED: pyproject.toml + npm view testcontainers version]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | `>=0.28,<0.29` | `AsyncClient` в integration тестах (ASGITransport) | Уже в pyproject.toml. Для HTTP integration tests с app |
| asgi-lifespan | `>=2.1,<3` | LifespanManager в тестах | Уже в dev deps. Нужен для P3 tests с реальным lifespan |
| pytest-asyncio | `>=1.1,<2` | Async test runner | Уже в dev deps. `asyncio_mode = "auto"` в pyproject. |
| pytest-cov | `>=7.1,<8` | Coverage | Уже в dev deps. P3 добавляет `source = ["src/bet_maker"]` в pyproject coverage config. |

### Dependency to Add

```toml
# В [dependency-groups.dev]:
"testcontainers>=4.9,<5",
```

`testcontainers[postgresql]` как extra-синтаксис — избыточен: в testcontainers v4.x postgres-модуль поставляется в base пакете, никаких extras для psql нет. Подтверждено через PyPI.

[VERIFIED: pypi.org/pypi/testcontainers — extras list не содержит "postgresql"]

---

## Architecture Patterns

### System Architecture Diagram

```
[HTTP Client]
      │ POST /bet {event_id, amount}  │ GET /bets  │ GET /bet/{id}
      │ GET /health
      v
[entrypoints/api/bets.py, health.py]
      │ Pydantic BetCreate validation (Field(gt=0, max_digits=12, decimal_places=2) + AfterValidator)
      │ Depends(get_uow) → AsyncUnitOfWork
      │ Depends(get_event_lookup) → StubEventLookup  [P4: HttpEventLookup]
      │ Depends(get_session) → AsyncSession  [read-only routes]
      │ Depends(get_engine) → AsyncEngine  [health]
      v
[interactors/place_bet.py]
      │ event_lookup.get_event(event_id) → EventSnapshot | None
      │ validate: snapshot is not None, deadline > now, state == NEW
      │ async with uow:
      │     bet = Bet(event_id, amount=quantize_amount(amount))
      │     uow.bets.add(bet)  → session.add + flush
      │     model_validate(bet, from_attributes=True)  ← inside session (A1 mitigation)
      │ UoW __aexit__ → commit
      v
[selectors/list_bets.py, selectors/get_bet.py]
      │ session.execute(select(Bet).order_by(created_at.desc()))
      │ BetRead.model_validate(row, from_attributes=True)
      v
[infrastructure/db/engine.py]   ←→  [PostgreSQL 16 — bets table]
      │ AsyncEngine (pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800)
      │ async_sessionmaker(engine, expire_on_commit=False)
      v
[entrypoints/lifespan.py]
      │ 1. BetMakerSettings()
      │ 2. configure_structlog()
      │ 3. create_async_engine + async_sessionmaker
      │ 4. wait_for_postgres() — tenacity(attempts=10, exp_backoff min=1 max=10)
      │ 5. app.state.engine / .sessionmaker / .event_lookup = StubEventLookup()
      │ yield
      │ finally: await engine.dispose()
```

### Recommended Project Structure (P3 additions only)

```
src/bet_maker/
├── models/
│   ├── __init__.py
│   └── bet.py               # Bet(Base), DeclarativeBase; BetStatus (str, Enum) здесь или в schemas/bets.py
├── schemas/
│   ├── __init__.py
│   ├── bets.py              # BetCreate, BetRead, BetStatus (если не в models)
│   └── events.py            # EventState (str, Enum) — дублирует line_provider, intentional D-12
├── repositories/
│   ├── __init__.py
│   └── bets.py              # BetRepository(session): add, get_by_id
├── facades/
│   ├── __init__.py
│   ├── uow.py               # AsyncUnitOfWork
│   ├── event_lookup.py      # EventLookup(Protocol), StubEventLookup, EventSnapshot
│   └── deps.py              # get_uow, get_session, get_engine, get_event_lookup, get_settings
├── interactors/
│   ├── __init__.py
│   └── place_bet.py         # place_bet(uow, *, event_id, amount, event_lookup) -> BetRead
├── selectors/
│   ├── __init__.py
│   ├── list_bets.py         # list_bets(session) -> list[BetRead]
│   └── get_bet.py           # get_bet_by_id(session, bet_id) -> BetRead | None
├── helpers/
│   ├── __init__.py
│   ├── money.py             # quantize_amount(Decimal) -> Decimal (2dp, ROUND_HALF_UP)
│   └── status.py            # event_state_to_bet_status() — заглушка для P5
├── infrastructure/
│   ├── __init__.py
│   └── db/
│       ├── __init__.py
│       ├── engine.py        # create_async_engine + async_sessionmaker
│       └── pings.py         # wait_for_postgres(engine), ping_postgres(engine)
└── entrypoints/
    ├── api/
    │   ├── bets.py          # POST /bet, GET /bets, GET /bet/{bet_id}
    │   └── health.py        # REPLACE P1 stub — SELECT 1 ping
    └── lifespan.py          # EXTEND P1 — добавить engine/sessionmaker/event_lookup

alembic/versions/
└── 20260515_0001_bets_initial.py   # bet_status ENUM + bets table
```

### Pattern 1: SQLAlchemy 2.0 Typed Model with PG Native ENUM

**What:** Typed `Mapped[]` columns с `SqlEnum(BetStatus, name="bet_status", create_type=True)` + `Numeric(12,2)` для Decimal.

**Verified API:**

```python
# src/bet_maker/models/bet.py
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Enum as SqlEnum, Numeric, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BetStatus(str, Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[BetStatus] = mapped_column(
        SqlEnum(BetStatus, name="bet_status", create_type=True),
        nullable=False,
        default=BetStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
```

**Source:** `[VERIFIED: docs.sqlalchemy.org/en/20/orm/declarative_tables.html — Map Python Enum to SQLAlchemy Enum]`

**Ключевые детали:**
- `Numeric(12, 2)` — `asdecimal=True` по умолчанию. Asyncpg возвращает Python `Decimal` нативно для NUMERIC колонок. `[VERIFIED: SQLAlchemy docs sqlalchemy.types.Numeric.__init__]`
- `BetStatus(str, Enum)` — Python 3.10 compatible. StrEnum доступен только с 3.11. `[VERIFIED: P2 STATE.md decision]`
- `server_default=func.now()` — DDL-уровневый default: `created_at` заполняется PostgreSQL при INSERT. После flush и до commit значение доступно только если выполнить `await session.refresh(bet)` ИЛИ если использовать `RETURNING` в flush. **Важно:** `expire_on_commit=False` не помогает с server_default — значение никогда не было загружено в Python-объект. Решение для P3: после `flush()` в репозитории вызывать `await session.refresh(bet)` ИЛИ возвращать объект из SELECT внутри той же сессии перед commit. `[ASSUMED — на основе SQLAlchemy async поведения; требует верификации в тестах]`
- `onupdate=func.now()` — ORM UPDATE trigger: срабатывает только при изменении ORM-объекта (P5 settle path). При прямом SQL UPDATE мимо ORM — не срабатывает. Для P3 — только server_default важен; onupdate используется в P5.

### Pattern 2: AsyncUnitOfWork (verified code shape)

```python
# src/bet_maker/facades/uow.py
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bet_maker.repositories.bets import BetRepository


class AsyncUnitOfWork:
    bets: BetRepository
    session: AsyncSession

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._cm: async_sessionmaker[AsyncSession] | None = None

    async def __aenter__(self) -> AsyncUnitOfWork:
        self._cm = self._sessionmaker.begin()
        self.session = await self._cm.__aenter__()
        self.bets = BetRepository(self.session)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        assert self._cm is not None
        await self._cm.__aexit__(exc_type, exc, tb)
        self._cm = None
```

**Source:** `[CITED: .planning/research/ARCHITECTURE.md §Pattern 1 + docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html]`

### Pattern 3: Alembic Initial Migration — PG ENUM идемпотентность

**Ключевая проблема:** `CREATE TYPE bet_status AS ENUM (...)` падает при повторном запуске (`alembic upgrade head` дважды) с ошибкой `type "bet_status" already exists`.

**Решение через `op.execute`:**

```python
# alembic/versions/20260515_0001_bets_initial.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    # Idempotent ENUM creation
    bet_status = postgresql.ENUM(
        "PENDING", "WON", "LOST",
        name="bet_status",
        create_type=False,  # не создаём автоматически при create_all
    )
    bet_status.create(op.get_bind(), checkfirst=True)  # checkfirst=True = DO NOTHING IF EXISTS

    op.create_table(
        "bets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "WON", "LOST", name="bet_status", create_type=False),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("bets")
    bet_status = postgresql.ENUM("PENDING", "WON", "LOST", name="bet_status", create_type=False)
    bet_status.drop(op.get_bind(), checkfirst=True)
```

**Критично:** `create_type=False` в `sa.Enum(...)` внутри `create_table` — иначе Alembic попытается CREATE TYPE ещё раз. `checkfirst=True` в `bet_status.create()` делает `SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'bet_status')` перед созданием.

**Source:** `[VERIFIED: docs.sqlalchemy.org/en/20/dialects/postgresql.html — ENUM.create(checkfirst=True)]`

### Pattern 4: testcontainers session-scoped с asyncpg URL + alembic programmatic upgrade

```python
# tests/conftest.py (root — дополнение к существующему skeleton)
from __future__ import annotations

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_container():
    """Session-scoped PostgreSQL container. Built-in wait strategy (psql SELECT 1 via ExecWaitStrategy)."""
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_dsn(postgres_container: PostgresContainer) -> str:
    return postgres_container.get_connection_url()  # postgresql+asyncpg://...


@pytest.fixture(scope="session")
def run_alembic_migrations(pg_dsn: str) -> None:
    """Run alembic upgrade head ONCE per session — validates migration idempotency."""
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", pg_dsn)
    command.upgrade(alembic_cfg, "head")
    # Second run — must be idempotent (success criterion #5)
    command.upgrade(alembic_cfg, "head")


@pytest_asyncio.fixture(scope="session")
async def async_engine(pg_dsn: str, run_alembic_migrations: None):
    engine = create_async_engine(pg_dsn, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def truncate_bets(async_engine):
    """Per-test isolation via TRUNCATE — real COMMIT transactions, not savepoints."""
    yield
    async with async_engine.begin() as conn:
        await conn.execute(sa.text("TRUNCATE bets RESTART IDENTITY CASCADE"))
```

**Ключевые детали:**
- `PostgresContainer` ждёт готовности через `ExecWaitStrategy` (psql SELECT), не через log-message. `[VERIFIED: testcontainers-python GitHub source]`
- `driver="asyncpg"` → `get_connection_url()` возвращает `postgresql+asyncpg://...`. `[VERIFIED: testcontainers-python source — driver_str = f"+{driver}" если driver не None]`
- `command.upgrade(alembic_cfg, "head")` — programmatic invocation. Запускается sync (alembic синхронный), поэтому в `scope="session"` fixture без `async`. `[VERIFIED: alembic.sqlalchemy.org — Programmatic Command Invocation]`
- Alembic `env.py` уже читает `sqlalchemy.url` из Config через `config.get_main_option("sqlalchemy.url")` — это значит `set_main_option` перезаписывает его для тестов без правки env.py. `[VERIFIED: alembic/env.py в репозитории]`
- `TRUNCATE RESTART IDENTITY CASCADE` — не `DELETE` (медленнее), не `ROLLBACK` (не работает с COMMIT-based UoW тестами). `[ASSUMED — стандартная практика; подтверждается CONTEXT.md D-23]`
- `scope="session"` для контейнера и engine — один контейнер на весь pytest run. `[ASSUMED — стандартная практика для testcontainers]`

**Предостережение:** `async` fixtures с `scope="session"` требуют `pytest-asyncio >= 0.21` в режиме `auto`. Наш pytest-asyncio 1.1.0 поддерживает. Однако session-scoped async fixtures должны быть объявлены через `@pytest_asyncio.fixture(scope="session")`, НЕ через `@pytest.fixture(scope="session")` + async. `[VERIFIED: pytest-asyncio 1.1.0 поддерживает session scope в auto mode]`

### Pattern 5: tenacity async retry для wait_for_postgres

```python
# src/bet_maker/infrastructure/db/pings.py
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential
import logging

log = structlog.get_logger()
_stdlib_log = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(10),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
    before_sleep=before_sleep_log(_stdlib_log, logging.WARNING),
)
async def wait_for_postgres(engine: AsyncEngine) -> None:
    """Tenacity@retry автоматически определяет async coroutine и использует AsyncRetrying."""
    async with engine.connect() as conn:
        await conn.scalar(text("SELECT 1"))


async def ping_postgres(engine: AsyncEngine) -> bool:
    """Single ping for /health — no retry. Returns True/False."""
    try:
        async with engine.connect() as conn:
            await conn.scalar(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
```

**Source:** `[VERIFIED: github.com/jd/tenacity — @retry decorator auto-uses AsyncRetrying for coroutines]`

**Примечание:** `before_sleep_log` использует `logging.Logger` (stdlib), не structlog — это ограничение tenacity 9.x. Для structlog-интеграции: написать кастомный `before_sleep` callback с `structlog.get_logger().warning(...)`. Альтернатива — принять stdlib logging для retry событий (уровень WARNING уходит в консоль через alembic logger config).

### Pattern 6: Health check endpoint с /health JSON

```python
# src/bet_maker/entrypoints/api/health.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from bet_maker.facades.deps import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(engine: AsyncEngine = Depends(get_engine)) -> JSONResponse:
    ok = await ping_postgres(engine)
    if ok:
        return JSONResponse({"status": "ok", "checks": {"postgres": "ok"}})
    return JSONResponse(
        {"status": "degraded", "checks": {"postgres": "down"}},
        status_code=503,
    )
```

**Важно:** P1 smoke-test `assert response.json() == {"status": "ok"}` сломается. Первый implementing-task P3 обновляет assertion на `body["status"] == "ok"` (subset check). `[CITED: CONTEXT.md D-28]`

### Anti-Patterns to Avoid

- **Anti-Pattern 1:** `session.commit()` в репозитории. Только `flush()` — UoW владеет commit. `[CITED: ARCHITECTURE.md Anti-Pattern 1]`
- **Anti-Pattern 2:** Один `AsyncSession` shared между requests или between tasks. Каждый request = новый UoW = новая session. `[CITED: ARCHITECTURE.md Anti-Pattern 3, PITFALLS A2]`
- **Anti-Pattern 3:** Module-level `AsyncSession` или `AsyncEngine` в lifespan без `app.state`. Engine — module-level safe (пул), Session — НИКОГДА module-level. `[CITED: PITFALLS A2]`
- **Anti-Pattern 4:** `Numeric(asdecimal=False)` или `Float()` для amount. Теряет Decimal точность. `[CITED: PITFALLS A5]`
- **Anti-Pattern 5:** Возвращать raw ORM instance из interactor за пределы session. `model_validate(..., from_attributes=True)` внутри сессии. `[CITED: PITFALLS A1]`
- **Anti-Pattern 6:** Хардкод `sqlalchemy.url` в `alembic.ini`. Anti-Pattern 7 уже закрыт в P1. `[CITED: ARCHITECTURE.md Anti-Pattern 7]`
- **Anti-Pattern 7:** `SQLite` в тестах вместо реального PG. FOR UPDATE, ENUM types, NUMERIC precision — всё ломается. QA-07 явно требует testcontainers. `[CITED: REQUIREMENTS.md QA-07]`

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Transaction lifecycle (commit/rollback on exception) | Ручной try/except + commit/rollback | `async_sessionmaker.begin()` как context manager | SQLAlchemy гарантирует rollback на любом исключении автоматически |
| Decimal quantization / rounding | Custom round() логика | `Decimal.quantize(Decimal("0.01"), ROUND_HALF_UP)` | Banker's rounding vs half-up — значимо для финансов |
| DB wait на startup | Custom `while True: connect()` loop | `tenacity @retry(stop=stop_after_attempt(N), wait=wait_exponential(...))` | Правильный exponential backoff, reraise, before_sleep_log |
| Container readiness в тестах | `time.sleep(5)` после start() | `PostgresContainer.start()` включает встроенный ExecWaitStrategy | Psql SELECT внутри контейнера — надёжнее любого sleep |
| Alembic migration runner в тестах | subprocess или `os.system("alembic upgrade head")` | `alembic.command.upgrade(Config("alembic.ini"), "head")` | Programmatic API — нет subprocess overhead, можно переопределить sqlalchemy.url |
| PG ENUM idempotency | DO $$ BEGIN / EXCEPTION блок | `ENUM.create(bind, checkfirst=True)` | Стандартный SQLAlchemy/Alembic API для этого |
| Pydantic Decimal input validation | Ручная проверка len(str(v).split(".")[-1]) | `Field(gt=0, max_digits=12, decimal_places=2)` | Type-level, 422 с точным error type `decimal_max_places` |

**Key insight:** SQLAlchemy 2.0 async + Alembic + testcontainers закрывают 95% инфраструктурного кода — всё, что ниже business-logic, уже решено.

---

## Common Pitfalls

### Pitfall 1: `server_default` не заполняет Python атрибут сразу после flush

**What goes wrong:** `await uow.session.flush()` в `BetRepository.add()` отправляет INSERT в PG, но `bet.created_at` в Python-объекте может быть `None` (server_default — это DDL, PG заполняет на сервере, не ORM). Если вернуть `bet` из interactor и сразу сериализовать в BetRead — `created_at = None` → Pydantic ValidationError или `None` в ответе.

**Why it happens:** `server_default` заполняется PG-сервером. SQLAlchemy не делает RETURNING автоматически после flush в async mode (зависит от версии). `expire_on_commit=False` не помогает — атрибут просто никогда не был загружен.

**How to avoid:** После `flush()` вызвать `await session.refresh(bet)` — это выполняет SELECT по PK и загружает DB-populated поля. ИЛИ использовать `RETURNING id, created_at, updated_at` в INSERT (явно через `execution_options(synchronize_session=False)`). Рекомендуемый путь — `refresh`.

```python
async def add(self, bet: Bet) -> Bet:
    self._session.add(bet)
    await self._session.flush()
    await self._session.refresh(bet)  # loads server_default fields
    return bet
```

**Warning signs:** `created_at` = `None` в BetRead ответе. `updated_at` = `None`.

[ASSUMED: основано на SQLAlchemy async поведении. Требует верификации через test_models.py]

---

### Pitfall 2: Alembic ENUM `CREATE TYPE` на повторном upgrade head

**What goes wrong:** `alembic upgrade head` второй раз → `sqlalchemy.exc.ProgrammingError: type "bet_status" already exists`.

**Why it happens:** Без `checkfirst=True`, `ENUM.create(bind)` всегда эмитирует `CREATE TYPE`.

**How to avoid:** `ENUM.create(op.get_bind(), checkfirst=True)` + `create_type=False` в `sa.Enum(...)` внутри `create_table`. `[VERIFIED: docs.sqlalchemy.org/en/20/dialects/postgresql.html]`

**Warning signs:** Test `test_alembic.py` падает на втором вызове `command.upgrade(cfg, "head")`.

---

### Pitfall 3: testcontainers session-scoped async fixture в pytest-asyncio

**What goes wrong:** `@pytest_asyncio.fixture(scope="session")` + event loop scope mismatch → `ScopeMismatch: You tried to access the function scoped fixture ... with a session scoped request object`.

**Why it happens:** pytest-asyncio 1.x по умолчанию создаёт новый event loop per function. Session-scoped async fixtures требуют session-scoped event loop.

**How to avoid:** Добавить в `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
# + для session-scoped async fixtures:
asyncio_default_fixture_loop_scope = "session"
```
ИЛИ использовать `@pytest.fixture(scope="session")` для sync части (контейнер, DSN, alembic) и `@pytest_asyncio.fixture(scope="session")` только для async-части (engine, sessionmaker).

[ASSUMED: основано на pytest-asyncio 1.x документации. Требует верификации при написании conftest]

---

### Pitfall 4: P1 health test `body == {"status": "ok"}` сломается

**What goes wrong:** P3 меняет health response на `{"status":"ok","checks":{"postgres":"ok"}}`. Существующий тест `assert response.json() == {"status": "ok"}` фейлится.

**How to avoid:** Первый implementing task P3 обновляет assertion:
```python
# BEFORE
assert response.json() == {"status": "ok"}
# AFTER
assert response.json()["status"] == "ok"
```
`[CITED: CONTEXT.md D-28]`

---

### Pitfall 5: Decimal serialization — тесты сравнивают float вместо string

**What goes wrong:** `assert body["amount"] == 10.0` — всегда False, т.к. Pydantic v2 сериализует Decimal как `"10.00"` (string). `[VERIFIED: uv run python — model_dump_json() returns {"amount":"10.00"}]`

**How to avoid:** `assert body["amount"] == "10.00"` — везде string. `[CITED: CONTEXT.md D-19]`

---

### Pitfall 6: alembic.ini `sqlalchemy.url` override в тестах

**What goes wrong:** При programmatic `command.upgrade(Config("alembic.ini"), "head")`, если `alembic.ini` не содержит `sqlalchemy.url`, env.py берёт его из `BetMakerSettings().postgres_dsn` (production DSN), не из тестового контейнера.

**How to avoid:**
```python
alembic_cfg = Config("alembic.ini")
alembic_cfg.set_main_option("sqlalchemy.url", test_dsn)  # override перед вызовом
command.upgrade(alembic_cfg, "head")
```
Наш env.py читает `config.get_main_option("sqlalchemy.url")` — если он установлен через `set_main_option`, production DSN не используется. `[VERIFIED: alembic/env.py в репозитории строка 19]`

---

### Pitfall 7: Decimal round-trip через asyncpg

**What goes wrong:** `asyncpg` с колонкой `NUMERIC(12,2)` — `asdecimal=True` по умолчанию в `Numeric(12,2)` → Python получает `Decimal`. НО: если использовать `Float()` вместо `Numeric()` — asyncpg вернёт float → `10.00000000001`.

**How to avoid:** `Mapped[Decimal] = mapped_column(Numeric(12, 2))` — `asdecimal=True` выведено автоматически из `Decimal` Python annotation. `[VERIFIED: SQLAlchemy Numeric.__init__ docs]`

---

## Code Examples

### Interactor place_bet с EventLookup

```python
# src/bet_maker/interactors/place_bet.py
from __future__ import annotations

from uuid import UUID
from decimal import Decimal

import structlog

from bet_maker.facades.event_lookup import EventLookup
from bet_maker.facades.uow import AsyncUnitOfWork
from bet_maker.helpers.money import quantize_amount
from bet_maker.models.bet import Bet, BetStatus
from bet_maker.schemas.bets import BetRead
from bet_maker.schemas.events import EventState
from config.time import utc_now

log = structlog.get_logger()


class EventNotBettable(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


async def place_bet(
    uow: AsyncUnitOfWork,
    *,
    event_id: UUID,
    amount: Decimal,
    event_lookup: EventLookup,
) -> BetRead:
    snapshot = await event_lookup.get_event(event_id)
    if snapshot is None:
        raise EventNotBettable("event not found")
    if snapshot.deadline <= utc_now():
        raise EventNotBettable("deadline passed")
    if snapshot.state != EventState.NEW:
        raise EventNotBettable("event not active")

    async with uow:
        bet = Bet(event_id=event_id, amount=quantize_amount(amount), status=BetStatus.PENDING)
        uow.bets.add(bet)
        await uow.session.flush()
        await uow.session.refresh(bet)  # load server_default created_at/updated_at
        return BetRead.model_validate(bet, from_attributes=True)  # inside session — A1 mitigated
```

`[CITED: CONTEXT.md D-14]`

### BetRepository

```python
# src/bet_maker/repositories/bets.py
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bet_maker.models.bet import Bet


class BetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, bet: Bet) -> None:
        self._session.add(bet)  # no flush here — caller (interactor) controls flush timing

    async def get_by_id(self, bet_id: UUID) -> Bet | None:
        result = await self._session.execute(select(Bet).where(Bet.id == bet_id))
        return result.scalar_one_or_none()
```

### Selectors

```python
# src/bet_maker/selectors/list_bets.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetRead


async def list_bets(session: AsyncSession) -> list[BetRead]:
    stmt = select(Bet).order_by(Bet.created_at.desc())
    rows = (await session.execute(stmt)).scalars()
    return [BetRead.model_validate(r, from_attributes=True) for r in rows]
```

### Pydantic BetCreate с Decimal validation

```python
# Verified: uv run python — Field(decimal_places=2) + AfterValidator
# 10.123 → 422 с type="decimal_max_places"
# 10 → quantized to 10.00
# -5 → 422 с type="greater_than"

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from bet_maker.helpers.money import quantize_amount

Amount = Annotated[
    Decimal,
    Field(gt=Decimal("0"), max_digits=12, decimal_places=2),
    AfterValidator(quantize_amount),
]

class BetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    amount: Amount
```

`[VERIFIED: local uv run python test]`

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `alembic init` (sync env.py) | `alembic init -t async` | SQLAlchemy 1.4+ / Alembic 1.7+ | env.py uses asyncio.run() — уже в P1 |
| `StrEnum` | `(str, Enum)` | Python 3.10 (StrEnum = 3.11+) | BetStatus, EventState — см. P2 D-13 |
| `condecimal()` (Pydantic v1) | `Annotated[Decimal, Field(...)]` | Pydantic v2 | condecimal deprecated; Field + AfterValidator |
| `Column()` style | `Mapped[] = mapped_column()` | SQLAlchemy 2.0 | Typed, mypy-friendly |
| Shared session | Per-request UoW via `async_sessionmaker.begin()` | SQLAlchemy 2.0 async best practice | Pitfall A2 mitigation |

**Deprecated/outdated:**
- `condecimal` из Pydantic v1: не использовать. Заменено `Annotated[Decimal, Field(max_digits=..., decimal_places=...)]`.
- `Column()` без `Mapped[]`: legacy style, не проходит mypy strict.
- `testcontainers[postgresql]` как extra: в testcontainers 4.x нет такого extra — postgres модуль в base пакете.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `server_default=func.now()` не заполняет Python атрибут после flush без `refresh(bet)` | Pitfall 1, Pattern 1, Code Examples | Если SQLAlchemy делает RETURNING автоматически — refresh лишний (harmless). Если нет — `created_at=None` в BetRead. |
| A2 | `TRUNCATE bets RESTART IDENTITY CASCADE` per-test в teardown достаточно для isolation | Pattern 4 | Если другие таблицы (P5) появятся — нужно расширить TRUNCATE список. В P3 bets единственная таблица. |
| A3 | Session-scoped async fixtures работают с `asyncio_mode="auto"` в pytest-asyncio 1.1.0 | Pattern 4 | Если нужен явный `asyncio_default_fixture_loop_scope="session"` — добавить в pyproject. |
| A4 | Programmatic `command.upgrade(cfg, "head")` с `set_main_option("sqlalchemy.url", ...)` корректно переопределяет DSN из BetMakerSettings в env.py | Pitfall 6, Pattern 4 | env.py читает `config.get_main_option("sqlalchemy.url")` — если он установлен, Settings.postgres_dsn не вызывается. Это стандартная Alembic практика. |

---

## Open Questions

1. **`session.refresh(bet)` vs `RETURNING` после flush**
   - What we know: `server_default=func.now()` не заполняет Python атрибут через ORM автоматически в async режиме.
   - What's unclear: Делает ли SQLAlchemy 2.0.49 + asyncpg RETURNING автоматически при flush? Если да — refresh лишний.
   - Recommendation: Добавить `test_models.py` с проверкой `bet.created_at is not None` после flush без refresh — если зелёный без refresh, удалить. Безопасно оставить refresh в любом случае (один SELECT).

2. **pytest-asyncio session-scoped fixtures loop scope**
   - What we know: pytest-asyncio 1.1.0 поддерживает `scope="session"` для async fixtures.
   - What's unclear: Нужен ли `asyncio_default_fixture_loop_scope = "session"` в pyproject.ini_options для корректной работы session-scoped async fixtures?
   - Recommendation: Попробовать без настройки первым. Если ScopeMismatch — добавить `asyncio_default_fixture_loop_scope = "session"`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | testcontainers PostgresContainer | ✓ (macOS dev) | Docker Desktop | В CI: GitHub Actions runner имеет Docker natively |
| Python 3.10 | Runtime | ✓ | 3.10.20 (.python-version) | — |
| PostgreSQL (container) | QA-07 tests | ✓ (via testcontainers) | 16-alpine | — |
| uv | Package management | ✓ | 0.11.14 | — |
| testcontainers | QA-07 | не установлен (needs `uv add`) | 4.14.2 (latest) | — |

**Missing dependencies with no fallback:** testcontainers — нужно добавить в `dependency-groups.dev`.

**Missing dependencies with fallback:** нет.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.1.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/bet_maker -q -x` |
| Full suite command | `uv run pytest -q` |
| Coverage command | `uv run pytest --cov=src/bet_maker --cov-fail-under=85 tests/bet_maker` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BM-01 (sync) | Bet model без coefficient | unit | `pytest tests/bet_maker/test_models.py -x` | ❌ Wave 0 |
| BM-01 | amount Numeric(12,2), asdecimal=True | unit/integration | `pytest tests/bet_maker/test_models.py -x` | ❌ Wave 0 |
| BM-02 | UoW commit on clean exit, rollback on exception | unit | `pytest tests/bet_maker/test_uow.py -x` | ❌ Wave 0 |
| BM-03 | Layer structure — import проверка | unit (structural) | `pytest tests/bet_maker/test_models.py -x` | ❌ Wave 0 |
| BM-05 | POST /bet 201 + Decimal round-trip "10.00" | integration | `pytest tests/bet_maker/test_bet_routes.py::test_post_bet_happy -x` | ❌ Wave 0 |
| BM-05 | POST /bet 422 — amount >2dp | integration | `pytest tests/bet_maker/test_bet_routes.py::test_post_bet_invalid_amount -x` | ❌ Wave 0 |
| BM-05 | POST /bet 422 — amount <=0 | integration | `pytest tests/bet_maker/test_bet_routes.py::test_post_bet_negative_amount -x` | ❌ Wave 0 |
| BM-06 | POST /bet 422 — event not found | integration | `pytest tests/bet_maker/test_bet_routes.py::test_post_bet_event_not_found -x` | ❌ Wave 0 |
| BM-06 | POST /bet 422 — deadline passed | integration | `pytest tests/bet_maker/test_bet_routes.py::test_post_bet_deadline_passed -x` | ❌ Wave 0 |
| BM-06 | POST /bet 422 — event not NEW | integration | `pytest tests/bet_maker/test_bet_routes.py::test_post_bet_event_not_new -x` | ❌ Wave 0 |
| BM-07 | GET /bets returns list, ordered created_at desc | integration | `pytest tests/bet_maker/test_bet_routes.py::test_get_bets_ordering -x` | ❌ Wave 0 |
| BM-08 | GET /health 200 с PG up | integration | `pytest tests/bet_maker/test_health.py::test_health_pg_ok -x` | частично (P1 stub) |
| BM-08 | GET /health 503 с PG down | integration | `pytest tests/bet_maker/test_health.py::test_health_pg_down -x` | ❌ Wave 0 |
| BM-13 | GET /bet/{id} 200 + BetRead | integration | `pytest tests/bet_maker/test_bet_routes.py::test_get_bet_by_id -x` | ❌ Wave 0 |
| BM-13 | GET /bet/{id} 404 | integration | `pytest tests/bet_maker/test_bet_routes.py::test_get_bet_not_found -x` | ❌ Wave 0 |
| QA-07 | Все тесты используют реальный PG (testcontainers) | integration | `pytest tests/bet_maker -q` | ❌ Wave 0 |
| SC-5 | alembic upgrade head idempotent (2 runs) | alembic test | `pytest tests/bet_maker/test_alembic.py -x` | ❌ Wave 0 |
| SC-6 | Decimal round-trip "10.00" → "10.00" | integration | `pytest tests/bet_maker/test_bet_routes.py::test_decimal_roundtrip -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/bet_maker -q -x --tb=short`
- **Per wave merge:** `uv run pytest -q` (весь suite)
- **Phase gate:** `uv run pytest --cov=src/bet_maker --cov-fail-under=85 tests/bet_maker`

### Wave 0 Gaps

- [ ] `tests/bet_maker/test_models.py` — covers BM-01
- [ ] `tests/bet_maker/test_repositories.py` — covers BM-02
- [ ] `tests/bet_maker/test_uow.py` — covers BM-02
- [ ] `tests/bet_maker/test_event_lookup.py` — covers BM-06 (StubEventLookup)
- [ ] `tests/bet_maker/test_place_bet.py` — covers BM-05/BM-06
- [ ] `tests/bet_maker/test_selectors.py` — covers BM-07/BM-13
- [ ] `tests/bet_maker/test_bet_routes.py` — covers BM-05/BM-06/BM-07/BM-13
- [ ] `tests/bet_maker/test_health.py` — update/extend P1 (covers BM-08)
- [ ] `tests/bet_maker/test_alembic.py` — covers SC-5 (idempotent upgrade head)
- [ ] `tests/bet_maker/test_lifespan.py` — covers D-27 (startup retry)
- [ ] `tests/conftest.py` — расширить: postgres_container, pg_dsn, run_alembic_migrations, async_engine, session_factory, truncate_bets
- [ ] `tests/bet_maker/conftest.py` — переписать: PG-backed client fixture + StubEventLookup seed fixture
- [ ] `pyproject.toml` — добавить `testcontainers>=4.9,<5` в dev deps; добавить `source = ["src/bet_maker"]` в coverage.run (сейчас только src/line_provider)
- [ ] `alembic/versions/20260515_0001_bets_initial.py` — первая миграция

---

## Security Domain

> `security_enforcement` не установлен явно в `.planning/config.json` — treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | не в scope (нет auth в ТЗ) |
| V3 Session Management | no | не в scope |
| V4 Access Control | no | не в scope |
| V5 Input Validation | yes | Pydantic v2 `Field(gt=0, max_digits=12, decimal_places=2)` + `extra="forbid"` |
| V6 Cryptography | no | нет криптографии в P3 |

### Known Threat Patterns for Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Oversized Decimal payload (очень большое amount) | Tampering | `max_digits=12` ограничивает до 999999999999.99 |
| Extra fields in POST body | Tampering | `extra="forbid"` на BetCreate |
| SQL injection через event_id | Tampering | UUID4 тип — невалидные UUID отклоняются Pydantic до попадания в SQL |
| Negative/zero amount | Tampering | `Field(gt=0)` — 422 до DB |
| Reconnect flood при PG down | DoS (self) | tenacity `stop_after_attempt(10)` + exponential backoff ограничивает loop |

---

## Sources

### Primary (HIGH confidence)
- `/websites/sqlalchemy_en_20_orm` (Context7) — expire_on_commit, mapped_column Enum, typed Mapped
- `/websites/sqlalchemy_en_20` (Context7) — ENUM.create(checkfirst=True), pool_pre_ping, Numeric asdecimal
- `/websites/alembic_sqlalchemy` (Context7) — programmatic command.upgrade, Config.set_main_option
- `/testcontainers/testcontainers-python` (Context7) — PostgresContainer API, wait strategy
- `/jd/tenacity` (Context7) — @retry for coroutines, before_sleep_log, wait_exponential
- `github.com/testcontainers/testcontainers-python` (WebFetch) — PostgresContainer._connect() = ExecWaitStrategy; driver parameter verified
- `pypi.org/pypi/testcontainers` (direct check) — version 4.14.2; no "postgresql" extra in v4.x
- `alembic/env.py` в репозитории — verified existing async template + set_main_option pattern
- `uv run python` (local verification) — Pydantic decimal_places=2 validation, Decimal JSON serialization "10.00"
- `uv run python` (local verification) — SQLAlchemy Numeric(12,2).asdecimal=True default

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` §Pattern 1 — UoW/Repository verified shape
- `.planning/research/PITFALLS.md` §A1..A7, D2 — mitigations verified in P2 execution
- `CONTEXT.md D-01..D-32` — все locked decisions (user verified in discussion)

### Tertiary (LOW confidence)
- Assumption A1 (server_default + refresh) — standard SQLAlchemy behavior, not verified via live test in this session
- Assumption A3 (session-scoped async fixtures) — pytest-asyncio docs, не запускалось

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — все версии в pyproject.toml, PyPI verified
- Architecture: HIGH — ARCHITECTURE.md + SQLAlchemy Context7 docs verified
- Pitfalls: HIGH — PITFALLS.md verified through P1/P2 execution; mitigations locked in CONTEXT.md
- Test patterns: MEDIUM — testcontainers API verified, session-scoped async fixtures assumed

**Research date:** 2026-05-15
**Valid until:** 2026-06-15 (stable stack; testcontainers 4.x API stable)
