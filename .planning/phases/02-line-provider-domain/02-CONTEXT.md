# Phase 2: line-provider domain - Context

**Gathered:** 2026-05-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 наполняет `line-provider` доменной логикой: in-memory event store + полное HTTP CRUD API. Без AMQP — публикация в RabbitMQ откладывается до P5 (но интерфейс event_bus вводится сейчас).

**В скоупе:**
- `InMemoryEventStore` (dict + `asyncio.Lock`) в `infrastructure/store/in_memory.py` (LP-01)
- Pydantic-модель `Event` (event_id UUID4, coefficient Decimal 2dp >0, deadline UTC datetime, state enum NEW/FINISHED_WIN/FINISHED_LOSE) (LP-02)
- `POST /event` — create only, 201 с EventRead, 409 на дубль event_id (LP-03)
- `PUT /event/{event_id}` — update only, 200 с EventRead, 404 если не существует, 422 на reverse state transition (LP-03, LP-08)
- `GET /event/{event_id}` — 200 с EventRead, 404 если нет (LP-04)
- `GET /events` — список активных (`deadline > now AND state == NEW`) (LP-05)
- `GET /health` — `{"status":"ok"}` стаб, deep-pings PG/RMQ откладываются на P5 (LP-07 частично, переносится на P5)
- `helpers/state_machine.py` — `is_transition_allowed(current, new) -> bool` (LP-08)
- `facades/event_bus.py` — `EventBus` protocol + `NoopEventBus` (P5 подменит на RabbitEventBus); interactor `set_event_state` уже вызывает `event_bus.publish(...)` после store-commit
- Unit-тесты на interactors/selectors/helpers/store (QA-04)
- Integration-тесты на 4 HTTP-routes через `httpx.AsyncClient(transport=ASGITransport)` (QA-05)

**Не в скоупе:**
- Реальная публикация в RabbitMQ (P5, LP-06)
- DLX/DLQ-топология (P5)
- Pingи PG/RMQ в `/health` (P5)
- Bet-maker интеграция (`GET /events` proxy в bet-maker — P4)
- Reconciliation (P6)

</domain>

<decisions>
## Implementation Decisions

### HTTP-API контракт
- **D-01:** API из трёх mutating-эндпоинтов + двух read:
  - `POST /event` — create only. Тело: `EventCreate {event_id: UUID4, coefficient: Decimal, deadline: datetime}` (state неявно `NEW` — клиент не присылает). Ответ: 201 + `EventRead`. На дубль event_id → 409.
  - `PUT /event/{event_id}` — update only. Тело: `EventUpdate {coefficient: Decimal, deadline: datetime, state: EventState}` (full replace кроме event_id). Ответ: 200 + `EventRead`. Если события нет → 404. Запрещённый state-переход → 422.
  - `GET /event/{event_id}` — 200 + `EventRead`; 404 если нет.
  - `GET /events` — 200 + `list[EventRead]`; только активные (`deadline > now AND state == NEW`).
  - `GET /health` — 200 `{"status":"ok"}`.
- **D-02:** `PATCH` не используется — все мутации через POST (создание) и PUT (обновление, включая state-change). Уменьшает поверхность API, проще описывать в README и AsyncAPI. State-change в P5 публикует AMQP-сообщение из `interactors/set_event_state.py`, который дёргается в обработчике PUT при обнаружении NEW→FINISHED_*.

### event_id
- **D-03:** `event_id: UUID4`. Клиент генерирует и присылает в POST body. Pydantic-валидация типа (`Annotated[UUID, ...]`); store при `add` выкидывает `EventAlreadyExistsError` → 409. Idempotent: повтор POST с тем же id → 409 (никаких автоматических ретраев, повтор должен быть осознанным).
- **D-04:** `event_id` иммутабелен после создания. В PUT тело не содержит `event_id` (id берётся из URL). Если клиент пришлёт его в теле — Pydantic `extra="forbid"` отрежет 422.
- **D-05:** **Расхождение с REQUIREMENTS LP-02 ("event_id (str)")** — приоритет за CONTEXT.md. Планировщик в первом плане P2 должен синхронизировать REQUIREMENTS.md LP-02 (str → UUID4). Также `EventFinishedMessage.event_id` в P5 и `bets.event_id` в P3 — оба `UUID` (PG-тип `UUID`, SQLAlchemy `Mapped[UUID]`). Архитектурный документ `ARCHITECTURE.md` локально использует `int` в примерах — это устаревший пример, не контракт.

