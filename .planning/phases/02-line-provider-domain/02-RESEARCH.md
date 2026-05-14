# Phase 2: line-provider domain — Research

**Researched:** 2026-05-14
**Domain:** Async FastAPI domain layer на in-memory store; HTTP CRUD; стек поднят в P1.
**Confidence:** HIGH (decisions из CONTEXT.md и фиксированные конвенции P1 закрывают почти все варианты; LOW-зоны выделены явно в Open Questions).

## Summary

Phase 2 — это «толстый» доменный слой `line-provider` поверх каркаса P1. Технические компоненты (FastAPI 0.136.1, Pydantic 2.13.4, structlog, pytest 9.0.3 + pytest-asyncio 1.1.0) уже стоят, новых runtime-зависимостей нет. CONTEXT.md (D-01..D-20) фиксирует API, состав модулей, семантику store/state-machine и шаблон EventBus-фасада, готового к подмене в P5. Архитектурно фаза — это применение шаблона «entrypoints → interactors/selectors → infrastructure → schemas/helpers/facades», утверждённого в `.planning/research/ARCHITECTURE.md` §«line_provider — paste-ready tree».

Главные технические риски P2: (1) **тест-фикстура `client` не триггерит lifespan** — без `LifespanManager` (`asgi-lifespan`) `app.state.event_bus` / `app.state.event_store` остаются неинициализированными и DI-функции упадут; (2) **порядок mutate → publish** должен быть структурно заложен сейчас (commit→publish в interactor), иначе P5 потребует рефакторинга; (3) **снимок vs ссылка** на возврат из store: `frozen=True` моделей Pydantic v2 устраняет внешнюю мутацию, но требует осознанной дисциплины (D-16/D-17). State-machine — простейший case-statement; ловушек нет.

**Primary recommendation:** Реализовать структуру строго по D-01..D-20: `infrastructure/store/in_memory.py` (dict + `asyncio.Lock`, snapshot-возврат frozen Pydantic), `helpers/state_machine.py` (чистая функция), `facades/event_bus.py` (Protocol + NoopEventBus), `facades/deps.py` (`Depends(get_store|get_event_bus)` через `Request.app.state`), `interactors/{create_event,set_event_state}.py` (mutate → publish), `selectors/{list_active_events,get_event_by_id}.py`, `schemas/{events,messages}.py` (один enum `EventState` — single source of truth), `entrypoints/api/events.py` (4 роута). **Тест-инфраструктуру обновить:** добавить `asgi-lifespan>=2.1,<3` в dev-deps и переписать fixture `client` через `LifespanManager` — без этого все integration-тесты P2 будут падать на `AttributeError: app.state.event_bus`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**HTTP-API контракт**
- **D-01:** API из трёх mutating-эндпоинтов + двух read:
  - `POST /event` — create only. Тело: `EventCreate {event_id: UUID4, coefficient: Decimal, deadline: datetime}` (state неявно `NEW` — клиент не присылает). Ответ: 201 + `EventRead`. На дубль event_id → 409.
  - `PUT /event/{event_id}` — update only. Тело: `EventUpdate {coefficient: Decimal, deadline: datetime, state: EventState}` (full replace кроме event_id). Ответ: 200 + `EventRead`. Если события нет → 404. Запрещённый state-переход → 422.
  - `GET /event/{event_id}` — 200 + `EventRead`; 404 если нет.
  - `GET /events` — 200 + `list[EventRead]`; только активные (`deadline > now AND state == NEW`).
  - `GET /health` — 200 `{"status":"ok"}`.
- **D-02:** `PATCH` не используется — все мутации через POST (создание) и PUT (обновление, включая state-change). State-change в P5 публикует AMQP-сообщение из `interactors/set_event_state.py`, который дёргается в обработчике PUT при обнаружении NEW→FINISHED_*.

**event_id**
- **D-03:** `event_id: UUID4`. Клиент генерирует и присылает в POST body. Pydantic-валидация типа (`Annotated[UUID, ...]`); store при `add` выкидывает `EventAlreadyExistsError` → 409. Idempotent: повтор POST с тем же id → 409.
- **D-04:** `event_id` иммутабелен после создания. В PUT тело не содержит `event_id` (id берётся из URL). Если клиент пришлёт его в теле — Pydantic `extra="forbid"` отрежет 422.
- **D-05:** **Расхождение с REQUIREMENTS LP-02 ("event_id (str)")** — приоритет за CONTEXT.md. Планировщик в первом плане P2 должен синхронизировать REQUIREMENTS.md LP-02 (str → UUID4). Также `EventFinishedMessage.event_id` в P5 и `bets.event_id` в P3 — оба `UUID`. Архитектурный документ `ARCHITECTURE.md` локально использует `int` в примерах — устаревший пример, не контракт.

**Семантика обновления (PUT)**
- **D-06:** PUT мутирует все поля кроме event_id: `coefficient`, `deadline`, `state`. Полное replace-тело — частичных PATCH-апдейтов нет.
- **D-07:** `deadline > now` валидируется **только на POST** (create). На PUT любой deadline допустим.
- **D-08:** State-machine: разрешён только `NEW → FINISHED_WIN`, `NEW → FINISHED_LOSE`, и no-op `state == current_state`. Любые остальные → 422 с `{"detail":"state transition <X>→<Y> not allowed"}`.
- **D-09:** На PUT с no-op state — успех 200, поля coefficient/deadline обновляются. `event_bus.publish` НЕ вызывается (только на реальный переход на терминальное состояние).
- **D-10:** `coefficient` и `deadline` валидируются Pydantic-схемой одинаково в POST и PUT: `coefficient: Annotated[Decimal, condecimal(gt=0, decimal_places=2)]`, `deadline: datetime` (UTC-aware).

**EventBus facade (P5-ready)**
- **D-11:** `src/line_provider/facades/event_bus.py`:
  - `class EventBus(Protocol)`: `async def publish(self, message: EventFinishedMessage, *, routing_key: str) -> None: ...`
  - `class NoopEventBus(EventBus)`: логирует `event_bus.publish.noop` через structlog (P2 default).
  - `EventBusDep = Annotated[EventBus, Depends(get_event_bus)]` — provider возвращает `app.state.event_bus`.
- **D-12:** `src/line_provider/interactors/set_event_state.py`:
  - Сначала `await store.update(event_id, ...)` (in-memory commit под `asyncio.Lock`).
  - После успешного commit — `await event_bus.publish(EventFinishedMessage(...), routing_key=f"event.finished.{outcome}")` ТОЛЬКО при NEW→FINISHED_*.
  - Порядок строго: commit → publish (Anti-Pattern 2).
- **D-13:** В P2 `schemas/messages.py` уже создаётся с финальным `EventFinishedMessage` (Pydantic v2 `ConfigDict(frozen=True, extra="forbid")`, `schema_version: int = 1`). `event_id` в schema — `UUID`.
- **D-14:** `app.state.event_bus = NoopEventBus()` устанавливается в `entrypoints/lifespan.py` после `configure_structlog`. P5 подменит на `RabbitEventBus(broker=router.broker)` без изменений в interactor.

**In-memory store**
- **D-15:** Один `asyncio.Lock` на инстанс `InMemoryEventStore` — гранулярность глобальная. Все мутации (`add`, `update`, `replace`) под `async with self._lock`. Чистые чтения (`get_by_id`, `list_active`) без лока — возвращают snapshot.
- **D-16:** Store возвращает **snapshots, не ссылки**. Все методы возвращают `Event` (frozen Pydantic v2) или `list[Event]`. Внутри store — `dict[UUID, Event]`.
- **D-17:** `Event` модель в `schemas/events.py` — frozen Pydantic v2 (`ConfigDict(frozen=True)`). Поля: `event_id: UUID`, `coefficient: Decimal`, `deadline: datetime`, `state: EventState`. Pydantic v2 by default JSON-сериализует UUID/Decimal/datetime.

**Тесты**
- **D-18:** Unit-тесты (без HTTP): state_machine (таблица переходов), in_memory_store (add/update/get/list_active + concurrent под `asyncio.gather`), interactors (create_event, set_event_state с фейк-EventBus + проверка порядка commit→publish), selectors (с monkey-patched `utc_now()` через `helpers/time` или `freezegun`).
- **D-19:** Integration-тесты на API через `client` fixture из `tests/line_provider/conftest.py`:
  - happy path POST→GET→PUT→GET; 409 на дубль; 404 на отсутствующее; 422 на reverse-transition; 422 на coefficient ≤ 0; 422 на deadline в прошлом (только POST).
  - `list /events` фильтрует завершённые и просроченные.
- **D-20:** Тесты НЕ проверяют реальную публикацию AMQP. Проверяется только что `NoopEventBus.publish` был вызван с правильным `EventFinishedMessage` через `AsyncMock` или собственный `FakeEventBus`-список.

