# Phase 5: RabbitMQ integration — Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 закрывает межсервисную интеграцию через RabbitMQ:

- **line-provider** заменяет `NoopEventBus` на `RabbitEventBus` и публикует `EventFinishedMessage` при терминальном переходе (`FINISHED_WIN` / `FINISHED_LOSE`) — точка вызова `event_bus.publish(...)` в `interactors/set_event_state.py` уже на месте (Phase 2 D-12, commit-before-publish).
- **bet-maker** поднимает RabbitMQ subscriber в том же процессе, что и HTTP API; декларирует свою queue + DLX + DLQ + bindings; через manual ack атомарно проводит `settle_bets_for_event` под `FOR UPDATE SKIP LOCKED`.
- `/health` расширяется: 503 при отказе PG **или** RabbitMQ **или** `subscriber_count == 0`.
- Контрактная защита: `EventFinishedMessage` дублируется byte-for-byte в обоих сервисах (`extra="forbid"`, `schema_version=1`) и сверяется CI-тестом.
- Poison-сообщения (`ValidationError`, `DecodeError`, `schema_version != 1`, `IntegrityError`) сразу маршрутизируются в `bet_maker.events.finished.dlq` через выделенный DLX `bsw.events.dlx`. Transient (`OperationalError`, `connection_invalidated`, `TimeoutError`) ретраятся `tenacity` 3 раза с экспоненциальным backoff внутри handler — без broker-cycling.

**Out of scope (Phase 5):**
- Reconciliation job — Phase 6 (используем тот же `settle_bets_for_event` interactor, поэтому D-17/D-13 заложены под `settled_via='reconciler'`).
- DLQ inspection / replay endpoints — Management UI достаточен для приёмки.
- Publisher confirms — FastStream defaults; researcher оценит включение явно в RESEARCH.md.
- Quorum queue / cluster — single-node demo, classic durable достаточно.

</domain>

<decisions>
## Implementation Decisions

### RMQ Topology & Ownership

- **D-01:** Topic exchange `bsw.events` (`durable=True`, `auto_delete=False`). Топик расширяем под будущие event-классы без переименования (R5 запрещает редактировать args существующего exchange).
- **D-02:** Main queue `bet_maker.events.finished` — classic durable. Single-node docker-compose, quorum overkill.
- **D-03:** Разделённая владельность declare:
  - line-provider lifespan declare-ит `bsw.events` (topic, durable).
  - bet-maker lifespan declare-ит `bet_maker.events.finished` + DLX `bsw.events.dlx` + DLQ `bet_maker.events.finished.dlq` + binding в `bsw.events` по `event.finished.*` + binding DLQ в DLX по `bet_maker.events.finished`.
  - Каждый сервис владеет своей частью lifecycle.
- **D-04:** Отдельный DLX `bsw.events.dlx` (direct, durable) + DLQ `bet_maker.events.finished.dlq`. Main queue имеет аргументы `x-dead-letter-exchange=bsw.events.dlx` и `x-dead-letter-routing-key=bet_maker.events.finished`. Two-exchange separation of concerns: happy-path и error-path не смешиваются (видно в Management UI как две топологии).
- **D-05:** Routing key константы единым источником на сервис:
  - line-provider: `src/line_provider/messaging/routing.py` (re-export существующего `_TERMINAL_TO_ROUTING` из `interactors/set_event_state.py` в новый модуль).
  - bet-maker: `src/bet_maker/messaging/routing.py`.
  - Обе содержат `EVENT_FINISHED_WIN = "event.finished.win"`, `EVENT_FINISHED_LOSE = "event.finished.lose"`, `EVENT_FINISHED_WILDCARD = "event.finished.*"`. Immutable (`Final[str]`), rename-only.
- **D-06:** bet-maker subscriber bind-ится через wildcard `event.finished.*` — ловит обе терминальные ветки одной queue без per-state binding.

