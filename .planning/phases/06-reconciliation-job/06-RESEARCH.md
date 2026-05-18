# Phase 6: Reconciliation job — Research

**Researched:** 2026-05-18
**Domain:** asyncio background task, SQLAlchemy 2.0 async SELECT DISTINCT, Alembic `ALTER TYPE ADD VALUE`, FastAPI lifespan lifecycle
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Все решения D-01..D-25 из 06-CONTEXT.md зафиксированы. Ключевые:

- **D-01** `BetRepository.get_pending_event_ids() -> list[UUID]` — `SELECT DISTINCT event_id FROM bets WHERE status='PENDING'`
- **D-02** Branch-таблица per event_id: FINISHED_WIN/LOSE → `settle_bets_for_event`; None (404) → `cancel_bets_for_event`; NEW → skip
- **D-03** `BetStatus.CANCELLED = "cancelled"` + Alembic migration `0003_bet_status_cancelled.py`
- **D-04** `cancel_bets_for_event(uow, *, event_id, cancelled_via)` → `CancelResult` DTO; reuses `get_pending_locked` + `FOR UPDATE SKIP LOCKED`
- **D-06** Отдельный `HttpEventLookup` для reconciler'а с reconciler-params; разделяет singleton `httpx.AsyncClient`
- **D-09** `BetMakerSettings` + 2 новых поля: `line_provider_reconciler_attempts: int = 5`, `line_provider_reconciler_backoff_max_s: float = 10.0` (третье — `reconciliation_interval_s` — уже есть в коде)
- **D-10** Двухуровневый try/except в `reconciliation_loop`: inner — `asyncio.CancelledError` (re-raise), outer — `Exception` (log + continue)
- **D-11** `_run_tick` структура: отдельный read-only UoW для `get_pending_event_ids`, per-event UoW в `_reconcile_event`; per-event try/except + continue
- **D-13** `/health` четвёртая проверка: `reconciler_ok = not reconciliation_task.done()`
- **D-15** Startup-порядок: reconciler_event_lookup pin → `create_task(reconciliation_loop, name="reconciliation")` после declare topology
- **D-16** Shutdown: `task.cancel()` + `with suppress(CancelledError): await task` — **первым** в finally, до `broker.close() / http_client.aclose() / engine.dispose()`
- **D-17** `await asyncio.sleep(interval_s)` ПЕРЕД первым tick
- **D-19..D-24** Тестовые сценарии (unit cancel, unit loop, health concurrent, e2e drop-publish)
- **D-25** Sync-task: REQUIREMENTS.md BM-05 + BM-12 + ROADMAP.md Phase 6 — CANCELLED branch

### Claude's Discretion

- Точный путь Alembic-миграции для `ALTER TYPE betstatus ADD VALUE` в async-template
- Размещение: `bet_maker/entrypoints/reconciliation.py` (рекомендовано CONTEXT.md)
- Точная реализация `monkeypatch.setattr(RabbitEventBus, "publish", AsyncMock())` для D-23
- Структура log-событий namespace `reconciler.*`
- `_reconcile_event` — отдельная функция vs метод класса `Reconciler`

### Deferred Ideas (OUT OF SCOPE)

- Deadline-based cancel fallback (без `event_deadline` колонки)
- Batch endpoint `GET /events?ids=...` в line-provider
- Reconciler-публикация в RMQ
- Auto-restart reconciler task через watchdog
- Jitter для interval
- Prometheus метрики
- `CANCELLED-cause` колонка
- Concurrent HTTP внутри tick через asyncio.gather + semaphore
- Grace period для свежих PENDING bet'ов

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BM-12 | Reconciliation job — asyncio background task в lifespan, период через pydantic-settings (default 30s); выбирает PENDING-ставки, тянет статус события из line-provider, доводит до WON/LOST | Полностью покрыт: asyncio.create_task pattern, SELECT DISTINCT, HttpEventLookup reuse, settle/cancel interactors |
| QA-08 | E2E сценарий: create event → place bet → drop publish → finish event → assert bet WON/CANCELLED via reconciler within one interval | Покрыт: testcontainers pattern из P5, monkeypatch RabbitEventBus.publish, ENV override RECONCILIATION_INTERVAL_S=1.0 |

</phase_requirements>

---

## Summary

Фаза 6 добавляет один новый файл-модуль (`entrypoints/reconciliation.py`), один новый interactor (`interactors/cancel_bets_for_event.py`), расширение `BetStatus` enum на четвёртое значение `CANCELLED` с Alembic-миграцией, два новых поля в `BetMakerSettings`, расширение lifespan, расширение `/health`, и тест-suite из трёх уровней (unit / integration / e2e).

Все зависимости фазы (P4 `HttpEventLookup` + `make_retry_decorator`, P5 `settle_bets_for_event` + `get_pending_locked` + `AsyncUnitOfWork` + testcontainers fixtures) уже реализованы и верифицированы. Фаза является **чистым extension**-слоем поверх готовой инфраструктуры — никакой существующий production-код не переписывается, кроме lifespan.py, health.py, deps.py, settings/config.py, schemas/bets.py и repositories/bets.py (добавление методов/полей).