### Семантика обновления (PUT)
- **D-06:** PUT мутирует все поля кроме event_id: `coefficient`, `deadline`, `state`. Полное replace-тело — частичных PATCH-апдейтов нет.
- **D-07:** `deadline > now` валидируется **только на POST** (create). На PUT любой deadline допустим (поддерживает финиш события через несколько секунд после deadline без extra-422). Bet-maker всё равно отрежет `POST /bet` на событие с `deadline <= now` (BM-06).
- **D-08:** State-machine: разрешён только `NEW → FINISHED_WIN`, `NEW → FINISHED_LOSE`, и no-op `state == current_state`. Любые остальные переходы (`FINISHED_* → NEW`, `FINISHED_WIN → FINISHED_LOSE`, etc.) → 422 с `{"detail":"state transition <X>→<Y> not allowed"}`.
- **D-09:** На PUT с no-op state (`state == current_state`) — успех 200, поля coefficient/deadline обновляются. `event_bus.publish` НЕ вызывается (публикуется только реальный переход на терминальное состояние).
- **D-10:** `coefficient` и `deadline` валидируются Pydantic-схемой одинаково в POST и PUT: `coefficient: Annotated[Decimal, condecimal(gt=0, decimal_places=2)]`, `deadline: datetime` (UTC-aware, тз-aware конверсия в `helpers/time.py` или Pydantic-валидатор).

### EventBus facade (P5-ready)
- **D-11:** `src/line_provider/facades/event_bus.py`:
  - `class EventBus(Protocol)`: `async def publish(self, message: EventFinishedMessage, *, routing_key: str) -> None: ...`
  - `class NoopEventBus(EventBus)`: логирует `event_bus.publish.noop` через structlog и возвращает (P2 default).
  - `EventBusDep = Annotated[EventBus, Depends(get_event_bus)]` — provider возвращает `app.state.event_bus`.
- **D-12:** `src/line_provider/interactors/set_event_state.py`:
  - Сначала `await store.update(event_id, ...)` (in-memory commit под `asyncio.Lock`).
  - После успешного commit — `await event_bus.publish(EventFinishedMessage(...), routing_key=f"event.finished.{outcome}")` ТОЛЬКО при переходе NEW→FINISHED_*.
  - Порядок строго: commit → publish (Anti-Pattern 2 из PITFALLS.md).
- **D-13:** В P2 `schemas/messages.py` уже создаётся с финальным `EventFinishedMessage` (Pydantic v2 `model_config = ConfigDict(frozen=True, extra="forbid")`, `schema_version: int = 1`, поля по ARCHITECTURE.md). Это позволяет в P5 не трогать схему, только подменить реализацию EventBus. `event_id` в schema — `UUID`.
- **D-14:** `app.state.event_bus = NoopEventBus()` устанавливается в `entrypoints/lifespan.py` после `configure_structlog`. P5 подменит на `RabbitEventBus(broker=router.broker)` без изменений в interactor.