### Claude's Discretion
- Точный набор Pydantic-валидаторов (`@field_validator` vs `condecimal` vs `Annotated[..., AfterValidator]`) — выбрать стилистически единый вариант.
- Конкретный тип конструктора `Event` (Pydantic vs `dataclass(frozen=True)`). Pydantic предпочтительнее.
- Точная сигнатура `InMemoryEventStore` (методы `replace` vs `update` vs `upsert`).
- Структура `helpers/state_machine.py` (set transitions / dict / pattern match).
- 200 vs 201 на PUT — выбираю 200 (replace existing, не create).
- `EventState` enum location — `schemas/events.py` или `schemas/messages.py`. **Обе схемы должны импортировать один enum** (single source of truth).

### Deferred Ideas (OUT OF SCOPE)
- **Реальная AMQP-публикация в `set_event_state`** — P5 (LP-06).
- **Deep-pings PG/RMQ в `/health`** — P5 (LP-07 полностью).
- **AsyncAPI docs (`/asyncapi`)** — P7 (DOC-04); FastStream активируется в P5.
- **OpenAPI tags/summaries/examples для событий** — P7 (DOC-01..04).
- **Pagination и фильтры на `GET /events`** — не в скоупе тестового задания.
- **Idempotency-Key header на `POST /event`** — REL/API-01 deferred per REQUIREMENTS.md (v2).
- **Per-event асинхронные локи** — оптимизация для масштаба, не нужна в P2.
- **Sequence/auto-increment event_id** — отвергнуто в пользу UUIDv4.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LP-01 | Хранение событий in-memory под `asyncio.Lock`. | §«In-memory store pattern» — single-lock + snapshot-возврат, Anti-Pattern 6 mitigation; код-шаблон в §«Code Examples». |
| LP-02 | Модель `Event`: event_id, coefficient (Decimal 2dp >0), deadline, state. **Note D-05:** event_id = UUID4 (override REQUIREMENTS «str»). | §«Pydantic v2 patterns» — `Annotated[Decimal, Field(gt=0, decimal_places=2)]`, `frozen=True`. |
| LP-03 | `POST /event` (create) + `PUT /event/{id}` (update со state-change по state-machine). | §«HTTP API design» — детальные сигнатуры routes, 201/200/409/404/422; §«State machine placement». |
| LP-04 | `GET /event/{id}` — 200 / 404. | §«HTTP API design» + §«Selector layer». |
| LP-05 | `GET /events` — список активных (deadline>now AND state==NEW). | §«Selector layer» — pure read через `utc_now()` injection для тестов. |
| LP-07 | `GET /health` (deep-ping → P5; в P2 — стаб 200). | §«Health endpoint policy» — liveness-only в P2, документировать сейчас. |
| LP-08 | Валидация бизнес-инвариантов: coefficient >0, deadline в будущем при создании, запрет reverse state transitions. | §«State machine placement» (422 в interactor, не Pydantic) + §«Pydantic v2 patterns» (coefficient/deadline schema). |
| QA-04 | Unit-тесты на каждый слой (interactors/selectors/helpers/store). | §«Validation Architecture» — детальная карта unit/integration; §«Test fixture critical fix». |
| QA-05 | Integration-тесты на API через httpx AsyncClient. | §«Test fixture critical fix» — **обязательная замена `client` fixture на LifespanManager**. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP request/response (routes) | API (`entrypoints/api/events.py`) | — | Boundary; thin handlers, делегируют в interactor/selector. |
| Business decision: разрешён ли state transition | Helper (`helpers/state_machine.py`) | Interactor (вызов + 422) | Чистая функция вне DI — легко юнит-тестировать таблицей. |
| Mutation orchestration (validate → store.commit → publish) | Interactor (`interactors/{create_event,set_event_state}.py`) | Facade (`event_bus`) | Use-case oriented; собирает store + facade + state_machine. |
| Read-only query (single + active list) | Selector (`selectors/{get_event_by_id,list_active_events}.py`) | Store (read) | Pure read pipeline; без mutate, без побочных эффектов. |
| Concurrency protection (Lock) | Infrastructure (`infrastructure/store/in_memory.py`) | — | Лок инкапсулирован в store; interactor не знает про него. |
| Pub/sub abstraction (P2 noop, P5 RabbitMQ) | Facade (`facades/event_bus.py`) | — | Один Protocol + 2 реализации (Noop/Rabbit); подмена в lifespan. |
| Wiring & singletons | Lifespan + Depends (`facades/deps.py`) | — | `app.state.event_store/event_bus` создаются в lifespan, читаются через `Request.app.state` в Depends-функциях. |
| Schema validation (HTTP body, AMQP body) | Schemas (`schemas/events.py`, `schemas/messages.py`) | — | Pydantic v2 = единственный источник правды для контрактов. |
| Cross-cutting: request_id | Middleware (P1 уже сделано, не трогаем) | — | A7 double-clear pattern, переиспользуется. |

## Standard Stack

### Core (всё уже в `pyproject.toml`)
| Library | Version (pinned) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.10.20 | Runtime — фиксировано ТЗ. `UUID4`, `StrEnum`, `match` доступны. | TZ-fixed. `[VERIFIED: pyproject.toml + .python-version]` |
| FastAPI | 0.136.1 (>=0.115,<0.137) | HTTP framework, OpenAPI генератор, native Pydantic v2. | TZ-recommended; авто-lifespan с FastStream доступен из коробки. `[VERIFIED: pyproject.toml]` |
| Pydantic | 2.13.4 (>=2.13,<3) | Схемы HTTP+AMQP, `frozen=True`, `extra="forbid"`. | `[VERIFIED: pyproject.toml]`. Native Decimal/UUID/datetime serialization. |
| pydantic-settings | 2.14.1 | Settings (already wired в P1, не трогаем). | `[VERIFIED: pyproject.toml]` |
| structlog | 25.5.0 | Логи с contextvars; bind в interactor'ах под текущий request_id. | `[VERIFIED: pyproject.toml]` |
| uvicorn[standard] | 0.46.0 | ASGI server (P1, не трогаем). | `[VERIFIED: pyproject.toml]` |

### Dev / Test
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 (>=9.0,<10) | Test runner. | Все тесты. `[VERIFIED: pyproject.toml]` |
| pytest-asyncio | 1.1.0 (>=1.1,<2) | Async tests; `asyncio_mode=auto` уже выставлен в pyproject из P1. | Все async-тесты. `[VERIFIED: pyproject.toml]` |
| pytest-cov | 7.1.0 | Покрытие; threshold в CI (≥80% общий, ≥85% domain) — но enforcement формально в P7 (QA-09). | По всем тестам. `[VERIFIED: pyproject.toml]` |
| httpx | 0.28.1 | `AsyncClient(transport=ASGITransport(app=...))` для integration-тестов. | Все API-integration тесты. `[VERIFIED: pyproject.toml]` |
| mypy | 2.1.0 strict + pydantic.mypy | Тип-чекер; P2 код должен пройти `mypy --strict` (QA-01 enforce, ownership в P7). | На каждом коммите P2. `[VERIFIED: pyproject.toml]` |
| ruff | 0.15.12 | Lint + format (E,W,F,I,B,UP,N,SIM,ASYNC,PL,RUF). | На каждом коммите. `[VERIFIED: pyproject.toml]` |

### НОВАЯ ЗАВИСИМОСТЬ — обязательная для P2
| Library | Version | Purpose | Why required |
|---------|---------|---------|--------------|
| **asgi-lifespan** | `>=2.1,<3` | `LifespanManager` обёртка вокруг ASGI-app в тестах — триггерит `lifespan` async-context-manager, без которого `app.state.event_store` / `app.state.event_bus` не инициализируются при работе через `ASGITransport`. | **БЛОКЕР**: FastAPI docs прямо предупреждают: «`AsyncClient` does NOT automatically trigger lifespan events». `[CITED: fastapi.tiangolo.com/advanced/async-tests/]`. Существующая fixture `tests/line_provider/conftest.py` сейчас работает только потому, что `/health` не читает `app.state`. Как только P2-routes начнут читать `request.app.state.event_store` — fixture упадёт с `AttributeError`. |

**Installation:**
```bash
uv add --dev "asgi-lifespan>=2.1,<3"
```