Единственный нетривиальный технический вопрос — паттерн Alembic `ALTER TYPE ... ADD VALUE` в async-окружении — **решён**: нужен `op.get_context().autocommit_block()` (официальная Alembic рекомендация). Это важно потому что PostgreSQL не разрешает `ALTER TYPE ADD VALUE` внутри транзакции.

**Primary recommendation:** Имплементировать в порядке зависимостей: (1) schema/settings/migration, (2) repository method, (3) cancel interactor, (4) reconciler module, (5) lifespan wiring, (6) health wiring, (7) deps wiring, (8) тесты. Порядок обусловлен тем, что reconciler импортирует cancel interactor, lifespan импортирует reconciler, health импортирует deps.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Polling PENDING event_ids | API / Backend (bet-maker) | Database | Reconciler живёт в том же процессе что и HTTP API; SELECT DISTINCT из PG |
| Fetch event state | API / Backend (bet-maker) | — | Reconciler вызывает line-provider HTTP endpoint через уже существующий HttpEventLookup |
| Settle / cancel bets | API / Backend (bet-maker) | Database | Interactors settle_bets_for_event / cancel_bets_for_event + UoW + PG |
| Task lifecycle (start/cancel) | API / Backend (bet-maker) | — | asyncio.create_task в lifespan; не нужна отдельная инфраструктура |
| Liveness check | API / Backend (bet-maker) | — | /health проверяет `task.done()` — стандартный HTTP-endpoint pattern |

---

## Standard Stack

### Core (все уже pinned в pyproject.toml — новых зависимостей нет)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio | stdlib | `create_task`, `sleep`, `CancelledError`, `Task` | Единственный способ background task в FastAPI без доп. библиотек |
| contextlib | stdlib | `suppress(asyncio.CancelledError)` в shutdown | Документированный идиом clean cancellation |
| SQLAlchemy | 2.0.49 | `select(Bet.event_id).where(...).distinct()` async | Уже используется; `.distinct()` нативно поддерживается |
| structlog | 25.5.0 | `bind_contextvars` / `clear_contextvars` в reconciler loop | Уже используется; log namespace `reconciler.*` |
| tenacity | 9.1.4 | `make_retry_decorator(attempts=5, max_backoff=10.0)` | Уже реализован в `facades/line_provider_client.py` — reuse |
| Alembic | 1.18.4 | `ALTER TYPE betstatus ADD VALUE IF NOT EXISTS 'cancelled'` | Уже используется для P3 + P5 migrations |

**Версии подтверждены:** все присутствуют в `pyproject.toml` и `uv.lock`. [VERIFIED: grep pyproject.toml]

**Установка:** `pyproject.toml` не меняется — новых зависимостей нет.

---

## Architecture Patterns

### System Architecture Diagram