### Manual-ack Ladder & Retry Budget

- **D-07:** `ack_policy=AckPolicy.MANUAL` обязательно на каждом `@router.subscriber(...)` (R1/F1). Никаких default REJECT_ON_ERROR.
- **D-08:** In-handler retry бюджет: `tenacity` 3 attempts с exp backoff `multiplier=0.2, min=0.2, max=2`. Применяется только к `settle_bets_for_event` call (DB-операция), а не вокруг всего handler.
- **D-09:** Классификация исключений (строгая таблица):
  - **POISON → `await msg.reject(requeue=False)` → DLQ:**
    - `pydantic.ValidationError` — payload не соответствует схеме.
    - `faststream.exceptions.DecodeError` — тело не JSON / битая кодировка.
    - Логическая проверка `payload.schema_version != 1` — custom `UnsupportedSchemaVersion`, ловится в этой же ветке.
    - `sqlalchemy.exc.IntegrityError` — DB-constraint violation (schema drift между payload и таблицей).
  - **TRANSIENT → внутри `tenacity` retry:**
    - `sqlalchemy.exc.OperationalError`
    - `sqlalchemy.exc.DBAPIError` с `connection_invalidated=True`
    - `asyncio.TimeoutError`
- **D-10:** Default policy: неизвестный `Exception` вне обоих списков → reject(requeue=False) → DLQ. Исчерпание 3 retry на transient → тоже reject(requeue=False) → DLQ. Core Value alignment: ставка не зависнет, reconciler Phase 6 подхватит закрытие.
- **D-11:** `await msg.ack()` происходит ТОЛЬКО после успешного выхода из `async with uow:` (R2/F4). `nack(requeue=True)` не используется ни в одной ветке — broker-cycling намеренно избегаем (R7).

### Idempotency in settle_bets_for_event

- **D-12:** Базовый механизм идемпотентности — `BetRepository.get_pending_locked(event_id)` с `with_for_update(skip_locked=True)` + `WHERE status='PENDING'` (R3, ROADMAP-locked). Повторный вызов на том же `event_id` возвращает 0 строк и не делает UPDATE.
- **D-13:** Добавить observability колонки в `Bet` (Alembic migration):
  - `settled_at: Mapped[datetime | None]` — nullable, без `server_default`; заполняется PG `func.now()` в UPDATE-стейтменте при settle.
  - `settled_via: Mapped[str | None]` — nullable, значения `'consumer'` или `'reconciler'`. Phase 6 переиспользует тот же interactor.
- **D-14:** `settled_at` источник — PG `func.now()` в UPDATE того же UoW commit. Совпадает с конвенцией Phase 3 (`created_at` / `updated_at` от PG). Reconciler Phase 6 будет писать тем же способом — однородный clock-source.
- **D-15:** НЕ создаём `consumed_events` / `processed_messages` таблицу. Status-filter + idempotent UPDATE — единственная точка истины; reconciler Phase 6 определяет «видели/не видели» через отсутствие PENDING-ставок.
- **D-16:** 0 PENDING-ставок на `event_id` → `structlog.info("settle.noop", event_id=..., reason="no PENDING bets")` + `ack`. Это нормальный идемпотентный исход.
- **D-17:** Сигнатура interactor:

  ```python
  async def settle_bets_for_event(
      uow: AsyncUnitOfWork,
      *,
      event_id: UUID,
      terminal_state: EventTerminalState,
      settled_via: Literal["consumer", "reconciler"],
  ) -> SettleResult: ...
  ```

  `SettleResult` — Pydantic DTO (`event_id`, `terminal_state`, `settled_count`, `settled_bet_ids: list[UUID]`, `settled_via`, `settled_at`). DTO живёт в `bet_maker/schemas/settle.py`.
- **D-18:** Transaction isolation level — `READ COMMITTED` (PG default, наследуется от Phase 3 `async_sessionmaker`). FOR UPDATE SKIP LOCKED + status-filter дают идемпотентность без подъёма isolation.