**Version verification (asgi-lifespan):**
```bash
# Latest published: 2.1.0 (2023-10), maintained by florimondmanca (homepage of asgi-lifespan).
# Spec works with pytest-asyncio 1.x (asyncio API, not trio-only).
```
`[CITED: github.com/florimondmanca/asgi-lifespan + fastapi.tiangolo.com/advanced/async-tests/]`

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asgi-lifespan` + `LifespanManager` | Вручную звать `await app.router.startup()` / `shutdown()` | Хрупко, не задокументировано как public API, обходит lifespan-asynccontextmanager. **Reject.** |
| `asgi-lifespan` | `from starlette.testclient import TestClient` (синхронный) | TestClient синхронен, ломает асинхронный стек, не совместим с `asyncio_mode=auto`. **Reject.** |
| `Annotated[Decimal, Field(gt=0, decimal_places=2)]` | `condecimal(gt=0, decimal_places=2)` | `condecimal` помечен «discouraged» в Pydantic 2.x docs, будет deprecated в Pydantic 3.0. `[CITED: pydantic.dev/docs/validation/.../types/]`. **Recommendation: Annotated style.** |
| `dataclass(frozen=True)` для `Event` | Pydantic `BaseModel(frozen=True)` | Dataclass не даёт `model_validate_json`/`model_dump`. Pydantic стоит копейки, единая модель для store + HTTP response. **Recommendation: Pydantic.** |
| `freezegun` для tests | monkey-patch `helpers.time.utc_now` | `helpers/time.utc_now()` уже централизован (P1, `src/config/time.py`). Monkey-patch проще, без новой зависимости. **Recommendation: monkey-patch.** Если freezegun понадобится в P5/P6 — добавить тогда. |
| `EventState` в `schemas/messages.py` (как `EventTerminalState` из ARCHITECTURE.md) | `EventState` в `schemas/events.py`, импорт в `messages.py` | Domain enum (NEW/FINISHED_WIN/FINISHED_LOSE) логически принадлежит к Event-схеме. `EventTerminalState` (только terminal states) можно вычислить как subset. **Recommendation: `EventState` в `schemas/events.py`, экспорт; в `messages.py` либо отдельный `EventTerminalState`, либо переиспользование двух терминальных значений.** |

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                           line-provider (P2)                          │
│                                                                       │
│   HTTP request ──▶ RequestContextMiddleware (P1, A7 double-clear)    │
│                            │                                          │
│                            ▼                                          │
│              entrypoints/api/events.py  (4 routes)                   │
│                   │                                                   │
│                   │ Depends(get_store), Depends(get_event_bus)        │
│                   ▼                                                   │
│         ┌─────────────────────────────┐                              │
│         │  selectors/  (pure reads)    │  ◀── GET /event/{id}        │
│         │                              │  ◀── GET /events            │
│         └──────────┬───────────────────┘                              │
│                    │                                                  │
│                    ▼                                                  │
│         ┌─────────────────────────────┐                              │
│         │  interactors/                │  ◀── POST /event            │
│         │   create_event               │  ◀── PUT  /event/{id}       │
│         │   set_event_state            │                              │
│         └─┬─────────────────┬─────────┘                              │
│           │                 │                                         │
│  helpers/state_machine    facades/event_bus.py                       │
│  (pure: is_transition_    Protocol EventBus + NoopEventBus           │
│   allowed) — raise 422    publish() — no-op в P2,                    │
│                           RabbitEventBus в P5                         │
│           │                 ▲                                         │
│           │                 │ commit → publish (D-12)                 │
│           ▼                 │                                         │
│   infrastructure/store/in_memory.py                                  │
│      InMemoryEventStore(_data: dict[UUID, Event],                    │
│                         _lock: asyncio.Lock)                          │
│      add / update / get / list_active — snapshots only (D-16)        │
│                                                                       │
│   Lifespan (P1 + D-14): create InMemoryEventStore() + NoopEventBus() │
│                         → app.state.event_store / app.state.event_bus│
└──────────────────────────────────────────────────────────────────────┘

External:
   structlog → JSON stdout (P1)
   /health → 200 stub (P2; deep-pings → P5)
```

### Recommended Project Structure

```
src/line_provider/
├── __init__.py
├── __main__.py                          # P1 (не трогаем)
├── app.py                               # P1: add `app.include_router(events.router)`
├── settings/config.py                   # P1 (не трогаем в P2)
├── entrypoints/
│   ├── lifespan.py                      # P1 + D-14: добавить event_store/event_bus в app.state
│   ├── middleware.py                    # P1 (не трогаем)
│   └── api/
│       ├── health.py                    # P1 (не трогаем; LP-07 deep-ping → P5)
│       └── events.py                    # ★ НОВЫЙ: 4 routes (POST/PUT/GET-id/GET-list)
├── facades/                             # ★ НОВЫЙ пакет
│   ├── __init__.py
│   ├── event_bus.py                     # Protocol EventBus + NoopEventBus
│   └── deps.py                          # Depends-providers (get_store, get_event_bus)
├── interactors/                         # ★ НОВЫЙ пакет
│   ├── __init__.py
│   ├── create_event.py                  # validate + store.add (no publish)
│   └── set_event_state.py               # state_machine + store.update + publish (NEW→FIN_*)
├── selectors/                           # ★ НОВЫЙ пакет
│   ├── __init__.py
│   ├── get_event_by_id.py
│   └── list_active_events.py            # deadline>now AND state==NEW
├── helpers/                             # ★ НОВЫЙ пакет
│   ├── __init__.py
│   └── state_machine.py                 # is_transition_allowed(current, new) -> bool
├── schemas/                             # ★ НОВЫЙ пакет
│   ├── __init__.py
│   ├── events.py                        # EventState, Event (frozen), EventCreate, EventUpdate, EventRead
│   └── messages.py                      # EventFinishedMessage (frozen, extra="forbid", schema_version)
├── infrastructure/                      # ★ НОВЫЙ пакет
│   ├── __init__.py
│   └── store/
│       ├── __init__.py
│       └── in_memory.py                 # InMemoryEventStore + EventNotFoundError / EventAlreadyExistsError
└── py.typed                              # P1

tests/line_provider/
├── conftest.py                          # P1 + ★ ОБНОВИТЬ: LifespanManager wrapper
├── test_health.py                       # P1 (не трогаем)
├── test_state_machine.py                # ★ unit (helpers)
├── test_in_memory_store.py              # ★ unit (infrastructure)
├── test_create_event.py                 # ★ unit (interactor + FakeEventBus + real store)
├── test_set_event_state.py              # ★ unit (interactor + FakeEventBus + real store)
├── test_selectors.py                    # ★ unit (selectors + monkey-patched utc_now)
└── test_event_routes.py                 # ★ integration (httpx, full route matrix)
```

### Pattern 1: In-Memory Event Store с `asyncio.Lock` + snapshot-возвратом

**What:** Single async lock защищает все write-операции, чтения возвращают frozen-копию.
**When to use:** P2 single-process line-provider; D-15/D-16 фиксируют гранулярность.
**Example:**

```python
# src/line_provider/infrastructure/store/in_memory.py
# Source: ARCHITECTURE.md §«Anti-Pattern 6», CONTEXT.md D-15/D-16
from __future__ import annotations
import asyncio
from uuid import UUID

from line_provider.schemas.events import Event, EventState


class EventAlreadyExistsError(Exception):
    """Raised when add() called with an event_id that already exists."""


class EventNotFoundError(Exception):
    """Raised when update()/get() called with a missing event_id."""


class InMemoryEventStore:
    """Async-safe in-memory store for events.

    - Mutations (add/update) hold a single asyncio.Lock (D-15).
    - Reads (get_by_id/list_active) do NOT hold the lock — they only call
      dict.get / list(self._data.values()), both atomic at the bytecode level
      in CPython, and return frozen Pydantic snapshots (D-16).
    - Stored values are frozen Event models; callers cannot mutate them.
    """

    def __init__(self) -> None:
        self._data: dict[UUID, Event] = {}
        self._lock = asyncio.Lock()

    async def add(self, event: Event) -> Event:
        async with self._lock:
            if event.event_id in self._data:
                raise EventAlreadyExistsError(str(event.event_id))
            self._data[event.event_id] = event
            return event

    async def update(self, event_id: UUID, *, coefficient, deadline, state) -> tuple[Event, EventState]:
        """Returns (new_event, previous_state) so interactor can decide
        whether to publish (D-12 — NEW->FINISHED_* only)."""
        async with self._lock:
            current = self._data.get(event_id)
            if current is None:
                raise EventNotFoundError(str(event_id))
            previous_state = current.state
            new_event = current.model_copy(update={
                "coefficient": coefficient,
                "deadline": deadline,
                "state": state,
            })
            self._data[event_id] = new_event
            return new_event, previous_state

    async def get_by_id(self, event_id: UUID) -> Event | None:
        # Lock-free: dict.get is atomic; Event is frozen — caller cannot mutate.
        return self._data.get(event_id)

    async def list_all(self) -> list[Event]:
        # Snapshot of values; subsequent mutations don't affect returned list.
        return list(self._data.values())
```

**Почему `update()` возвращает `(event, previous_state)`:**
`interactors/set_event_state.py` принимает решение «публиковать или нет» на основании факта **реального перехода NEW→FINISHED_*** (D-09 no-op state НЕ публикуется). Чтобы interactor мог это решить без второго round-trip в store, store возвращает кортеж под локом — пара (new, previous) консистентна. Это структурно готово к P5: P5 добавит `await event_bus.publish(...)` в interactor, никакого рефакторинга store не потребуется.

### Pattern 2: Pure state-machine как helper

**What:** Чистая функция, без классов и DI.
**When to use:** Любой переход состояния в P2; вызывается из interactor.
**Example:**

```python
# src/line_provider/helpers/state_machine.py
# Source: CONTEXT.md D-08
from __future__ import annotations
from line_provider.schemas.events import EventState


_ALLOWED: frozenset[tuple[EventState, EventState]] = frozenset({
    (EventState.NEW, EventState.FINISHED_WIN),
    (EventState.NEW, EventState.FINISHED_LOSE),
})


def is_transition_allowed(current: EventState, new: EventState) -> bool:
    """Return True if transition is allowed.

    Allowed:
      - current == new  (no-op; D-09 — coefficient/deadline mutated, publish skipped)
      - NEW -> FINISHED_WIN | FINISHED_LOSE
    Everything else (FINISHED_* -> NEW, FINISHED_WIN <-> FINISHED_LOSE) is forbidden.
    """
    if current == new:
        return True
    return (current, new) in _ALLOWED
```