```
 Startup (lifespan.py)
 ┌─────────────────────────────────────────────────────────────────────┐
 │ 1..8: engine, PG, httpx, broker, topology, state.pins              │
 │ 9:  reconciler_event_lookup = HttpEventLookup(attempts=5, bp=10s)  │
 │     reconciliation_task = create_task(reconciliation_loop(app))    │
 │ 10: yield                                                           │
 └─────────────────────────────────────────────────────────────────────┘
              │
              ▼ (background)
 ┌─────────────────────────────────────────────────────────────────────┐
 │  reconciliation_loop(app, interval_s)                              │
 │  ┌──────────────────────────────────────────────────────────────┐  │
 │  │  while True:                                                 │  │
 │  │    await asyncio.sleep(interval_s)   ← sleep FIRST          │  │
 │  │    try: await _run_tick(app)                                 │  │
 │  │    except CancelledError: log + raise                        │  │
 │  │    except Exception: log.exception + continue               │  │
 │  └──────────────────────────────────────────────────────────────┘  │
 └─────────────────────────────────────────────────────────────────────┘
              │
              ▼ _run_tick(app)
 ┌─────────────────────────────────────────────────────────────────────┐
 │  UoW(read-only) → BetRepository.get_pending_event_ids()           │
 │                   → list[UUID]                                     │
 │                          │                                         │
 │  for event_id in event_ids:                                        │
 │    try: await _reconcile_event(sessionmaker, lookup, event_id)     │
 │    except Exception: log.exception + continue                      │
 └─────────────────────────────────────────────────────────────────────┘
              │
              ▼ _reconcile_event(sessionmaker, lookup, event_id)
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │  snapshot = await lookup.get_event(event_id)                                 │
 │                                                                               │
 │  None ──────────────────────────────────────────► cancel_bets_for_event()   │
 │                                                     status=CANCELLED          │
 │                                                     settled_via='reconciler'  │
 │                                                                               │
 │  state in {FINISHED_WIN, FINISHED_LOSE} ────────► settle_bets_for_event()   │
 │                                                     status=WON|LOST           │
 │                                                     settled_via='reconciler'  │
 │                                                                               │
 │  state == NEW ──────────────────────────────────► skip (log.debug)           │
 └───────────────────────────────────────────────────────────────────────────────┘

 Shutdown (lifespan.py finally)
 ┌─────────────────────────────────────────────────────────────────────┐
 │  reconciliation_task.cancel()                                      │
 │  with suppress(CancelledError): await reconciliation_task  ← FIRST │
 │  await broker.close()                                              │
 │  await http_client.aclose()                                        │
 │  await engine.dispose()                                            │
 └─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
src/bet_maker/
├── entrypoints/
│   ├── reconciliation.py     # NEW: reconciliation_loop, _run_tick, _reconcile_event
│   ├── lifespan.py           # EXTEND: + reconciler_event_lookup pin + create_task + cancel
│   └── api/
│       └── health.py         # EXTEND: + reconciler check (not task.done())
├── interactors/
│   └── cancel_bets_for_event.py  # NEW: cancel interactor, CancelResult
├── repositories/
│   └── bets.py               # EXTEND: + get_pending_event_ids() -> list[UUID]
├── schemas/
│   ├── bets.py               # EXTEND: BetStatus.CANCELLED
│   └── settle.py             # EXTEND: + CancelResult DTO
├── facades/
│   └── deps.py               # EXTEND: + ReconcilerEventLookupDep + ReconciliationTaskDep
└── settings/
    └── config.py             # EXTEND: + 2 new fields

alembic/versions/
└── 20260518_0003_bet_status_cancelled.py  # NEW: ALTER TYPE ... ADD VALUE

tests/bet_maker/
├── test_cancel_bets_for_event.py  # NEW: D-19 unit tests
├── test_reconciliation.py         # NEW: D-20 unit tests (mock lookup + real PG)
├── test_reconciliation_concurrent.py  # NEW: D-22 integration concurrent
└── test_reconciliation_e2e.py     # NEW: D-23 e2e drop-publish (SC#5)
```

### Pattern 1: SELECT DISTINCT event_id via SQLAlchemy async

Прямой аналог `get_pending_locked` из `repositories/bets.py`, только без `with_for_update` и с `.distinct()` на одной колонке.

```python
# Source: docs.sqlalchemy.org/en/20/core/selectable.html (VERIFIED: Context7 /websites/sqlalchemy_en_20)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bet_maker.models.bet import Bet
from bet_maker.schemas.bets import BetStatus

async def get_pending_event_ids(self, session: AsyncSession) -> list[UUID]:
    result = await session.execute(
        select(Bet.event_id)
        .where(Bet.status == BetStatus.PENDING)
        .distinct()
    )
    return list(result.scalars().all())
```

Важно: `.scalars().all()` — стандартный путь для single-column SELECT; не использовать `.fetchall()` (вернёт Row-объекты, а не UUID).

### Pattern 2: asyncio.create_task + shutdown в lifespan

```python
# Source: Python 3.10 stdlib docs (VERIFIED: .venv/bin/python -c "import asyncio; help(asyncio.create_task)")
from contextlib import suppress
import asyncio

# Startup (inside lifespan, after all state.pins):
reconciliation_task = asyncio.create_task(
    reconciliation_loop(app, interval_s=settings.reconciliation_interval_s),
    name="reconciliation",
)
app.state.reconciliation_task = reconciliation_task

# Shutdown (first in finally):
reconciliation_task.cancel()
with suppress(asyncio.CancelledError):
    await reconciliation_task
```

`asyncio.create_task(coro, *, name=None)` — сигнатура в Python 3.10. [VERIFIED: .venv/bin/python]

`task.cancel()` выбрасывает `CancelledError` в `await asyncio.sleep(interval_s)` (ближайший await в loop). Из-за `raise` в `except asyncio.CancelledError`, ошибка пропагируется наружу — `with suppress(CancelledError)` в shutdown её поглощает.

### Pattern 3: Двухуровневый try/except loop

```python
# Source: D-10 из CONTEXT.md — совпадает со стандартным asyncio task lifecycle pattern
async def reconciliation_loop(app: FastAPI, *, interval_s: float) -> None:
    log = structlog.get_logger().bind(task="reconciliation")
    while True:
        try:
            await asyncio.sleep(interval_s)   # CancelledError брошено здесь
            await _run_tick(app)
        except asyncio.CancelledError:
            log.info("reconciler.cancelled")
            raise  # propagate — lifespan ловит через suppress
        except Exception:
            log.exception("reconciler.tick.failed")
            # loop continues — R8 invariant
```

Критически важно: `except asyncio.CancelledError` должен идти **до** `except Exception`. В Python 3.8+ `CancelledError` является подклассом `BaseException`, но в asyncio context он также является наследником `Exception` в Python < 3.8. В Python 3.10 `CancelledError` наследует от `BaseException`, **не** от `Exception` — поэтому `except Exception` его не поймает. [VERIFIED: Python 3.10 stdlib]