### In-memory store
- **D-15:** Один `asyncio.Lock` на инстанс `InMemoryEventStore` — гранулярность глобальная. На масштабах P2 (один процесс, одна реплика line-provider, события создаются вручную) per-event lock даст накладные расходы без benefit'а. Anti-Pattern 6 mitigated: все мутации (`add`, `update`, `replace`) под `async with self._lock`. Чистые чтения (`get_by_id`, `list_active`) без лока — возвращают snapshot (см. D-16).
- **D-16:** Store возвращает **snapshots, не ссылки**: `add`/`update`/`get_by_id`/`list_active` возвращают `Event` (frozen Pydantic-модель) или `list[Event]`. Внутри — store держит `dict[UUID, Event]`. Это исключает race-modification клиентом возвращённого объекта.
- **D-17:** `Event` модель в `schemas/events.py` — frozen Pydantic v2 (`ConfigDict(frozen=True)`). Поля: `event_id: UUID`, `coefficient: Decimal`, `deadline: datetime`, `state: EventState`. Конвертация в response: тот же `Event` (есть JSON-serialiser для UUID/Decimal/datetime через Pydantic v2 by default).

### Тесты
- **D-18:** Unit-тесты (без HTTP):
  - `tests/line_provider/test_state_machine.py` — таблица переходов (allowed/forbidden пары).
  - `tests/line_provider/test_in_memory_store.py` — add/update/get/list_active поведение, дубль → exception, concurrent mutations под `asyncio.gather` не теряют данные.
  - `tests/line_provider/test_interactors.py` — `create_event`, `set_event_state` с фейк-EventBus и реальным in-memory store; проверка порядка commit→publish.
  - `tests/line_provider/test_selectors.py` — `list_active_events` фильтрация по `deadline > now` и `state == NEW` с `freeze_time` через `helpers/time.utc_now()`.
- **D-19:** Integration-тесты на API через `client` fixture из `tests/line_provider/conftest.py` (уже есть с P1):
  - `tests/line_provider/test_event_routes.py` — happy path POST→GET→PUT→GET; 409 на дубль; 404 на отсутствующее; 422 на reverse-transition; 422 на coefficient ≤ 0; 422 на deadline в прошлом (только POST).
  - `tests/line_provider/test_event_routes.py` — `list /events` фильтрует завершённые и просроченные.
- **D-20:** Тесты НЕ проверяют реальную публикацию AMQP (это P5). Проверяется только что `NoopEventBus.publish` был вызван с правильным `EventFinishedMessage` через `unittest.mock.AsyncMock` или собственный `FakeEventBus`-список.

### Claude's Discretion
- Точный набор Pydantic-валидаторов (`@field_validator` vs `condecimal` vs `Annotated[..., AfterValidator]`) — выбрать стилистически единый вариант.
- Конкретный тип конструктора `Event` (Pydantic vs `dataclass(frozen=True)`) — на planner. Pydantic предпочтительнее ради `model_validate`/`model_dump_json`, но dataclass проще держать frozen.
- Точная сигнатура `InMemoryEventStore` (методы `replace` vs `update` vs `upsert`) — на planner; главное соблюсти D-15/D-16.
- Структура `helpers/state_machine.py` (set transitions / dict / pattern match) — на planner.
- 200 vs 201 на PUT — оба валидны, выбираю 200 (replace existing, не create).
- `EventState` enum location — `schemas/events.py` или `schemas/messages.py`. Planner выбирает, но **обе схемы должны импортировать один enum** (single source of truth).

### Folded Todos
None — no open todos matched this phase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Проектные документы
- `.planning/PROJECT.md` — Core Value, Constraints, Out of Scope, Key Decisions table.
- `.planning/REQUIREMENTS.md` — для P2 особенно LP-01..05, LP-07, LP-08, QA-04, QA-05. **NB:** LP-02 говорит `event_id (str)` — это устарело, см. D-05; первый task плана должен синхронизировать.
- `.planning/ROADMAP.md` §«Phase 2: line-provider domain» — 6 success criteria, pitfalls preventing.
- `.planning/STATE.md` — текущая позиция, P1 complete, accumulated decisions.
- `CLAUDE.md` §«Technology Stack» и §«Stack Patterns by Variant» — пинованные версии.
- `CLAUDE.md` §«Constraints» — ТЗ-фиксированные ограничения (in-memory line-provider, fully async).