**Где репортить 422:** в `interactors/set_event_state.py`, бросая `HTTPException(422, ...)` или (чище) свой `TransitionForbiddenError`, который `entrypoints/api/events.py` ловит и переводит в `HTTPException`. Pydantic-валидатор НЕ годится — он не имеет доступа к `current_state` (Pydantic валидирует только тело запроса, current_state живёт в store). **Recommendation:** доменное исключение в interactor + перевод в HTTPException на уровне route handler (или `exception_handler` на уровне `build_app`). FastAPI 422 идиоматичен для семантической ошибки тела/состояния. `[CITED: ARCHITECTURE.md §Pattern, CONTEXT.md D-08]`

### Pattern 3: EventBus facade (Protocol + Noop) — P5-ready

**What:** `Protocol` контракт + `NoopEventBus` для P2; в P5 добавляется `RabbitEventBus`.
**When to use:** Все mutate-interactor'ы, требующие сайд-эффекта «event finished». В P2 публикация — no-op (только лог).
**Example:**

```python
# src/line_provider/facades/event_bus.py
# Source: CONTEXT.md D-11, ARCHITECTURE.md §«Anti-Pattern 5»
from __future__ import annotations
from typing import Protocol

import structlog

from line_provider.schemas.messages import EventFinishedMessage


class EventBus(Protocol):
    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None: ...


class NoopEventBus:
    """P2 default: log only, no AMQP. Replaced by RabbitEventBus in P5 (D-14)."""

    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None:
        structlog.get_logger().info(
            "event_bus.publish.noop",
            routing_key=routing_key,
            event_id=str(message.event_id),
            new_state=message.new_state.value,
            schema_version=message.schema_version,
        )
```

```python
# src/line_provider/facades/deps.py
# Source: WebFetch fastapi.tiangolo.com/advanced/middleware/ — Pattern 1: Request.app.state
from __future__ import annotations
from typing import Annotated

from fastapi import Depends, Request

from line_provider.facades.event_bus import EventBus
from line_provider.infrastructure.store.in_memory import InMemoryEventStore


def get_store(request: Request) -> InMemoryEventStore:
    return request.app.state.event_store


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus


StoreDep = Annotated[InMemoryEventStore, Depends(get_store)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
```

### Pattern 4: Interactor с commit→publish ordering (Anti-Pattern 2 mitigation)

```python
# src/line_provider/interactors/set_event_state.py
# Source: CONTEXT.md D-12, ARCHITECTURE.md §«Anti-Pattern 2»
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from line_provider.facades.event_bus import EventBus
from line_provider.helpers.state_machine import is_transition_allowed
from line_provider.infrastructure.store.in_memory import InMemoryEventStore, EventNotFoundError
from line_provider.schemas.events import Event, EventState
from line_provider.schemas.messages import EventFinishedMessage, EventTerminalState


class TransitionForbiddenError(Exception):
    def __init__(self, current: EventState, new: EventState) -> None:
        self.current = current
        self.new = new
        super().__init__(f"state transition {current.value}->{new.value} not allowed")


_TERMINAL_TO_ROUTING: dict[EventState, str] = {
    EventState.FINISHED_WIN: "event.finished.win",
    EventState.FINISHED_LOSE: "event.finished.lose",
}


async def set_event_state(
    store: InMemoryEventStore,
    event_bus: EventBus,
    *,
    event_id: UUID,
    coefficient: Decimal,
    deadline: datetime,
    new_state: EventState,
) -> Event:
    # 1) Read current state (needed for state-machine check + ordering).
    #    Do this lock-free; if a concurrent writer mutates between get and update,
    #    update() inside the lock will still see consistent (current, previous_state).
    current = await store.get_by_id(event_id)
    if current is None:
        raise EventNotFoundError(str(event_id))
    if not is_transition_allowed(current.state, new_state):
        raise TransitionForbiddenError(current.state, new_state)

    # 2) Commit to in-memory store FIRST (D-12 / Anti-Pattern 2 / R9).
    new_event, previous_state = await store.update(
        event_id,
        coefficient=coefficient,
        deadline=deadline,
        state=new_state,
    )

    # 3) Publish ONLY on actual NEW -> FINISHED_* transition (D-09).
    if previous_state == EventState.NEW and new_state in _TERMINAL_TO_ROUTING:
        await event_bus.publish(
            EventFinishedMessage(
                event_id=new_event.event_id,
                new_state=EventTerminalState(new_state.value),
                coefficient=new_event.coefficient,
                occurred_at=new_event.deadline,  # or utc_now(); planner picks
                correlation_id=...,  # planner: bind from request_id or structlog contextvars
            ),
            routing_key=_TERMINAL_TO_ROUTING[new_state],
        )
    return new_event
```

**Note for planner:** Между `store.get_by_id()` (шаг 1) и `store.update()` (шаг 2) есть TOCTOU-окно — но `update()` под локом перепроверяет state по фактически записанному значению через возвращаемое `previous_state`, поэтому реально race условий не возникает (state-machine-check сделан до lock, но если за это время состояние изменилось, `previous_state` это поймает и решение про publish будет корректным). **Альтернатива** — встроить state-machine check внутрь `store.update()` под локом; чище, но смешивает infrastructure с domain. **Recommendation:** оставить проверку в interactor, как выше, с явным комментарием про TOCTOU; для P2 single-process этого достаточно. Если planner предпочтёт встроить check в store — пометить как осмысленное отступление от слоистости.

### Pattern 5: HTTP routes как тонкий слой

```python
# src/line_provider/entrypoints/api/events.py
# Source: CONTEXT.md D-01..D-04, D-06..D-10
from __future__ import annotations
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from line_provider.facades.deps import StoreDep, EventBusDep
from line_provider.infrastructure.store.in_memory import EventAlreadyExistsError, EventNotFoundError
from line_provider.interactors.create_event import create_event
from line_provider.interactors.set_event_state import set_event_state, TransitionForbiddenError
from line_provider.schemas.events import EventCreate, EventRead, EventUpdate
from line_provider.selectors.get_event_by_id import get_event_by_id
from line_provider.selectors.list_active_events import list_active_events


router = APIRouter(tags=["events"])


@router.post("/event", status_code=status.HTTP_201_CREATED, response_model=EventRead)
async def create_event_route(body: EventCreate, store: StoreDep) -> EventRead:
    try:
        event = await create_event(store, body=body)
    except EventAlreadyExistsError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    return EventRead.model_validate(event, from_attributes=True)


@router.put("/event/{event_id}", status_code=status.HTTP_200_OK, response_model=EventRead)
async def update_event_route(
    event_id: UUID,
    body: EventUpdate,
    store: StoreDep,
    event_bus: EventBusDep,
) -> EventRead:
    try:
        event = await set_event_state(
            store, event_bus,
            event_id=event_id,
            coefficient=body.coefficient,
            deadline=body.deadline,
            new_state=body.state,
        )
    except EventNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    except TransitionForbiddenError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"state transition {exc.current.value}->{exc.new.value} not allowed",
        )
    return EventRead.model_validate(event, from_attributes=True)


@router.get("/event/{event_id}", response_model=EventRead)
async def get_event_route(event_id: UUID, store: StoreDep) -> EventRead:
    event = await get_event_by_id(store, event_id=event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return EventRead.model_validate(event, from_attributes=True)


@router.get("/events", response_model=list[EventRead])
async def list_events_route(store: StoreDep) -> list[EventRead]:
    events = await list_active_events(store)
    return [EventRead.model_validate(e, from_attributes=True) for e in events]
```

### Pattern 6: Pydantic v2 schemas

```python
# src/line_provider/schemas/events.py
# Source: CONTEXT.md D-10, D-17; WebFetch pydantic.dev/docs/.../types/
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class EventState(StrEnum):
    NEW = "NEW"
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"


Coefficient = Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)]
# max_digits=8 → up to 999999.99 — больше, чем нужно для коэффициентов (обычно < 1000.00),
# но даёт запас. Planner may tune.


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    coefficient: Coefficient
    deadline: AwareDatetime  # enforces tz-aware datetime; rejects naive


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coefficient: Coefficient
    deadline: AwareDatetime  # D-07: no `> now` validation on PUT
    state: EventState


class Event(BaseModel):
    """Internal frozen domain entity stored in InMemoryEventStore (D-17)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_id: UUID
    coefficient: Coefficient
    deadline: AwareDatetime
    state: EventState


class EventRead(BaseModel):
    """HTTP response model — mirror of Event but not frozen (FastAPI serializes both fine)."""
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    coefficient: Coefficient
    deadline: AwareDatetime
    state: EventState
```