Тем не менее, для явной читаемости и согласованности с D-10 паттерном, `except asyncio.CancelledError` пишем явно перед `except Exception`.

### Pattern 4: Alembic `ALTER TYPE ADD VALUE` с autocommit_block

**Это критически важный паттерн** — PostgreSQL **не разрешает** `ALTER TYPE ADD VALUE` внутри транзакционного блока (транзакция должна быть уже зафиксирована). Alembic предоставляет `autocommit_block` для этого кейса.

```python
# Source: https://alembic.sqlalchemy.org/en/latest/api/runtime.html (VERIFIED: Context7 /websites/alembic_sqlalchemy)
from alembic import op

def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE betstatus ADD VALUE IF NOT EXISTS 'cancelled'")

def downgrade() -> None:
    # PostgreSQL не поддерживает DROP VALUE из ENUM — downgrade технически невозможен
    # без пересоздания type. Для test-task scope — pass.
    pass
```

**Почему `autocommit_block` обязателен**: В async-mode (наш `env.py` использует `async_engine_from_config`), Alembic открывает транзакцию вокруг каждой миграции. `ALTER TYPE ADD VALUE` в PostgreSQL требует autocommit — иначе `ERROR: ALTER TYPE ... ADD VALUE cannot run inside a transaction block`. `autocommit_block` коммитит предшествующую транзакцию и выполняет DDL без транзакции. [VERIFIED: Context7 /websites/alembic_sqlalchemy, официальная документация]

**Idempotency**: `ADD VALUE IF NOT EXISTS 'cancelled'` — PG 9.6+ поддерживает, у нас PG 16. Rerun safe.

**Что делать с Bet ORM**: `BetStatus` enum в SQLAlchemy определён как `SqlEnum(BetStatus, name="bet_status", create_type=True)`. После добавления `CANCELLED` в Python-enum и в PG-enum (через миграцию), ORM автоматически будет принимать новое значение без изменения модели.

### Pattern 5: CancelResult DTO (паттерн SettleResult)

```python
# Source: bet_maker/schemas/settle.py (VERIFIED: codebase)
from pydantic import BaseModel, ConfigDict
from typing import Literal
from uuid import UUID
from datetime import datetime

class CancelResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    cancelled_count: int
    cancelled_bet_ids: list[UUID]
    cancelled_via: Literal["reconciler"]
    cancelled_at: datetime
```

Без поля `terminal_state` — в cancel нет terminal state (причина 404, а не WIN/LOSE).

### Anti-Patterns to Avoid

- **Не использовать `except BaseException`** в reconciler loop — поймает `SystemExit`/`KeyboardInterrupt`. Только `Exception` в outer except.
- **Не делать `task.exception()` в /health без проверки `task.done()`** — бросает `InvalidStateError` если task ещё running. Достаточно `not task.done()`.
- **Не закрывать http_client / engine ДО `await reconciliation_task`** — reconciler может держать in-flight UoW при shutdown.
- **Не создавать второй `httpx.AsyncClient` для reconciler** — D-06 явно запрещает: разделяем singleton pool.
- **Не вызывать `uow.session.commit()` явно** — UoW коммитит на `__aexit__`; explicit commit нарушает Anti-Pattern 1.
- **Не использовать `SELECT DISTINCT ON (event_id)` PostgreSQL-специфичный синтаксис** — достаточно `.distinct()` на одной колонке; portable и чище.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry с backoff | Свой retry loop с `asyncio.sleep` | `make_retry_decorator(attempts=5, max_backoff=10.0)` из `facades/line_provider_client.py` | Уже реализован в P4; содержит правильный `_is_retryable` (только 5xx/TransportError, не 4xx) |
| Row locking при concurrent settle/cancel | Явный `SELECT ... FOR UPDATE` + проверка | `BetRepository.get_pending_locked(event_id)` из P5 | Уже реализован с `SKIP LOCKED` + status filter; interactor `cancel_bets_for_event` просто вызывает его |
| EventLookup в reconciler | Новый HTTP client | `HttpEventLookup` конструктор с новыми params | Уже параметризован `(http_client, attempts, max_backoff)` |
| Structured logging в background task | Самодельный logger | `structlog.get_logger().bind(task="reconciliation")` | Уже настроен в P1; `bind()` возвращает bound logger |

**Key insight:** Фаза 6 — почти полностью **composition** слоев P3-P5. Новый production-код минимален: `reconciliation_loop` + `_run_tick` + `_reconcile_event` (< 80 строк).

---

## Common Pitfalls