### Consumer Host & Lifespan

- **D-19:** Один процесс bet-maker: HTTP API + RabbitMQ subscriber в одном `FastAPI` lifespan через `RabbitRouter` + `app.include_router(router)` (auto-lifespan FastStream — `fastapi>=0.112.2`, наш pin `>=0.115` это покрывает). Один docker-сервис bet-maker, один `/health`.
- **D-20:** `/health` проверки:
  - `await router.broker.ping(timeout=1.0)` → bool (RabbitMQ).
  - `len(router.broker.subscribers) > 0` (SC#5 prerequisite).
  - PG ping (Phase 3 D-22 уже на месте).
  - 503 если **любая** из проверок упала.
- **D-21:** Lifespan строгая последовательность (F3):
  ```
  startup:  wait_for_postgres → build httpx singleton → router.broker.connect()
            → declare topology (exchange/queues/bindings) → yield
  shutdown: ...reverse order, nested try/finally guarantees aclose+dispose
  ```
  Никаких `asyncio.gather` параллельных шагов.
- **D-22:** До завершения startup uvicorn не открывает порт; никаких промежуточных `{status: "starting"}` состояний. Docker healthcheck получит connection-refused, что и есть желаемая семантика 503-аналога.

### Publisher (line-provider)

- **D-23:** `RabbitEventBus(EventBus)` в `src/line_provider/facades/event_bus.py` (новый класс рядом с существующим `NoopEventBus`). Инкапсулирует `await router.broker.publish(message, routing_key=...)`. `NoopEventBus` остаётся для unit-тестов (Phase 2 conftest).
- **D-24:** line-provider lifespan: `router.broker.connect()` → declare exchange `bsw.events` → `app.state.event_bus = RabbitEventBus(router.broker)` → yield. R9/R12 уже обеспечен — `interactors/set_event_state.py` мутирует store ДО publish (Phase 2 D-12).

### Consumer (bet-maker)

- **D-25:** Новый модуль `src/bet_maker/entrypoints/messaging.py` с:
  ```python
  router = RabbitRouter(settings.amqp_url)

  @router.subscriber(
      queue=RabbitQueue(
          "bet_maker.events.finished",
          durable=True,
          arguments={
              "x-dead-letter-exchange": "bsw.events.dlx",
              "x-dead-letter-routing-key": "bet_maker.events.finished",
          },
      ),
      exchange=RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True),
      routing_key="event.finished.*",
      ack_policy=AckPolicy.MANUAL,
  )
  async def on_event_finished(payload: EventFinishedMessage, msg: RabbitMessage) -> None: ...
  ```
  Handler делает: `clear_contextvars()` → bind → validate schema_version → tenacity-обёрнутый settle → ack/reject.
- **D-26:** `prefetch_count=10` (F2). Задаётся через `RabbitBroker(amqp_url, ...)` параметром или на subscriber QoS уровне — точный API researcher уточнит, оба варианта приемлемы.
- **D-27:** structlog binding в handler (A7):
  ```python
  clear_contextvars()
  try:
      bind_contextvars(message_id=msg.message_id, correlation_id=..., event_id=payload.event_id)
      ...
  finally:
      clear_contextvars()
  ```

### Schema Duplication Enforcement

- **D-28:** `EventFinishedMessage` дублируется byte-for-byte в `src/bet_maker/schemas/messages.py` (SC#6). Никаких cross-service импортов (Phase 3 D-12 политика).
- **D-29:** CI-тест `tests/contract/test_event_finished_message_schema.py` импортирует обе модели и сравнивает `EventFinishedMessage.model_json_schema()` (Pydantic v2). При расхождении — failing test, видно в PR.

### Testing

- **D-30:** Unit-тесты handler через `TestRabbitBroker(router.broker)` (in-memory). Покрытие веток:
  - happy path → `ack` после UoW commit
  - poison (каждый класс из D-09 POISON) → `reject(requeue=False)`
  - transient → tenacity retry → success после ретрая → `ack`
  - transient → исчерпание retry → `reject(requeue=False)`
  - 0 PENDING → info-log + `ack`
- **D-31:** Один e2e тест против реального RabbitMQ через `testcontainers.rabbitmq.RabbitMqContainer` (F6 SC#7). Сценарий: создать event в line-provider → POST /bet → опубликовать `EventFinishedMessage` через RabbitEventBus → дождаться `GET /bets` со статусом `WON`/`LOST`. Постгрес — также testcontainers (Phase 3 D-22).

### Claude's Discretion

- Точный API `prefetch_count` (broker-level `RabbitBroker(prefetch_count=10)` vs subscriber-level QoS) — researcher уточнит по Context7 FastStream docs (D-26).
- Точный путь `RabbitQueue.arguments` для DLQ-headers vs `dlq` shortcut FastStream — researcher выберет.
- Размещение `messaging/routing.py` (новый под-пакет vs внутри `entrypoints/`) — planner решит исходя из existing pattern.
- Точная форма `tenacity` обёртки на `settle_bets_for_event` (декоратор vs контекст-менеджер) — переиспользуем `make_retry_decorator` factory из Phase 4 D-05, planner адаптирует `_is_retryable` под TRANSIENT-класс из D-09.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — LP-06 (line-provider publishes EventFinishedMessage), BM-09 (durable consumer + manual ack), BM-10 (settle via FOR UPDATE SKIP LOCKED), BM-11 (DLQ for poison), QA-06 (testcontainers e2e + TestRabbitBroker unit tests).
- `.planning/ROADMAP.md` §«Phase 5: RabbitMQ integration» — 7 success criteria + 12 pitfalls (R1/R2/R3/R5/R7/R9/R12/F1–F8/A7).
- `./Тестовое задание Middle Python developer.pdf` — оригинальный ТЗ-документ (memory: feedback_verify_against_tz.md — sync with REQUIREMENTS.md if drift detected).

### Prior phase contexts (locked decisions that constrain Phase 5)
- `.planning/phases/01-skeleton-infrastructure/01-CONTEXT.md` — D-02 shared config package, D-17/D-18 structlog `bind_contextvars`/`clear_contextvars` middleware, D-19 wait_for_postgres with tenacity.
- `.planning/phases/02-line-provider-domain/02-CONTEXT.md` — D-05 UUID event_id, D-12 commit-before-publish ordering в `set_event_state.py`, D-17 frozen Event, EventFinishedMessage schema (`schema_version=1`, `extra="forbid"`).
- `.planning/phases/03-bet-maker-domain-db/03-CONTEXT.md` — D-01 NO coefficient column on Bet, D-09 Bet schema, D-11 EventLookup Protocol, D-12 EventState duplication (no cross-service imports), D-13 app.state DI via `Annotated`+`Depends`, D-18 AsyncUnitOfWork shape, D-22 wait_for_postgres in lifespan.
- `.planning/phases/04-bet-maker-http-integration-with-line-provider/04-CONTEXT.md` — D-05/D-07/D-11 `make_retry_decorator` tenacity factory (переиспользуем), D-19/D-20 lifespan singleton + reverse-order shutdown с nested try/finally.

### Project instructions
- `./CLAUDE.md` §«Recommended Stack» — FastStream 0.6.x, `faststream[rabbit]>=0.6,<0.7`, не объявлять `aio-pika` напрямую.
- `./CLAUDE.md` §«FastStream + FastAPI Integration — Pattern & Caveats» — auto-lifespan для `fastapi>=0.112.2`, `TestRabbitBroker` для unit-тестов.
- `./CLAUDE.md` §«Constraints» — async всюду, RabbitMQ 4.2-management-alpine, Python 3.10.x.

### Existing code (call sites & extension points)
- `src/line_provider/schemas/messages.py` — `EventFinishedMessage` (Phase 2, ready as-is).
- `src/line_provider/facades/event_bus.py` — `EventBus` Protocol + `NoopEventBus`; добавляем `RabbitEventBus` рядом.
- `src/line_provider/interactors/set_event_state.py` — call site `event_bus.publish(...)` уже на месте; точечная замена DI.
- `src/bet_maker/models/bet.py` (Bet ORM) — D-13 добавит две nullable колонки через Alembic migration.
- `src/bet_maker/repositories/bets.py` — добавляем `get_pending_locked(event_id) -> list[Bet]`.
- `src/bet_maker/entrypoints/api/health.py` — расширяем existing handler по D-20.
- `src/bet_maker/entrypoints/lifespan.py` — расширяем по D-21 (PG → httpx → broker.connect → declare → yield).
- `src/bet_maker/facades/deps.py` — добавляем `RabbitBrokerDep`, `EventBusDep`.
- `pyproject.toml` — `faststream[rabbit]>=0.6,<0.7` уже декларирован; `testcontainers>=4.9,<5` уже dev-dep; rabbitmq-extra модуль `testcontainers.rabbitmq` готов к использованию.
- `docker-compose.yml` — RabbitMQ 4.2-management-alpine с healthcheck и `depends_on: service_healthy` уже на месте (Phase 1).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`EventFinishedMessage`** (`src/line_provider/schemas/messages.py`) — фиксированная Pydantic-модель Phase 2; копируется byte-for-byte в bet-maker (D-28).
- **`EventBus` Protocol + `NoopEventBus`** (`src/line_provider/facades/event_bus.py`) — DI-каркас уже встроен в `set_event_state.py` через `app.state.event_bus`. Замена на `RabbitEventBus` — точечная.
- **`AsyncUnitOfWork`** (Phase 3) — `async_sessionmaker.begin()` контекст с auto-commit / auto-rollback. Используется в consumer handler без изменений.
- **`BetRepository`** (Phase 3) — добавим `get_pending_locked(event_id)` методом, тем же стилем, что `add` / `get_by_id`.
- **`make_retry_decorator`** (Phase 4 `bet_maker/facades/line_provider_client.py`) — tenacity factory с `_is_retryable` predicate и `_log_before_sleep` callback. Переиспользуем для in-handler retry в consumer (D-08), адаптируя `_is_retryable` под TRANSIENT-список из D-09.
- **structlog middleware** (Phase 1) — `RequestContextMiddleware` с `bind_contextvars`/`clear_contextvars`. Consumer handler следует тому же паттерну (D-27).

### Established Patterns
- **DI через `Annotated` + `Depends` + `app.state`** (Phase 3 D-13) — `RabbitBrokerDep`, `EventBusDep`, `SettleInteractorDep` будут устроены так же.
- **Lifespan reverse-order shutdown с nested try/finally** (Phase 4 D-20) — добавляем broker layer в ту же конструкцию.
- **Pydantic schemas с `extra="forbid"`** — обязательно для `EventFinishedMessage` (SC#6) и для `SettleResult` DTO.
- **`from_attributes=True`** для ORM ↔ DTO roundtrip — применимо к `SettleResult.from_bet(bet)` если потребуется.
- **`schema_version` поле + validation** (Phase 2) — паттерн расширяем: consumer добавляет `if payload.schema_version != 1: raise UnsupportedSchemaVersion`.

### Integration Points
- **`line_provider/lifespan.py`** — добавить `await router.broker.connect()` и declare exchange `bsw.events`; заменить `NoopEventBus` на `RabbitEventBus(router.broker)` в `app.state.event_bus`.
- **`bet_maker/entrypoints/lifespan.py`** — добавить broker.connect() **после** httpx-singleton + declare main queue + DLX + DLQ + bindings.
- **`bet_maker/entrypoints/messaging.py`** (новый файл) — RabbitRouter + `@router.subscriber` handler.
- **`bet_maker/interactors/settle_bets_for_event.py`** (новый файл) — UoW + repo.get_pending_locked + status flip + settled_at/settled_via UPDATE.
- **`bet_maker/schemas/messages.py`** (новый файл) — byte-for-byte копия `EventFinishedMessage`.
- **`bet_maker/schemas/settle.py`** (новый файл) — `SettleResult` DTO.
- **`bet_maker/repositories/bets.py`** — расширяется методом `get_pending_locked`.
- **`bet_maker/messaging/routing.py`** + **`line_provider/messaging/routing.py`** (новые модули) — routing key константы (D-05).
- **`bet_maker/entrypoints/api/health.py`** — расширение по D-20 (broker.ping + subscribers > 0).
- **`tests/contract/test_event_finished_message_schema.py`** (новый файл) — schema equality test (D-29).
- **`tests/bet_maker/test_messaging.py`** (новый файл) — TestRabbitBroker unit-тесты handler (D-30).
- **`tests/bet_maker/test_e2e_rabbitmq.py`** (новый файл) — testcontainers e2e (D-31).
- **Alembic migration** — добавить `settled_at` и `settled_via` колонки в `bets` (D-13).

</code_context>

<specifics>
## Specific Ideas

- **Routing key constants**: `EVENT_FINISHED_WIN = "event.finished.win"`, `EVENT_FINISHED_LOSE = "event.finished.lose"`, `EVENT_FINISHED_WILDCARD = "event.finished.*"` — типизированы как `Final[str]`.
- **`prefetch_count = 10`** (F2 фиксирован).
- **Tenacity параметры** для in-handler retry: `stop_after_attempt(3) + wait_exponential(multiplier=0.2, min=0.2, max=2)`. `before_sleep` хук переиспользует structlog-логгер по паттерну Phase 4 `_log_before_sleep`.
- **Custom exception** `UnsupportedSchemaVersion(ValueError)` в `bet_maker/schemas/messages.py` или в `bet_maker/entrypoints/messaging.py` — кидается явно после `model_validate`, ловится той же веткой что `ValidationError`.
- **`testcontainers.rabbitmq.RabbitMqContainer`** session-scoped fixture в `tests/conftest.py` (по аналогии с Phase 3 Postgres testcontainer).
- **`durable=True` + classic** для main queue; `durable=True + direct` для DLX; `durable=True` для DLQ — все объекты выживают рестарт брокера.

</specifics>

<deferred>
## Deferred Ideas

- **Reconciliation job** — Phase 6. Phase 5 уже закладывает фундамент: `SettleResult.settled_via: Literal['consumer', 'reconciler']` и идемпотентная сигнатура `settle_bets_for_event(...)`. Reconciler в Phase 6 переиспользует тот же interactor.
- **DLQ replay / inspection endpoints** — отдельная фаза или out of scope; для приёмки Phase 5 хватит RabbitMQ Management UI.
- **Publisher confirms** в line-provider — FastStream defaults сейчас. Если researcher найдёт явное обоснование, может включиться в Phase 5; иначе deferred до production-hardening.
- **Quorum queues / cluster** — single-node demo, deferred до момента, когда понадобится HA.
- **Schema migration v2** (`schema_version=2`) — пока нет триггера; механизм отвержения v!=1 в DLQ уже готов.
- **Outbox-pattern для line-provider** — явно out of scope (PROJECT.md, противоречит in-memory storage).
- **Prometheus / metrics** на `settle_noop_total` / DLQ-counters — `info`-логи + Management UI закрывают приёмку; metrics — future hardening.
- **k8s readiness/liveness split** для /health — docker-compose не требует, deferred.

</deferred>

---

*Phase: 05-rabbitmq-integration*
*Context gathered: 2026-05-18*