```python
# src/line_provider/schemas/messages.py
# Source: CONTEXT.md D-13; ARCHITECTURE.md Pattern 2 (event_id corrected to UUID per D-05)
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class EventTerminalState(StrEnum):
    """Subset of EventState — only terminal values; published in EventFinishedMessage."""
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"


class EventFinishedMessage(BaseModel):
    """AMQP body for routing key event.finished.{win,lose}.

    Created in P2 (D-13) but only PUBLISHED starting P5. Schema is single
    source of truth — bet-maker's schemas/messages.py mirrors this byte-for-byte.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    event_id: UUID
    new_state: EventTerminalState
    coefficient: Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)]
    occurred_at: AwareDatetime
    correlation_id: str
```

**Decision: validator `deadline > now` для `EventCreate`** — лучше всего через `@field_validator` или `Annotated[..., AfterValidator]`. Validator должен использовать `helpers/time.utc_now()` (или `src/config/time.py`'s `utc_now`) чтобы тесты могли monkey-patch без `freezegun`. **Pitfall:** не использовать `datetime.utcnow()` (deprecated с Python 3.12), не использовать наивные datetime.

```python
# src/line_provider/schemas/events.py (дополнение)
from pydantic import AfterValidator

from config.time import utc_now


def _deadline_in_future(v: datetime) -> datetime:
    if v <= utc_now():
        raise ValueError("deadline must be in the future")
    return v


FutureDeadline = Annotated[AwareDatetime, AfterValidator(_deadline_in_future)]


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    coefficient: Coefficient
    deadline: FutureDeadline  # only on POST (D-07)
```

### Pattern 7: Test fixture — критическое исправление (LifespanManager)

**Текущий `tests/line_provider/conftest.py` НЕ запускает lifespan.** Это не вылавливалось в P1, потому что `/health` не читал `app.state`. Как только P2-routes начнут читать `request.app.state.event_store` через `Depends(get_store)`, **все integration-тесты упадут с AttributeError**.

```python
# tests/line_provider/conftest.py — ОБНОВЛЁННАЯ версия
# Source: fastapi.tiangolo.com/advanced/async-tests/ (LifespanManager pattern)
from __future__ import annotations
from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from line_provider.app import build_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = build_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
```

Альтернатива (без `asgi-lifespan`): вручную вызвать `await app.router.startup()` / `shutdown()` — **отвергнуто**: обходит lifespan-asynccontextmanager (D-14 ставит `app.state.event_bus` именно в lifespan).

**Также:** в integration-тестах часто нужен прямой доступ к `app.state.event_store` (например, чтобы пред-заполнить состояние через store напрямую, а не через POST). Добавить fixture `event_store`:

```python
@pytest_asyncio.fixture
async def event_store(client: AsyncClient) -> InMemoryEventStore:
    """Access the same store the client uses. client fixture must yield first."""
    # client.transport is httpx.ASGITransport; its app attribute is our FastAPI app.
    return client._transport.app.state.event_store  # type: ignore[attr-defined]
```

(Это «приватный» способ; чище — менять `client` fixture на yield-tuple `(client, app)`. Planner picks.)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State-machine | Custom enum-of-tuples класс с регистрацией переходов | Чистая функция + frozenset (см. Pattern 2) | На 3 состояния и 2 разрешённых перехода библиотека (`transitions`, `python-statemachine`) — overkill. |
| HTTP error responses | Свой формат ошибок | `HTTPException(status_code, detail)` FastAPI | Стандартный contract; OpenAPI генерирует автоматически. RFC7807 deferred per REQUIREMENTS v2 (API-04). |
| Decimal parsing | Самим парсить строки | `Annotated[Decimal, Field(gt=0, decimal_places=2)]` Pydantic v2 | Pydantic v2 принимает `"10.00"` и `Decimal("10.00")`, отвергает float автоматически. `[VERIFIED: pydantic v2 docs]` |
| UUID validation | Регулярки | `Annotated[UUID, ...]` (Pydantic v2 принимает UUID + строку) | Pydantic парсит обе формы. |
| In-memory store | Раскатывать Redis для тестового задания | Dict + asyncio.Lock | ТЗ явно требует in-memory line-provider. Out-of-scope (REQUIREMENTS «Out of Scope» — Redis cache событий). |
| AMQP publish stub в тестах | Городить mock-broker | `NoopEventBus` + `AsyncMock` / собственный `FakeEventBus`-список | D-20 явно фиксирует — реальный AMQP только в P5. |
| Lifespan triggering в тестах | Самим звать `app.router.startup()` | `asgi_lifespan.LifespanManager` | Это public-API замены TestClient'а для FastAPI async; рекомендован FastAPI docs. `[CITED: fastapi.tiangolo.com/advanced/async-tests/]` |
| Validation: `deadline > now` | Логика в route handler / interactor | Pydantic `AfterValidator` с `utc_now()` | 422 идёт автоматически до интерактора; единое место для теста. |
| Frozen domain entity | Самописный `__setattr__` | Pydantic `ConfigDict(frozen=True)` | Pydantic v2 встроенный; raise `ValidationError` на присваивание. |

**Key insight:** Весь P2 — это применение стандартных Pydantic v2 + FastAPI + asyncio примитивов. Единственная «архитектурная» абстракция — `EventBus` Protocol, и она существует только ради P5 (D-11/D-14). Не вводить дополнительных слоёв; не вводить generic-репозитория (он нужен только bet-maker — ARCHITECTURE.md §«Structure Rationale»: «repositories/ is bet-maker-only»).

## Runtime State Inventory

> P2 — greenfield для line-provider domain (in-memory only). Раздел не применим в полном объёме, но проверяем явно:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None.** In-memory `dict` живёт только в процессе. Перезапуск контейнера полностью обнуляет state. `[VERIFIED: ТЗ + ARCHITECTURE.md §«line-provider only store»]` | Документировать в README (P7) как известное свойство test-task scope. |
| Live service config | **None.** Никаких внешних сервисов P2 не настраивает (RabbitMQ exchange/queue — P5). | — |
| OS-registered state | **None.** Сервис стартует через `python -m line_provider` под docker-compose; никаких systemd/cron/Task Scheduler. | — |
| Secrets/env vars | **None new.** P1 уже завёл `LINE_PROVIDER_RABBITMQ_URL` через pydantic-settings — не используется в P2 (NoopEventBus). | — |
| Build artifacts | **None.** Hatch editable install сидит на src/line_provider; новые модули подхватятся `uv sync --frozen` без переустановки. | — |

**Nothing requires migration** — это чистый extension существующего скелета P1.

## Common Pitfalls

### Pitfall 1: Тестовая fixture не триггерит lifespan
**What goes wrong:** Все integration-тесты P2 падают с `AttributeError: 'State' object has no attribute 'event_store'`, потому что lifespan не запустился и `app.state.event_store` / `app.state.event_bus` остались неинициализированными.
**Why it happens:** `httpx.ASGITransport(app=...)` НЕ триггерит ASGI lifespan-события (документировано FastAPI). `tests/line_provider/conftest.py` сейчас работает только потому, что `/health` не читает `app.state`.
**How to avoid:** Добавить `asgi-lifespan>=2.1,<3` в dev-dependencies; обернуть build_app() в `LifespanManager(app)` внутри fixture `client` (Pattern 7).
**Warning signs:** Любой тест, который попадает на route, использующий `Depends(get_store)`, кидает AttributeError при первом запуске.

### Pitfall 2: Reverse state transition валидируется через Pydantic, а не interactor
**What goes wrong:** Попытка валидировать переход (NEW→FINISHED_WIN) на уровне `EventUpdate` Pydantic-схемы. Pydantic не знает `current_state` (он в store) — валидатор либо ничего не проверит, либо потребует пробрасывать contextvar, что хрупко.
**Why it happens:** Соблазн «всю валидацию в Pydantic».
**How to avoid:** State-machine — domain-логика, она в `helpers/state_machine.py` + interactor. 422 кидается через доменное исключение → HTTPException на уровне route (Pattern 4/5). Pydantic валидирует только тип `state: EventState` (любое из трёх значений).
**Warning signs:** `model_validator(mode='after')` пытается читать что-то снаружи модели.

### Pitfall 3: Decimal сериализуется как «10» вместо «10.00»
**What goes wrong:** Reviewer присылает `coefficient: "10"` → Pydantic принимает, store кладёт `Decimal("10")`, ответ — `"10"`. Хотя по ТЗ — «ровно 2 знака после запятой».
**Why it happens:** `decimal_places=2` в Pydantic v2 — это **верхний предел** scale при валидации, не enforcement точно 2 цифры. `Decimal("10")` имеет 0 decimal_places — проходит проверку «не более 2».
**How to avoid:** Либо валидатор требует `quantize(Decimal("0.01"))` (helper `helpers/money.py`-стиль), либо проверка «scale == 2» через `@field_validator` + `.as_tuple().exponent == -2`. **Recommendation:** quantize on input + serialize-time. `quantize` дешевле; результат всегда `"10.00"`. Pydantic v2 сериализует Decimal как строку — это правильно (Pitfall A4 в PITFALLS.md), но требует, чтобы внутреннее значение было уже quantized.
**Warning signs:** Тест-кейс `POST {"coefficient": "10"}` → `GET` возвращает `"10"`; reviewer пишет «нет 2 знаков».
**Note for planner:** ТЗ говорит «Decimal, ровно 2 знака». Решить — отвергать `"10"` со ссылкой на decimal_places, или принимать и quantize. **Я рекомендую quantize** (более user-friendly, эквивалентно по семантике хранения), но это **`[ASSUMED]`** трактовка ТЗ — занести в Open Questions.

### Pitfall 4: Naive datetime пройдёт валидацию
**What goes wrong:** `deadline: datetime` принимает наивный datetime; сравнение `deadline > utc_now()` (где `utc_now()` tz-aware) кинет `TypeError`.
**Why it happens:** Pydantic v2 принимает обе формы datetime по умолчанию.
**How to avoid:** Использовать `AwareDatetime` из `pydantic` (не из стандартного `datetime`) — это `Annotated[datetime, ...]` с валидатором, требующим tzinfo.
**Warning signs:** `TypeError: can't compare offset-naive and offset-aware datetimes` в логах.

### Pitfall 5: TOCTOU между get_by_id и update в interactor
**What goes wrong:** Два concurrent PUT на тот же event_id: оба читают current_state=NEW, оба проходят state-machine check, оба пишут — выигрывает последний, но первый думает что он сделал NEW→FINISHED_WIN и публикует.
**Why it happens:** state-machine check сделан до lock'а (см. Pattern 4).
**How to avoid:** Решение в store.update() — он возвращает `(new_event, previous_state)`, и interactor публикует **только если `previous_state == NEW`** (см. Pattern 4 шаг 3). Тогда оба concurrent PUT'а пройдут state-machine check, но второй увидит `previous_state == FINISHED_WIN` и **не опубликует** — что эквивалентно D-09 no-op semantic.
**Warning signs:** Concurrent test на gather видит больше одного publish'а.

### Pitfall 6: Lock-граница не закрывает «read+decision»
**What goes wrong:** Реакция на «оптимизацию»: «давайте читать без лока, а писать под локом» → потерянная апдейт-операция: PUT-A читает state=NEW, PUT-B читает state=NEW, оба пишут FINISHED.
**Why it happens:** Anti-Pattern 6 — read без lock, write под lock'ом, но read-decision-write — не атомарны.
**How to avoid:** В D-15 явно — мутация под локом, чтение без; **но** мутация обязана внутри лок-блока перепроверить предусловия по фактическому значению (см. Pattern 1 — `current = self._data.get(event_id)` внутри `async with self._lock`).
**Warning signs:** Concurrent test fails недетерминированно.

### Pitfall 7: structlog contextvars утечка между HTTP-запросами (A7)
**What goes wrong:** P1 middleware уже делает clear+bind+clear (A7 double-clear). Если в interactor добавить `bind_contextvars(event_id=...)` без clear на выходе, следующий запрос унаследует event_id.
**Why it happens:** structlog contextvars живут до явного clear; A7 fix именно про это.
**How to avoid:** В interactor'ах НЕ bind — пусть middleware держит request_id, в логах interactor'а оно появится автоматически. Если нужен event_id — `log.info("...", event_id=...)` без bind.
**Warning signs:** Логи второго запроса показывают event_id предыдущего.

### Pitfall 8: `event_id: UUID` в URL path и в body одновременно (D-04)
**What goes wrong:** Если `EventUpdate` имеет поле `event_id`, а в роуте `PUT /event/{event_id}` — это два источника правды, легко рассинхронизировать.
**Why it happens:** Соблазн положить полную модель в body.
**How to avoid:** D-04 явно — `EventUpdate` БЕЗ `event_id`; `extra="forbid"` отрежет если клиент пришлёт. event_id — только из path.
**Warning signs:** 422 на запросе с лишним полем — корректное поведение.

### Pitfall 9: `model_validate(event, from_attributes=True)` на frozen Pydantic
**What goes wrong:** `from_attributes=True` нужен для SQLAlchemy ORM-моделей; для Pydantic→Pydantic это no-op, но `model_validate(event)` работает.
**Why it happens:** Скопировано из bet-maker'овых паттернов.
**How to avoid:** В P2 можно проще: `EventRead(**event.model_dump())` или `EventRead.model_validate(event.model_dump())`. **Recommendation:** оставить `model_validate(event)` без `from_attributes` — Pydantic v2 умеет.

### Pitfall 10: `_TERMINAL_TO_ROUTING` ключ-зависимость от значения enum
**What goes wrong:** Конструируется routing key через `new_state.value.split('_')[-1].lower()` — magic; легко сломать переименованием enum.
**Why it happens:** Удобство «одна строка».
**How to avoid:** Явный mapping `dict[EventState, str]` (Pattern 4 — `_TERMINAL_TO_ROUTING`); единый источник правды.
**Warning signs:** В P5 при добавлении третьего terminal-state routing key собирается через подстроку.

## Code Examples

### Дополнительный пример: create_event interactor

```python
# src/line_provider/interactors/create_event.py
from __future__ import annotations

from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventCreate, EventState


async def create_event(store: InMemoryEventStore, *, body: EventCreate) -> Event:
    event = Event(
        event_id=body.event_id,
        coefficient=body.coefficient,
        deadline=body.deadline,
        state=EventState.NEW,
    )
    return await store.add(event)
```

### Дополнительный пример: list_active_events selector

```python
# src/line_provider/selectors/list_active_events.py
from __future__ import annotations

from config.time import utc_now
from line_provider.infrastructure.store.in_memory import InMemoryEventStore
from line_provider.schemas.events import Event, EventState


async def list_active_events(store: InMemoryEventStore) -> list[Event]:
    """LP-05: deadline > now AND state == NEW."""
    now = utc_now()
    return [
        e for e in await store.list_all()
        if e.state == EventState.NEW and e.deadline > now
    ]
```

### Дополнительный пример: пример unit-теста state-machine

```python
# tests/line_provider/test_state_machine.py
import pytest

from line_provider.helpers.state_machine import is_transition_allowed
from line_provider.schemas.events import EventState


@pytest.mark.parametrize(
    ("current", "new", "allowed"),
    [
        (EventState.NEW, EventState.FINISHED_WIN, True),
        (EventState.NEW, EventState.FINISHED_LOSE, True),
        (EventState.NEW, EventState.NEW, True),
        (EventState.FINISHED_WIN, EventState.NEW, False),
        (EventState.FINISHED_LOSE, EventState.NEW, False),
        (EventState.FINISHED_WIN, EventState.FINISHED_LOSE, False),
        (EventState.FINISHED_LOSE, EventState.FINISHED_WIN, False),
        (EventState.FINISHED_WIN, EventState.FINISHED_WIN, True),
        (EventState.FINISHED_LOSE, EventState.FINISHED_LOSE, True),
    ],
)
def test_is_transition_allowed(current: EventState, new: EventState, allowed: bool) -> None:
    """LP-08: state-machine table."""
    assert is_transition_allowed(current, new) is allowed
```

## State of the Art

| Old Approach | Current Approach (2026) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `from pydantic import condecimal; price: condecimal(...)` | `from typing import Annotated; price: Annotated[Decimal, Field(gt=0, decimal_places=2)]` | Pydantic 2.x deprecation notice — full removal in 3.0 | Использовать Annotated style. `[CITED: pydantic.dev]` |
| `datetime.utcnow()` (naive) | `datetime.now(timezone.utc)` (aware) | Python 3.12 deprecated `utcnow()` | `config/time.utc_now()` уже делает правильно (P1). |
| `httpx.Client(app=...)` (deprecated в httpx 0.27+) | `httpx.AsyncClient(transport=httpx.ASGITransport(app=...))` | httpx 0.28 (наша версия) | Используется уже в P1. |
| Sync `TestClient` для FastAPI | `httpx.AsyncClient + ASGITransport + LifespanManager` | FastAPI ≥0.100 async-first | LifespanManager обязателен для lifespan. |
| Pydantic v1 `Config: orm_mode=True` | Pydantic v2 `ConfigDict(from_attributes=True)` | Pydantic 2.0 (Jun 2023) | Уже в P1. |
| `pytest.mark.asyncio` | `asyncio_mode=auto` в pytest.ini + native `async def test_*` | pytest-asyncio 0.21+ | Уже включено в P1 pyproject. |

**Deprecated/outdated в материалах проекта:**
- ARCHITECTURE.md §Pattern 2: `event_id: int` в `EventFinishedMessage` — **OVERRIDDEN by CONTEXT.md D-05** на `UUID`.
- REQUIREMENTS.md LP-02: «event_id (str)» — **OVERRIDDEN by CONTEXT.md D-05** на `UUID4`. **Первый task P2-плана — синхронизировать REQUIREMENTS.md.**
- ARCHITECTURE.md §«line_provider — paste-ready tree»: `PATCH /events/{id}` — **OVERRIDDEN by CONTEXT.md D-02** на `PUT /event/{id}` (и `/event` вместо `/events` для одиночного).
- ARCHITECTURE.md §Phase 2: `POST /events`, `PATCH /events/{id}` — **OVERRIDDEN by CONTEXT.md D-01**.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Pydantic v2 `decimal_places=2` accepts `"10"` без `quantize` (т.е. валидирует «не более 2 цифр», не «ровно 2») | Pitfall 3, Pattern 6 | Если ТЗ строго требует «ровно 2» — нужен дополнительный валидатор или quantize. **`[ASSUMED]`** на основе общеизвестного поведения Pydantic v2; planner может уточнить через test или enforce quantize в helper. |
| A2 | ТЗ позволяет принимать `"10"` если внутренне quantize → `"10.00"` (vs строго отвергнуть) | Pitfall 3 | Можно интерпретировать ТЗ двояко. Я рекомендую quantize-on-input, но это **`[ASSUMED]`** трактовка. Discuss-phase решение нужно. |
| A3 | `model_copy(update={...})` на frozen Pydantic v2 возвращает новый объект без мутации текущего | Pattern 1 (`store.update()`) | Стандартное поведение Pydantic v2, **`[VERIFIED: Pydantic v2 docs]`**, но если frozen блокирует model_copy — нужен fallback `Event(**{**current.model_dump(), **updates})`. |
| A4 | `Event` хранится как frozen — это не блокирует FastAPI сериализацию для `EventRead` | Pattern 6 | Pydantic frozen блокирует setattr, не сериализацию. `[VERIFIED: pydantic docs]`. Низкий риск. |
| A5 | `Request.app.state.event_store` доступен синхронно (не async) внутри Depends-функции | Pattern 3 (`facades/deps.py`) | Стандартное FastAPI поведение. **`[VERIFIED: fastapi docs]`**. |
| A6 | `asgi-lifespan` 2.1.0 совместим с FastAPI 0.136 + pytest-asyncio 1.1.0 | Pattern 7 | API стабильный с 2.0 (2021). Возможен edge-case с FastAPI 0.136 lifespan — нужен реальный smoke-test первым тестом P2. Риск: средний; митигация — verify на первом задизайненом тесте. **`[ASSUMED]` для конкретной версионной пары**. |
| A7 | pytest-cov порог ≥85% для domain-кода — типичный bar для middle-уровня | Validation Architecture | QA-09 формально требует ≥80% общий, threshold в CI — P7. Конкретный bar для domain — **`[ASSUMED]`**, planner может выбрать другой. |
| A8 | `correlation_id` в `EventFinishedMessage` — можно взять request_id из structlog contextvars | Pattern 4 | Семантически логично — corellation_id связывает HTTP-запрос с AMQP-сообщением. Но **`[ASSUMED]`** — CONTEXT.md явно не фиксирует источник; planner может решить иначе (UUID на месте генерации, и т.д.). |

## Open Questions

1. **Strict «ровно 2 знака после запятой» vs «не более 2 + quantize»** (см. Pitfall 3, Assumption A1/A2)
   - What we know: ТЗ говорит «ровно 2 знака»; Pydantic v2 `decimal_places=2` валидирует «не более 2».
   - What's unclear: Принимать `"10"` и quantize'ить или отвергать с 422.
   - Recommendation: **Принимать + quantize** в `helpers/money.py` (стилистически совпадёт с bet-maker P3 — там тот же паттерн нужен). Документировать решение в плане. Discuss-phase явно не закрыло.

2. **Источник `correlation_id` для `EventFinishedMessage`** (см. Assumption A8)
   - What we know: D-13 фиксирует поле `correlation_id: str`; structlog уже binds request_id (P1, A7).
   - What's unclear: Брать ли request_id из contextvars, или генерить новый UUID в interactor.
   - Recommendation: Брать `request_id` из `structlog.contextvars.get_contextvars()` или (чище) принимать как параметр в interactor с дефолтом `uuid4().hex`. Тесты тогда могут pin'ить correlation_id явно.

3. **Концентрация валидаторов: один файл `helpers/validators.py` или inline в `schemas/events.py`**
   - What we know: `FutureDeadline`, `Coefficient` — переиспользуются.
   - What's unclear: Стилистика.
   - Recommendation: Inline в `schemas/events.py`, экспортировать `Coefficient`, `FutureDeadline` как Annotated-aliases. Простой и достаточно DRY.

4. **`utc_now()` injection vs monkey-patch для тестов selector**
   - What we know: `config/time.utc_now()` уже централизован (P1).
   - What's unclear: monkeypatch module attribute или явный DI параметра `now: datetime | None = None`.
   - Recommendation: monkeypatch (`monkeypatch.setattr("line_provider.selectors.list_active_events.utc_now", lambda: ...)`) — без DI-шума в production-API. Без `freezegun`.

5. **Доступ к `event_store` из integration-тестов (для arrange-phase setup)**
   - What we know: Pattern 7 предлагает `client._transport.app.state.event_store` — приватный API.
   - What's unclear: Хочется ли публичную fixture `event_store` параллельно `client`.
   - Recommendation: Сделать fixture yield-tuple или две fixtures с разделяемым app. Planner picks.

6. **`EventState` location: `schemas/events.py` vs `schemas/messages.py`**
   - What we know: D-Discretion явно оставляет на planner; обе схемы должны импортировать один enum.
   - Recommendation: `EventState` (полный enum: NEW + 2 terminal) — в `schemas/events.py`. `EventTerminalState` (subset) — в `schemas/messages.py`, со значениями, дублирующими 2 terminal. Альтернатива — один enum везде. Recommend: два enum'а; AMQP-схема не должна знать про NEW.

## Environment Availability

> P2 — pure-Python code/test phase, никаких новых системных зависимостей. Audit делается формально.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10 | Все исходники | ✓ | 3.10.20 (`.python-version` from P1) | — |
| uv | Установка зависимостей | ✓ | 0.11.14 (CI), local — у пользователя | — |
| Все runtime libs (fastapi, pydantic, structlog, …) | Реализация | ✓ | См. `pyproject.toml` (P1 lock) | — |
| pytest, pytest-asyncio, pytest-cov, httpx | Тесты | ✓ | См. `pyproject.toml` | — |
| **asgi-lifespan** | Pattern 7 — integration-тесты с lifespan | **✗** | — | Нельзя обойти — без него `app.state` недоступен в тестах. **Blocking** — добавить через `uv add --dev`. |

**Missing dependencies with no fallback:**
- `asgi-lifespan>=2.1,<3` — обязателен для QA-05 (integration-тесты P2). Первый task плана — `uv add --dev asgi-lifespan>=2.1,<3` и `uv lock --offline=false` (или `uv sync` чтобы пересобрать `uv.lock`).

**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.1.0 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options] asyncio_mode = "auto"`, `pythonpath = ["src"]`) — уже из P1 |
| Quick run command (одна фаза) | `uv run pytest tests/line_provider -q -x` |
| Full suite command | `uv run pytest -q --cov=src/line_provider --cov-report=term-missing` |
| Phase gate | Все P2-тесты зелёные + coverage ≥85% на `src/line_provider/` (см. Assumption A7 — порог ориентировочный, формальный enforce в P7) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| LP-01 (lock) | `InMemoryEventStore.add` под локом отвергает дубль; concurrent gather не теряет апдейты | unit | `pytest tests/line_provider/test_in_memory_store.py -q` | ❌ Wave 0 — создать |
| LP-01 (lock) | `store.update` под локом возвращает корректный `(new, previous_state)` при concurrent writes | unit | same | ❌ Wave 0 |
| LP-02 (model) | `EventCreate`/`EventUpdate`/`Event` поля и валидаторы; `extra="forbid"`; frozen | unit | `pytest tests/line_provider/test_schemas.py -q` (опционально — может слиться с in_memory_store тестами) | ❌ Wave 0 |
| LP-03 (POST) | `POST /event` 201 + EventRead | integration | `pytest tests/line_provider/test_event_routes.py::test_post_event_creates -q` | ❌ Wave 0 |
| LP-03 (POST 409) | дубль event_id → 409 | integration | same | ❌ Wave 0 |
| LP-03 (POST 422) | coefficient ≤ 0 → 422 | integration | same | ❌ Wave 0 |
| LP-03 (POST 422) | deadline в прошлом → 422 (D-07) | integration | same | ❌ Wave 0 |
| LP-03 (PUT 200) | `PUT /event/{id}` 200 + EventRead на корректный апдейт | integration | same | ❌ Wave 0 |
| LP-03 (PUT 404) | `PUT` на несуществующее → 404 (D-03 PUT не upsert) | integration | same | ❌ Wave 0 |
| LP-03 (PUT publish) | `PUT` NEW→FINISHED_WIN вызвал `event_bus.publish` с корректным routing key (D-12, D-20 — fake bus) | integration | `pytest tests/line_provider/test_event_routes.py::test_put_publishes_on_terminal -q` | ❌ Wave 0 |
| LP-04 (GET id) | 200 на существующее, 404 на отсутствующее | integration | `pytest tests/line_provider/test_event_routes.py::test_get_event_by_id -q` | ❌ Wave 0 |
| LP-05 (GET list) | возвращает только `state==NEW AND deadline>now` | integration | `pytest tests/line_provider/test_event_routes.py::test_list_active_events -q` | ❌ Wave 0 |
| LP-05 (selector unit) | фильтр deadline+state — pure-функция, monkey-patched `utc_now` | unit | `pytest tests/line_provider/test_selectors.py -q` | ❌ Wave 0 |
| LP-07 (/health) | 200 + `{"status":"ok"}` (P1 уже есть, не дублировать) | integration | `pytest tests/line_provider/test_health.py -q` | ✅ exists (P1) |
| LP-08 (state-machine) | таблица 9 переходов; NEW→FIN_* / no-op = True, остальное = False | unit | `pytest tests/line_provider/test_state_machine.py -q` | ❌ Wave 0 |
| LP-08 (PUT 422) | reverse transition → 422 + detail message | integration | `pytest tests/line_provider/test_event_routes.py::test_put_reverse_transition_422 -q` | ❌ Wave 0 |
| LP-08 (no-op state) | PUT с `state == current_state` → 200, publish НЕ вызван (D-09) | integration | `pytest tests/line_provider/test_event_routes.py::test_put_noop_state_no_publish -q` | ❌ Wave 0 |
| QA-04 (unit coverage) | state_machine + in_memory_store + interactors + selectors — все слои покрыты | unit suite | `pytest tests/line_provider -q --cov=src/line_provider --cov-report=term-missing` | ❌ Wave 0 (несколько файлов) |
| QA-05 (integration via httpx) | API integration tests через `httpx.AsyncClient(transport=ASGITransport)` + LifespanManager | integration | `pytest tests/line_provider/test_event_routes.py -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/line_provider -q -x`  (early-fail на первой проваленной).
- **Per wave merge:** `uv run pytest -q` (полный suite — P1 smoke + P2 unit + P2 integration).
- **Phase gate (verify-work):**
  - `uv run pytest -q --cov=src/line_provider --cov-report=term-missing`
  - `uv run mypy --strict src/line_provider`
  - `uv run ruff check src/line_provider tests/line_provider`
  - `uv run ruff format --check src/line_provider tests/line_provider`

### Failure-Mode Classes Covered

| Failure Mode | Test Layer | Notes |
|--------------|-----------|-------|
| Concurrent dict mutation (Anti-Pattern 6) | unit (`asyncio.gather(*[add(...)])` на store) | Проверяет не теряем апдейты под gather; не доказывает absence of races строго, но покрывает обычный регрессионный сценарий. |
| Reverse state transition | unit (state_machine) + integration (PUT 422) | Двойной слой — pure-функция + API. |
| Decimal validation edge cases | unit (Pydantic schema) + integration (POST 422) | `"10.123"`, `"-5.00"`, `"0"`, `""`, `"abc"`. |
| Deadline in past on POST | integration | Через monkey-patch `utc_now` чтобы зафиксировать «now». |
| Lifespan singleton sharing | integration (LifespanManager triggers; assertion: 2 concurrent клиента видят одни и те же события — не нужно специально, по построению; smoke на «route видит store» достаточно) | Implicitly covered. |
| TOCTOU concurrent PUT (Pitfall 5) | unit на interactor через `asyncio.gather` на set_event_state | Проверяет — только один publish при concurrent gather'е (через FakeEventBus.call_args_list). |
| commit→publish ordering (Anti-Pattern 2) | unit на interactor через FakeEventBus, который raises Exception | Проверяет: store изменился даже если publish упал. |
| Validate-don't-mutate (no-op state) | integration (PUT с state==current, publish NOT called) | D-09. |
| 404 на отсутствующее (GET/PUT) | integration | LP-04 + LP-03. |
| 409 на дубль POST | integration | D-03. |
| Schema strict (`extra="forbid"`) | unit + integration (POST/PUT с лишним полем → 422) | D-04, D-13. |
| AMQP message frozen + extra=forbid | unit на `EventFinishedMessage` | D-13. Лишнее поле → ValidationError. |
| Naive datetime отвергается | unit + integration | `AwareDatetime` валидатор. |

### Wave 0 Gaps (must exist before T-01)

- [ ] **DEV DEPENDENCY:** `uv add --dev "asgi-lifespan>=2.1,<3"` + commit обновлённого `uv.lock`.
- [ ] **FIXTURE UPGRADE:** `tests/line_provider/conftest.py` — обновить `client` fixture на `LifespanManager`-обёртку (Pattern 7). Существующие тесты `test_health.py` должны продолжать проходить.
- [ ] **NEW FILES (test files Wave 0):**
  - `tests/line_provider/test_state_machine.py` (LP-08 unit)
  - `tests/line_provider/test_in_memory_store.py` (LP-01 unit)
  - `tests/line_provider/test_create_event.py` или объединённый `test_interactors.py` (interactor unit)
  - `tests/line_provider/test_set_event_state.py` (interactor unit с FakeEventBus)
  - `tests/line_provider/test_selectors.py` (selector unit)
  - `tests/line_provider/test_event_routes.py` (integration, все 4 routes)
- [ ] **Optional:** `tests/line_provider/_fakes.py` или `conftest.py` — общий `FakeEventBus` фикстура с `published: list[tuple[EventFinishedMessage, str]]`.

## Sources

### Primary (HIGH confidence)
- `.planning/phases/02-line-provider-domain/02-CONTEXT.md` — D-01..D-20 (полная фиксация решений P2).
- `.planning/research/ARCHITECTURE.md` §«line_provider — paste-ready tree», §«Pattern 2 RabbitMQ topology», §«Pattern 4 Lifespan composition», §«Anti-Pattern 2», §«Anti-Pattern 5», §«Anti-Pattern 6», §«Suggested Build Order — Phase 2».
- `.planning/research/PITFALLS.md` §«A4 Decimal serialization», §«A7 structlog contextvars», §«R9 Reconciler races order», §«R12 Publish from DB transaction».
- `.planning/REQUIREMENTS.md` LP-01, LP-02 (с поправкой D-05), LP-03, LP-04, LP-05, LP-07, LP-08, QA-04, QA-05.
- `.planning/STATE.md` — P1 complete; lifespan/middleware/settings уже стоят.
- `CLAUDE.md` §«Technology Stack» — пины версий FastAPI 0.136.1, Pydantic 2.13.4, httpx 0.28.1, pytest 9.0.3.
- `src/line_provider/{app.py,entrypoints/lifespan.py,entrypoints/middleware.py,entrypoints/api/health.py,settings/config.py}` — фактический скелет P1.
- `tests/line_provider/{conftest.py,test_health.py}` — текущая тест-фикстура (требует upgrade).
- `pyproject.toml` — точные версии пинов (`fastapi>=0.115,<0.137`, `pydantic>=2.13,<3`, `httpx>=0.28,<0.29`, `pytest>=9.0,<10`, `pytest-asyncio>=1.1,<2`).

### Secondary (MEDIUM-HIGH confidence; cross-verified)
- WebFetch `fastapi.tiangolo.com/advanced/async-tests/` — **критический источник** для Pattern 7 / LifespanManager. Прямая цитата: «`AsyncClient` won't trigger lifespan events. … use `LifespanManager` from florimondmanca/asgi-lifespan».
- WebFetch `pydantic.dev/docs/validation/latest/api/pydantic/types/` — `Annotated[Decimal, Field(...)]` vs `condecimal()`; deprecation в 3.0.
- WebFetch `fastapi.tiangolo.com/advanced/events/` — lifespan async-context-manager + `app.state`.
- WebFetch `fastapi.tiangolo.com/advanced/middleware/` (косвенно) — `Request.app.state` pattern для Depends-провайдера.
- WebFetch `python-httpx.org/advanced/transports/` — ASGITransport pattern.

### Tertiary (LOW — flagged for validation)
- Assumption A1 (`decimal_places=2` accepts `"10"`) — общеизвестное Pydantic v2 поведение, не verified отдельным тестом. Низкий риск; смягчается через A2 quantize.
- Assumption A6 (`asgi-lifespan` 2.1 совместим с FastAPI 0.136 + pytest-asyncio 1.1) — известно работает с большинством сочетаний, но точная комбинация — на smoke-test первого теста P2.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — пины уже в pyproject; единственное новое — `asgi-lifespan`, его API стабильно с 2021.
- Architecture: **HIGH** — CONTEXT.md D-01..D-20 фиксирует почти всё; structure из ARCHITECTURE.md.
- Pitfalls: **HIGH** — LifespanManager gap (Pitfall 1) — главный технический риск, обоснован FastAPI docs. Decimal/Naive datetime/TOCTOU — стандартные ловушки Pydantic + asyncio.
- Test architecture: **HIGH** — карта Req→Test полная; единственный LOW — конкретный порог coverage (Assumption A7).
- State machine: **HIGH** — таблица из 3 состояний тривиальна.
- EventBus facade: **HIGH** — Protocol + Noop полностью покрывает P2 needs; P5 swap — одна строка в lifespan.

**Research date:** 2026-05-14
**Valid until:** ~2026-06-14 (30 days). Стек стабилен; единственный риск — выход новой минорной версии FastAPI с lifespan-breaking change, что крайне маловероятно.