### Pitfall 1: `ALTER TYPE ADD VALUE` внутри транзакции
**What goes wrong:** `AlembicError: ERROR: ALTER TYPE ... ADD VALUE cannot run inside a transaction block` при `alembic upgrade head`.
**Why it happens:** Async Alembic env.py открывает транзакцию через `connection.run_sync(do_run_migrations)` → `context.begin_transaction()`.
**How to avoid:** Завернуть в `op.get_context().autocommit_block()` (Alembic официальный API). [VERIFIED: Context7]
**Warning signs:** `psycopg2.errors.ActiveSqlTransaction: ALTER TYPE ... ADD VALUE cannot run inside a transaction block`

### Pitfall 2: `task.done() == True` немедленно после создания (но до первого await)
**What goes wrong:** Health check возвращает 503 при первом запросе после startup.
**Why it happens:** Если `reconciliation_loop` бросает `TypeError` или `NameError` до первого `await`, task завершается немедленно.
**How to avoid:** Первый `await asyncio.sleep(interval_s)` — самый ранний await в loop; если до него возникает ошибка, это programming bug, не transient error. Покрыть unit-тестом.
**Warning signs:** Task завершается за < 1 секунду после создания.

### Pitfall 3: CancelledError не re-raise в inner except
**What goes wrong:** Reconciler игнорирует shutdown — `task.cancel()` не прерывает loop; shutdown зависает на `await reconciliation_task`.
**Why it happens:** В Python 3.10, `CancelledError` — подкласс `BaseException`, а **не** `Exception`. Значит `except Exception` его не поймает — это хорошо. Но если написать `except Exception: pass` без явного `except asyncio.CancelledError: raise`, а `CancelledError` брошен в `await asyncio.sleep`, он пропагируется через `except Exception` (не поймается), что корректно. Однако, если в `_run_tick` происходит другой `await`, который тоже может получить `CancelledError`, и там есть `try/except Exception`, то `CancelledError` снова не поймается — всё хорошо. Ловушка: если кто-то добавляет `except BaseException` — тогда `CancelledError` поглотится.
**How to avoid:** D-10 явно прописывает `except asyncio.CancelledError: raise` — следовать буквально.
**Warning signs:** `asyncio.wait_for(shutdown, timeout=5)` истекает.

### Pitfall 4: `scalars()` vs `all()` для SELECT DISTINCT одной колонки
**What goes wrong:** `get_pending_event_ids` возвращает `list[Row]` вместо `list[UUID]`.
**Why it happens:** `result.all()` возвращает `list[Row]`; нужно `result.scalars().all()`.
**How to avoid:** Всегда `session.execute(stmt).scalars().all()` для single-column SELECT.
**Warning signs:** `TypeError: UUID expected, got Row` в reconciler.

### Pitfall 5: Второй httpx.AsyncClient для reconciler
**What goes wrong:** Утечка соединений; два connection pool'а к line-provider.
**Why it happens:** Кажется логичным создать отдельный client для reconciler с другим timeout.
**How to avoid:** D-06: `HttpEventLookup(http_client=app.state.line_provider_http_client, attempts=5, max_backoff=10.0)` — тот же pool.
**Warning signs:** Два `httpx.AsyncClient` в lifespan.

### Pitfall 6: `task.exception()` в /health без `task.done()` проверки
**What goes wrong:** `InvalidStateError: Exception is not set` если task ещё running.
**Why it happens:** `task.exception()` бросает `InvalidStateError` пока task не завершён.
**How to avoid:** D-13: `reconciler_ok = not reconciliation_task.done()` — достаточно; не вызывать `.exception()`.
**Warning signs:** 500 Internal Server Error на `/health`.

### Pitfall 7: Read-only UoW и commit semantics
**What goes wrong:** `get_pending_event_ids` вызывает `uow.session.commit()` или выходит из UoW через exception.
**Why it happens:** Неправильное понимание Anti-Pattern 1 — "repo не коммитит" но UoW коммитит при `__aexit__` без исключения.
**How to avoid:** D-11 прямо говорит: read-only UoW для `get_pending_event_ids` отдельный — `async with uow:` только читает, UoW commit не вредит (нет writes), но логика верна. `BetRepository.get_pending_event_ids` — метод без flush/commit (Anti-Pattern 1 preserved).

---

## Code Examples

Verified patterns from official sources и существующей кодовой базы:

### get_pending_event_ids implementation

```python
# Source: SQLAlchemy 2.0 docs (VERIFIED: Context7 /websites/sqlalchemy_en_20) + existing bets.py pattern
async def get_pending_event_ids(self) -> list[UUID]:
    """SELECT DISTINCT event_id FROM bets WHERE status='PENDING'.

    D-01: read-only; no commit/flush. Anti-Pattern 1 preserved.
    """
    result = await self._session.execute(
        select(Bet.event_id)
        .where(Bet.status == BetStatus.PENDING)
        .distinct()
    )
    return list(result.scalars().all())
```

Паттерн идентичен `get_pending_locked` но без `with_for_update(skip_locked=True)` и с `.distinct()`.

### cancel_bets_for_event implementation