### Research
- `.planning/research/ARCHITECTURE.md` §«src/line_provider/ — paste-ready tree» — итоговая структура каталогов P2.
- `.planning/research/ARCHITECTURE.md` §«Pattern 2: RabbitMQ topology» — EventFinishedMessage schema (P5, но schema-файл создаётся в P2 за D-13). **Поправка:** `event_id` в схеме — UUID, не int (см. D-05).
- `.planning/research/ARCHITECTURE.md` §«Pattern 4: FastAPI + FastStream lifespan composition» — образец `lifespan.py` для P5 интеграции; в P2 lifespan дополняется только `app.state.event_bus = NoopEventBus()`.
- `.planning/research/ARCHITECTURE.md` §«Suggested Build Order — Phase 2» — детальный чек-лист.
- `.planning/research/ARCHITECTURE.md` §«Anti-Pattern 2: Publishing to AMQP from inside a DB transaction» — обоснование D-12 порядка commit→publish.
- `.planning/research/ARCHITECTURE.md` §«Anti-Pattern 6: Reading from the in-memory store via async without a lock» — обоснование D-15/D-16.
- `.planning/research/PITFALLS.md` §«R9 / R12 / Anti-Pattern 2» — публикация после commit, ordering.
- `.planning/research/PITFALLS.md` §«Anti-Pattern 6 (concurrent dict access)» — `asyncio.Lock` на мутациях.
- `.planning/research/PITFALLS.md` §«A7: structlog contextvars cross-task contamination» — `clear_contextvars` шаблон в request middleware (уже в `src/line_provider/entrypoints/middleware.py`, P1).
- `.planning/research/FEATURES.md` §«line-provider API» — детализация эндпоинтов и валидации.

### Прошлые фазы
- `.planning/phases/01-skeleton-infrastructure/01-CONTEXT.md` — D-15 (LineProviderSettings, env_prefix LINE_PROVIDER_), D-19 (/health stub), D-18 (RequestContextMiddleware A7 double-clear).
- `.planning/phases/01-skeleton-infrastructure/01-VERIFICATION.md` — подтверждение P1 success criteria.