```python
# Source: D-04 из CONTEXT.md + паттерн settle_bets_for_event.py (VERIFIED: codebase)
async def cancel_bets_for_event(
    uow: AsyncUnitOfWork,
    *,
    event_id: UUID,
    cancelled_via: Literal["reconciler"],
) -> CancelResult:
    cancelled_at = datetime.now(timezone.utc)
    async with uow:
        bets = await uow.bets.get_pending_locked(event_id)
        if not bets:
            log.info("cancel.noop", event_id=str(event_id), reason="no PENDING bets")
            return CancelResult(
                event_id=event_id,
                cancelled_count=0,
                cancelled_bet_ids=[],
                cancelled_via=cancelled_via,
                cancelled_at=cancelled_at,
            )
        bet_ids = [b.id for b in bets]
        await uow.session.execute(
            update(Bet)
            .where(Bet.id.in_(bet_ids))
            .values(
                status=BetStatus.CANCELLED,
                settled_at=func.now(),
                settled_via=cancelled_via,
            )
        )
        log.info(
            "cancel.committed",
            event_id=str(event_id),
            cancelled_count=len(bet_ids),
            reason="line_provider_404",
        )
        return CancelResult(
            event_id=event_id,
            cancelled_count=len(bet_ids),
            cancelled_bet_ids=bet_ids,
            cancelled_via=cancelled_via,
            cancelled_at=cancelled_at,
        )
```

### Alembic migration 0003

```python
# Source: alembic.sqlalchemy.org/en/latest/api/runtime.html (VERIFIED: Context7)
from alembic import op

revision = "0003_bet_status_cancelled"
down_revision = "0002_bets_settled_columns"

def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE betstatus ADD VALUE IF NOT EXISTS 'cancelled'")

def downgrade() -> None:
    pass  # PG ENUM DROP VALUE не поддерживается без pересоздания type
```

### asyncio.create_task в lifespan (Python 3.10)

```python
# Source: Python 3.10 stdlib (VERIFIED: .venv/bin/python)
reconciliation_task: asyncio.Task[None] = asyncio.create_task(
    reconciliation_loop(app, interval_s=settings.reconciliation_interval_s),
    name="reconciliation",
)
app.state.reconciliation_task = reconciliation_task
```

Тип `asyncio.Task[None]` — важен для mypy strict mode.

### Shutdown с suppress

```python
# Source: Python 3.10 contextlib.suppress (VERIFIED: .venv/bin/python)
from contextlib import suppress

reconciliation_task.cancel()
with suppress(asyncio.CancelledError):
    await reconciliation_task
```

### /health с 4-й проверкой

```python
# Source: паттерн из entrypoints/api/health.py (VERIFIED: codebase)
reconciler_task: asyncio.Task[None] = cast(
    "asyncio.Task[None]", request.app.state.reconciliation_task
)
reconciler_ok = not reconciler_task.done()

# В теле ответа при degraded:
"reconciler": "ok" if reconciler_ok else "dead"
```

### Тип аннотации для Task в mypy strict

```python
# Важно для mypy strict mode: Task — generic, нужно параметризовать
import asyncio
from typing import cast

# В deps.py:
def get_reconciliation_task(request: Request) -> "asyncio.Task[None]":
    return cast("asyncio.Task[None]", request.app.state.reconciliation_task)

ReconciliationTaskDep = Annotated["asyncio.Task[None]", Depends(get_reconciliation_task)]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.ensure_future` | `asyncio.create_task` | Python 3.7 | `create_task` принимает `name=` (Python 3.7+), явнее и типобезопаснее |
| `try/finally` без `suppress` | `with suppress(CancelledError): await task` | Python 3.4 contextlib | Чище чем `try/except CancelledError: pass` в `finally` |
| `ALTER TYPE ADD VALUE` без autocommit | `op.get_context().autocommit_block()` | Alembic 0.8.6 | `autocommit_block` добавлен специально для PG DDL вне транзакции |

**Deprecated/outdated:**
- `task.cancel()` без `await task` — task не считается завершённым, lifespan может закрыть engine до того, как task реально остановится.
- `except Exception: pass` в outer loop — скрывает реальные ошибки; нужен `log.exception`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `asyncio.Task[None]` корректно типизируется в mypy strict без импорта из `__future__` | Code Examples | mypy ошибка типизации; fix — добавить `from __future__ import annotations` (уже везде используется в codebase) |
| A2 | `postgresql.ENUM` в SQLAlchemy автоматически принимает новое значение после `ALTER TYPE ADD VALUE` без изменения ORM | Architecture Patterns | Может потребоваться явный `autoload_with=engine` или `ENUM.create()` вызов; на практике SQLAlchemy 2.0 с Python Enum использует string-значения и не кэширует PG-тип — скорее всего работает без изменений ORM |
| A3 | В тесте D-23 Сценарий 2 `monkeypatch.setattr(RabbitEventBus, "publish", AsyncMock())` достаточно для подавления publish без перезапуска LP testcontainer | Testing | Может потребоваться другой подход если `RabbitEventBus` не напрямую атрибут класса или если publish вызывается через экземпляр, а не через класс |

**Если таблица неполна:** Утверждения A1-A3 — единственные не верифицированные через инструменты в этой сессии.

---

## Open Questions

1. **Размещение `reconciliation.py`: `entrypoints/` vs `messaging/`**
   - Что мы знаем: CONTEXT.md рекомендует `entrypoints/reconciliation.py`; `messaging.py` содержит consumer (FastStream router)
   - Что неясно: нет принципиальной разницы с точки зрения Python imports
   - Recommendation: `entrypoints/reconciliation.py` — жизненный цикл (background task) ближе к lifespan, чем к messaging. Паттерн: `entrypoints/` = всё что касается lifecycle + HTTP + AMQP entry points.

2. **Класс `Reconciler` vs функции**
   - Что мы знаем: CONTEXT.md упоминает как discretion; D-10/D-11 дают функциональный вариант
   - Что неясно: class может быть чище для тестов (inject зависимости через `__init__`)
   - Recommendation: Planner решает; функциональный вариант (`reconciliation_loop` + `_run_tick` + `_reconcile_event`) проще и симметричен с consumer handler в `messaging.py` (тоже plain functions).

3. **`monkeypatch` для D-23 Сценарий 2**
   - Что мы знаем: `line_provider/entrypoints/messaging.py` содержит `RabbitEventBus` + `RabbitRouter`; `set_event_state` interactor вызывает `event_bus.publish`
   - Что неясно: Конкретный путь для monkeypatch — `line_provider.facades.event_bus.RabbitEventBus.publish` или иначе
   - Recommendation: Planner или implementor проверит конкретный import path по факту реализации P5; в тесте можно использовать `unittest.mock.patch("line_provider.facades.event_bus.RabbitEventBus.publish", AsyncMock())` как контекстный менеджер.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10 | Runtime | ✓ | 3.10.20 | — |
| asyncio.create_task | reconciliation_loop | ✓ | stdlib | — |
| contextlib.suppress | lifespan shutdown | ✓ | stdlib | — |
| SQLAlchemy 2.0 async | get_pending_event_ids | ✓ | 2.0.49 | — |
| Alembic 1.18 | migration 0003 | ✓ | 1.18.4 | — |
| PostgreSQL 16 (testcontainers) | integration tests | ✓ | 16-alpine | — |
| RabbitMQ 4.2 (testcontainers) | e2e tests | ✓ | 4.2-management-alpine | — |
| tenacity 9.1 | make_retry_decorator | ✓ | 9.1.4 | — |
| structlog 25.5 | logging | ✓ | 25.5.0 | — |

[VERIFIED: pyproject.toml + uv.lock + testcontainers в tests/conftest.py]