### Внешний контекст
- `Тестовое задание Middle Python developer.pdf` (в корне репо) — оригинальное ТЗ; для P2 релевантны разделы про API line-provider и про "ставка не зависает".

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/line_provider/app.py` — `build_app()` factory: добавляем `app.include_router(events.router)` рядом с health.
- `src/line_provider/entrypoints/lifespan.py` — лайфспан: добавляем `app.state.event_bus = NoopEventBus()` после `configure_structlog`. Логи `line_provider.startup` уже сидят.
- `src/line_provider/entrypoints/middleware.py` — `RequestContextMiddleware` с A7 double-clear (request_id propagation). Не трогаем; logs в interactor'ах будут уже под bind'нутым request_id.
- `src/line_provider/entrypoints/api/health.py` — стаб 200, не трогаем (LP-07 deep-ping → P5).
- `src/line_provider/settings/config.py` — `LineProviderSettings` уже с `rabbitmq_url` (для P5); в P2 ничего не меняем.
- `src/config/time.py` — `utc_now()`. Используем для валидации `deadline > now` и для тестов `freeze_time`.
- `src/config/logging.py` — `configure_structlog`. Не трогаем.
- `tests/line_provider/conftest.py` — `client` fixture с ASGITransport. Используем для всех integration-тестов событий.
- `pyproject.toml` — уже подключены fastapi, pydantic, pydantic-settings, structlog, httpx, pytest-asyncio. Новых runtime-зависимостей P2 не вводит. Dev: возможно `freezegun` для time-mocking — но `helpers/time.utc_now()` уже инжектируется, можно обойтись monkeypatch.

### Established Patterns
- Слоистая архитектура (`entrypoints/api → interactors/selectors → infrastructure/store` + `helpers/state_machine` + `facades/event_bus`) — ровно по ARCHITECTURE.md §paste-ready tree.
- `Depends`-injection через `facades/deps.py` — паттерн заложен в ARCHITECTURE.md и должен быть введён в P2 (раньше не было нужды).
- Pydantic v2 модели с `ConfigDict(frozen=True, extra="forbid")` для AMQP и доменных моделей (см. ARCHITECTURE.md Pattern 2).
- `tests/<service>/test_<feature>.py` с per-service `conftest.py` — установлено в P1.
- REQ-ID цитируется в test docstring для grep-traceability (соглашение из P1-07).

### Integration Points
- `entrypoints/api/events.py` (новый) → `facades/deps.get_store`, `facades/deps.get_event_bus` → `interactors/create_event`, `interactors/set_event_state` или `selectors/...`
- `interactors/set_event_state.py` → `infrastructure/store/InMemoryEventStore` → `facades/event_bus.EventBus.publish` (через Depends).
- `lifespan.py` → `app.state.event_bus = NoopEventBus()`, `app.state.event_store = InMemoryEventStore()`. Оба singleton'а живут на app.state, читаются Depends-функциями из `facades/deps.py`.
- `schemas/messages.EventFinishedMessage` — создаётся в P2 (D-13), но реально публикуется в P5. P5 импортирует тот же модуль.

</code_context>

<specifics>
## Specific Ideas

- **PATCH удаляется из API** — выбор пользователя. Все мутации через POST и PUT. State-change тоже через PUT (тело несёт новый state, state-machine валидирует).
- **POST на дубль → 409** — выбор пользователя; идиоматично для create-only семантики.
- **PUT на несуществующее → 404** (а не upsert) — выбор пользователя; чёткое разделение create/update.
- **UUIDv4 client-generated** — выбор пользователя; типобезопасно, idempotency-friendly, единый тип через все три сервиса (line-provider, bet-maker, AMQP). Расхождение с REQUIREMENTS LP-02 (str) — фиксируется как первый task плана.
- **PUT мутирует всё кроме event_id** — выбор пользователя. После финиша coefficient/deadline тоже мутабельны (хотя на практике никто не будет).
- **deadline > now только на POST** — выбор пользователя; PUT принимает любой deadline (real-time финиш через секунду после deadline валиден).
- **EventBus facade с NoopEventBus в P2** — выбор пользователя. Готовим интерфейс сейчас, реализацию подменяем в P5 одной строкой в `lifespan.py`.

</specifics>

<deferred>
## Deferred Ideas

- **Реальная AMQP-публикация в `set_event_state`** — P5 (LP-06). В P2 NoopEventBus + EventFinishedMessage схема готовы; P5 меняет реализацию через app.state.
- **Deep-pings PG/RMQ в `/health`** — P5 (LP-07 полностью). В P2 `/health` остаётся стабом по D-19 из P1.
- **AsyncAPI docs (`/asyncapi`)** — P7 (DOC-04); FastStream активируется в P5.
- **OpenAPI tags/summaries/examples для событий** — P7 (DOC-01..04). В P2 авто-сгенерированный OpenAPI содержит rooms-операции, расширенные метаданные не нужны.
- **Pagination и фильтры на `GET /events`** — не в скоупе тестового задания (не указано в ТЗ, не требуется bet-maker'у). Если когда-нибудь понадобится — отдельная фаза.
- **Idempotency-Key header на `POST /event`** — REL/API-01 deferred per REQUIREMENTS.md (v2). client-generated UUID4 уже даёт достаточную idempotency-гарантию для одной попытки.
- **Per-event асинхронные локи** — оптимизация для масштаба (1000+ rps на один event_id), не нужна в P2. D-15 фиксирует single-lock на масштабе ТЗ.
- **Sequence/auto-increment event_id** — не выбрано (D-03 UUIDv4). Sequence требует БД, что противоречит in-memory ТЗ.

### Reviewed Todos (not folded)
None — no todos reviewed in this phase.

</deferred>

---

*Phase: 2-line-provider-domain*
*Context gathered: 2026-05-14*