**Missing dependencies with no fallback:** нет.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.1.0 |
| Config file | `pyproject.toml` (`asyncio_mode = "auto"`, `pythonpath = ["src"]`) |
| Quick run command | `uv run pytest tests/bet_maker/test_cancel_bets_for_event.py tests/bet_maker/test_reconciliation.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BM-12 SC#1 | Message dropped → reconciler settles PENDING bets within interval | e2e | `pytest tests/bet_maker/test_reconciliation_e2e.py -x -q` | ❌ Wave 0 |
| BM-12 SC#2 | Worker survives transient errors — loop never exits silently | unit | `pytest tests/bet_maker/test_reconciliation.py::TestReconcilerErrorIsolation -x -q` | ❌ Wave 0 |
| BM-12 SC#3 | /health 503 if task.done() | integration | `pytest tests/bet_maker/test_health.py::TestHealthReconciler -x -q` | ❌ Wave 0 |
| BM-12 SC#4 | Reconciler + consumer concurrent → exactly one settled status | integration | `pytest tests/bet_maker/test_reconciliation_concurrent.py -x -q` | ❌ Wave 0 |
| QA-08 SC#5 | E2E drop-publish → WON via reconciler within one interval | e2e | `pytest tests/bet_maker/test_reconciliation_e2e.py -x -q` | ❌ Wave 0 |
| BM-12 cancel-branch | 404 from LP → CANCELLED bets | unit | `pytest tests/bet_maker/test_cancel_bets_for_event.py -x -q` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/bet_maker/ -x -q --ignore=tests/bet_maker/test_reconciliation_e2e.py --ignore=tests/bet_maker/test_reconciliation_concurrent.py`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/bet_maker/test_cancel_bets_for_event.py` — covers BM-12 cancel-branch (D-19)
- [ ] `tests/bet_maker/test_reconciliation.py` — covers BM-12 SC#2, loop error isolation (D-20)
- [ ] `tests/bet_maker/test_reconciliation_concurrent.py` — covers BM-12 SC#4 (D-22)
- [ ] `tests/bet_maker/test_reconciliation_e2e.py` — covers BM-12 SC#1 + QA-08 SC#5 (D-23)
- [ ] `tests/bet_maker/test_health.py` — добавить `TestHealthReconciler` класс (D-21)

---

## Security Domain

> security_enforcement не установлен явно — включён по умолчанию.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — reconciler internal background task |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A — не добавляет новых endpoints (кроме расширения /health) |
| V5 Input Validation | yes | `EventSnapshot` frozen Pydantic (уже реализован в P4); `CancelResult` / `SettleResult` frozen Pydantic |
| V6 Cryptography | no | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Reconciler бесконечно loop при LP недоступен | DoS (self) | `max_backoff=10s` в tenacity + per-event error isolation (D-11); httpx.Timeout(5.0) уже в singleton client |
| Log injection через event_id в reconciler log | Tampering | structlog JSONRenderer автоматически экранирует; event_id передаётся через `str(event_id)` |
| Phantom task в /health после паники | Information Disclosure | `task.done()` не раскрывает внутренних деталей; exception не логируется в response body |

---

## Sources

### Primary (HIGH confidence)
- Context7 `/websites/alembic_sqlalchemy` — `autocommit_block()` для `ALTER TYPE ADD VALUE` — **HIGH**
- Context7 `/websites/sqlalchemy_en_20` — `select().distinct()` + `scalars().all()` pattern — **HIGH**
- `src/bet_maker/interactors/settle_bets_for_event.py` — паттерн cancel interactor (codebase) — **HIGH**
- `src/bet_maker/repositories/bets.py` — паттерн `get_pending_locked` (codebase) — **HIGH**
- `src/bet_maker/entrypoints/lifespan.py` — точная точка extension для lifespan (codebase) — **HIGH**
- `src/bet_maker/entrypoints/api/health.py` — точная точка extension для /health (codebase) — **HIGH**
- `alembic/versions/20260515_0001_bets_initial.py` + `20260518_0002_bets_settled_columns.py` — паттерны существующих миграций (codebase) — **HIGH**
- `tests/bet_maker/test_settle.py` + `test_e2e_rabbitmq.py` — паттерны тестов (codebase) — **HIGH**
- `.venv/bin/python -c "import asyncio; ..."` — Python 3.10.20 asyncio API (VERIFIED) — **HIGH**
- `src/bet_maker/settings/config.py` — `reconciliation_interval_s` уже существует (codebase) — **HIGH**

### Secondary (MEDIUM confidence)
- Python 3.10 stdlib `contextlib.suppress` + `asyncio.CancelledError` — common knowledge, верифицировано через REPL

### Tertiary (LOW confidence)
- A2 (ASSUMED): SQLAlchemy ENUM auto-accept новых PG значений без ORM change — не верифицировано через инструменты в этой сессии

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact на Phase 6 |
|-----------|-------------------|
| Python 3.10.20 — фиксировано | `asyncio.create_task(name=...)` доступен с 3.7; `asyncio.CancelledError` — подкласс `BaseException` (не `Exception`) — важно для try/except порядка |
| FastAPI 0.136 | lifespan extension через `@asynccontextmanager` — текущий паттерн |
| SQLAlchemy 2.0 async, asyncpg | `select().distinct()` через `AsyncSession.execute()` |
| Полностью асинхронное взаимодействие | Reconciler только `async def`; никакого blocking I/O |
| pydantic-settings 2.14 | Три новых поля в `BetMakerSettings` через `Field()` |
| structlog 25.5 JSON logging | `log.bind(task="reconciliation")` + `log.exception(...)` в except |
| tenacity 9.1.4 | `make_retry_decorator` factory reuse |
| pytest 9.0 + pytest-asyncio 1.1 `asyncio_mode="auto"` | `@pytest.mark.asyncio(loop_scope="session")` на class-уровне |
| mypy strict | `asyncio.Task[None]` explicit type; `Literal["reconciler"]` в `cancelled_via`; `cast()` в deps.py |
| ruff zero warnings | Все импорты отсортированы; docstrings на публичных функциях |
| Хранение событий line-provider только in-memory | Reconciler не ожидает PG в line-provider; GET /event/{id} — единственный способ получить state |
| docker-compose.yml не меняется | `RECONCILIATION_INTERVAL_S` настраивается через ENV; default 30s достаточен |

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — все библиотеки уже присутствуют в lockfile и верифицированы через grep
- Architecture: HIGH — все паттерны взяты из существующего кода P3-P5; минимум новых концепций
- Pitfalls: HIGH — критический Pitfall 1 (ALTER TYPE в транзакции) верифицирован через Context7; остальные — из известных asyncio/SQLAlchemy паттернов
- Testing: HIGH — все fixture уже существуют в `tests/conftest.py` и `tests/bet_maker/conftest.py`; только stub-файлы нужны

**Research date:** 2026-05-18
**Valid until:** 2026-06-18 (стабильный стек, нет fast-moving компонентов)
