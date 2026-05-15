# Phase 3: bet-maker domain (DB) - Context

**Gathered:** 2026-05-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 наполняет `bet-maker` доменом ставок: PostgreSQL-персистенс через UoW + Repository, HTTP-эндпоинты `POST /bet`, `GET /bets`, `GET /bet/{bet_id}`, `/health` пингует PG. Без AMQP (P5) и без HTTP-клиента к line-provider (P4) — для P4-зависимой валидации события вводится `EventLookup` Protocol со stub-реализацией.

**В скоупе:**
- `models/bet.py` — SQLAlchemy 2.0 typed Bet (id UUID, event_id UUID, amount Numeric(12,2), status PG-ENUM, created_at, updated_at). **Без coefficient** (не требование ТЗ).
- Alembic initial migration `0001_bets_initial.py` — создаёт `bet_status` ENUM type + `bets` table; rerun idempotent.
- `infrastructure/db/engine.py` — `create_async_engine` с `pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800` + `async_sessionmaker(expire_on_commit=False)`.
- `facades/uow.py` — `AsyncUnitOfWork` поверх `async_sessionmaker.begin()`.
- `repositories/bets.py` — `BetRepository(session)` flushes; UoW commits.
- `facades/event_lookup.py` — `EventLookup(Protocol)` + `StubEventLookup` (in-process dict, заполняется в фикстурах). P4 подменит на `HttpEventLookup`.
- `schemas/bets.py` — `BetCreate(event_id, amount)`, `BetRead(id, event_id, amount, status, created_at)`, `BetStatus` enum.
- `helpers/money.py` — `quantize_amount(Decimal) -> Decimal` (round-half-up, 2dp).
- `interactors/place_bet.py` — write use-case: валидация amount, EventLookup проверка, INSERT.
- `selectors/list_bets.py` + `selectors/get_bet.py` — read DTOs (через `model_validate(from_attributes=True)`).
- `entrypoints/api/bets.py` — POST /bet (201), GET /bets (200), GET /bet/{bet_id} (200/404).
- `entrypoints/api/health.py` — расширяет P1 stub до PG-ping с JSON-details.
- `entrypoints/lifespan.py` — bootstrap engine, sessionmaker, `app.state.event_lookup = StubEventLookup()`, tenacity-retry PG ping при startup.
- REQUIREMENTS.md sync task: BM-01 (убрать coefficient), BM-05 (убрать «снимок coefficient»), новый BM-13 (`GET /bet/{bet_id}`); ROADMAP P3 success criteria sync.
- Тесты: `tests/bet_maker/conftest.py` с `testcontainers[postgresql]`, session-scoped PG, `alembic upgrade head` на старте, `TRUNCATE bets RESTART IDENTITY CASCADE` per-test; unit-тесты на repository/UoW/interactor/selectors/helpers; integration-тесты на 3 HTTP routes через `httpx.AsyncClient(transport=ASGITransport)`.

**Не в скоупе:**
- `GET /events` proxy / `httpx`-клиент к line-provider (P4, BM-04)
- Реальная валидация event через HTTP (P4 — `HttpEventLookup` подменит `StubEventLookup`)
- RabbitMQ consumer + `settle_bets_for_event` interactor (P5, BM-09/BM-10/BM-11)
- Reconciliation job (P6, BM-12)
- `(event_id, status)` PG-индекс (P5 — там появится `FOR UPDATE SKIP LOCKED` settle-путь; в P3 не нужен)
- `/health` RabbitMQ ping и subscriber-count check (P5)
- coefficient в Bet модели — нет в ТЗ, не нужен и в payout-логике (P5 берёт coefficient из `EventFinishedMessage` если потребуется)
- `Idempotency-Key` header на POST /bet — упомянуть в README как extension (FEATURES.md D4), не реализовывать

</domain>

<decisions>
## Implementation Decisions

### ТЗ-compliance (отличие от REQUIREMENTS.md)
- **D-01:** **Coefficient в записи Bet — НЕ хранится.** ТЗ (стр. 3) определяет POST /bet body как `{идентификатор события, сумма ставки}`, GET /bets возвращает «идентификаторы и текущие статусы». Coefficient — атрибут события, живёт в line-provider. Первый task P3 синхронизирует REQUIREMENTS.md: BM-01 убирает «coefficient Decimal 6.2», BM-05 убирает «снимок coefficient на момент создания» (по аналогии с P2 D-05 sync LP-02 str→UUID4).
- **D-02:** **GET /bet/{bet_id}** — добавляется в P3 (есть на диаграмме ТЗ, отсутствует в текстовом описании). Возврат: 200 с `BetRead {id, event_id, amount, status, created_at}` или 404. Регистрируется в REQUIREMENTS.md как новый **BM-13** и добавляется в ROADMAP P3 success criteria.
- **D-03:** **event_id остаётся UUID4** (как P2 D-05). ТЗ буквально допускает «строка или число», но мы зафиксировали UUID4 в P2 и в `EventFinishedMessage` (schemas/messages.py) — менять задним числом нельзя. Client-generated UUID4 — более сильный engineering-signal.

### POST /bet API контракт
- **D-04:** Body — `BetCreate {event_id: UUID4, amount: Decimal}`. Pydantic v2: `amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2), AfterValidator(quantize_amount)]` — тот же pattern что P2 Plan 02 для `Coefficient`. `extra="forbid"` отрезает лишние поля.
- **D-05:** Ответ — 201 с `BetRead`. Тело шире минимума ТЗ («как минимум id»), но возвращать только id обедняет UX для curl-демо. Все остальные поля заполнены сервером (status=PENDING, created_at=now, id=сгенерирован).
- **D-06:** Валидация события (BM-06) выполняется через **EventLookup facade** (см. D-11 ниже): если event не найден / `deadline <= now` / `state != NEW` → **422 с `{"detail":"event {id} is not bettable: {reason}"}`**. В P3 StubEventLookup всегда возвращает «valid» по умолчанию (тесты подкручивают через fixtures); в P4 HttpEventLookup делает реальный httpx-вызов в line-provider.

### GET /bets / GET /bet/{bet_id}
- **D-07:** GET /bets — возвращает `list[BetRead]`, **отсортировано по `created_at DESC`** (ROADMAP P3 success criterion #3). Без пагинации (test-task scale). Селектор — `selectors/list_bets.list_bets(session)` без UoW, чистый read.
- **D-08:** GET /bet/{bet_id} — 200 с `BetRead` или **404** `{"detail":"bet {id} not found"}`. Селектор — `selectors/get_bet.get_bet_by_id(session, bet_id)` возвращает `BetRead | None`; роутер мапит None → HTTPException(404).

### Bet модель / DB-схема
- **D-09:** **Финальная схема `bets`:**
  - `id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)` — Python-генерация (как event_id в P2), DB-тип `UUID`.
  - `event_id: Mapped[UUID] = mapped_column(nullable=False)` — UUID, **без FK** (events живут в другом сервисе/процессе).
  - `amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)` — PITFALLS A5.
  - `status: Mapped[BetStatus] = mapped_column(SqlEnum(BetStatus, name="bet_status", create_type=True), nullable=False, default=BetStatus.PENDING)` — **PG native ENUM type** `bet_status` ('PENDING','WON','LOST'); Alembic создаёт type первым шагом миграции.
  - `created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)` — DDL-уровень default (DB-portable).
  - `updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)` — SQLAlchemy 2.0 best-practice: `server_default` для DDL + `onupdate` через ORM (срабатывает на UPDATE через UoW; прямые SQL мимо ORM не updated_at — но в нашей архитектуре всё идёт через UoW).
- **D-10:** **Индексы — только PK в P3.** `(event_id, status)` композит для `FOR UPDATE SKIP LOCKED` settle-пути добавится в P5 отдельной Alembic-миграцией (P5 уже знает SQL ровно того, что нужно). `(created_at DESC)` для GET /bets — не нужен на test-task volume (один dev-instance). Идемпотентность settle-пути в P5 — через status state-machine (`WHERE status='PENDING'` фильтр + `FOR UPDATE SKIP LOCKED`), **без отдельной idempotency_key колонки**.

### EventLookup facade (P4-ready)
- **D-11:** `src/bet_maker/facades/event_lookup.py`:
  - `class EventSnapshot(BaseModel, frozen=True)`: `event_id: UUID, deadline: datetime, state: EventState` (импорт `EventState` — см. D-12).
  - `class EventLookup(Protocol)`: `async def get_event(self, event_id: UUID) -> EventSnapshot | None: ...`
  - `class StubEventLookup(EventLookup)`: держит `dict[UUID, EventSnapshot]`, методы `seed(snapshot)` / `seed_active(event_id, deadline=now+1h)` для удобства тестов. `get_event` возвращает `None` если id не засеяна — interactor мапит в 422.
  - `EventLookupDep = Annotated[EventLookup, Depends(get_event_lookup)]` — provider читает `app.state.event_lookup`.
- **D-12:** **`EventState` enum** — нужен на стороне bet-maker для проверки `state == NEW` в interactor. Опции:
  - (a) Импортировать из `line_provider.schemas.events` — нарушает service-boundary, бритвенно;
  - (b) Дублировать `class EventState(str, Enum)` в `bet_maker/schemas/events.py` (3 значения) — корректно, симметрично с дублированием `EventFinishedMessage` в P2 D-13 (intentional duplication).
  - **Выбор (b).** EventState на стороне bet-maker — в `bet_maker/schemas/events.py`; значения параритетны с `line_provider/schemas/events.EventState` (тест на parity добавится в P5 при e2e).
- **D-13:** В lifespan: `app.state.event_lookup = StubEventLookup()` устанавливается после `configure_structlog` и до запуска uvicorn. P4 подменит в lifespan на `HttpEventLookup(client=line_provider_client)`; `interactors/place_bet.py` не меняется между P3 и P4 (повторяет pattern P2 EventBus / NoopEventBus → RabbitEventBus).
- **D-14:** Interactor `place_bet`:
  ```
  async def place_bet(uow, *, event_id, amount, event_lookup) -> Bet:
      snapshot = await event_lookup.get_event(event_id)
      if snapshot is None:
          raise EventNotBettable("event not found")
      if snapshot.deadline <= utc_now():
          raise EventNotBettable("deadline passed")
      if snapshot.state != EventState.NEW:
          raise EventNotBettable("event not active")
      async with uow:
          bet = Bet(event_id=event_id, amount=quantize_amount(amount))
          uow.bets.add(bet)
          await uow.session.flush()
          return Bet.model_validate(bet, from_attributes=True)  # внутри session, A1 mitigated
  ```
  Route переводит `EventNotBettable → HTTPException(422)`.

### UoW + Repository + engine (зафиксировано из PITFALLS/ARCHITECTURE)
- **D-15:** `async_sessionmaker(engine, expire_on_commit=False)` — обязательное для async (PITFALLS A1). Sessionmaker — module-level singleton; sessions — per-request (PITFALLS A2).
- **D-16:** `create_async_engine` params: `pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800` (PITFALLS A3, не отступаем).
- **D-17:** `AsyncUnitOfWork` shape — точно как ARCHITECTURE Pattern 1: `__aenter__` делает `await self._sessionmaker.begin().__aenter__()`, экспонирует `self.session` и `self.bets`. `__aexit__` делегирует commit/rollback SQLAlchemy. Никакого ручного `await session.commit()` в репозиториях (Anti-Pattern 1).
- **D-18:** `BetRepository.add(bet)` — `self._session.add(bet); await self._session.flush()` (flush, не commit). `get_pending_locked(event_id)` НЕ нужен в P3 — это P5; здесь добавляем только `add` + `get_by_id`.

### Pydantic / Decimal serialization
- **D-19:** `BetRead.amount` — Pydantic v2 сериализует Decimal как **string** ("10.00") по умолчанию (PITFALLS A4). Принимаем это поведение; в README P7 явно документировать `amount: string, pattern: ^[0-9]+\.[0-9]{2}$`. **Тесты сравнивают строкой**, не float (`assert body["amount"] == "10.00"`, не `== 10.0`). ROADMAP P3 success criterion #6 явно требует round-trip `"10.00"` → `"10.00"`.
- **D-20:** `BetStatus` — Python `(str, Enum)` (как `EventState` в P2 D-13, см. STATE.md Plan 02-02 — `StrEnum` заменён на `(str, Enum)` из-за Python 3.10). Pydantic сериализует как `"PENDING"`/`"WON"`/`"LOST"`.

### Тесты (QA-07 + ROADMAP success criteria)
- **D-21:** **testcontainers session-scope PG**. `tests/conftest.py` root-level: `@pytest.fixture(scope="session")` поднимает `PostgresContainer("postgres:16-alpine")`, выдаёт DSN. Используется и в local pytest, и в CI (GitHub Actions runner имеет docker — никаких GHA `services:` блоков не добавляется в `.github/workflows/ci.yml`).
- **D-22:** **Bootstrap схемы — `alembic upgrade head`.** Session-fixture после старта контейнера запускает `alembic upgrade head` через subprocess (или programmatic API `alembic.command.upgrade`) с `BetMakerSettings.postgres_dsn` указывающим на тестовый контейнер. Это обеспечивает success criterion #5 («alembic upgrade head applies migration; rerun is idempotent») и ловит миграционные баги (forgotten ENUM CREATE TYPE, etc.) — стоимость +1s на старт session.
- **D-23:** **Per-test изоляция — TRUNCATE.** `@pytest.fixture(autouse=True)` для `tests/bet_maker/` функционального scope, в teardown выполняет `TRUNCATE bets RESTART IDENTITY CASCADE` через engine.connect(). Каждый тест работает в реальных COMMIT-транзакциях — критично для тестирования FOR UPDATE SKIP LOCKED в P5 (savepoint-based isolation сломает этот flow). Цена +50-100мс/тест приемлема для test-task scale.
- **D-24:** **Структура тестов:**
  - `tests/bet_maker/test_models.py` — unit: Bet creation, default status=PENDING, created_at, updated_at autopopulated.
  - `tests/bet_maker/test_repositories.py` — repository.add + session.flush, get_by_id.
  - `tests/bet_maker/test_uow.py` — UoW commit on clean exit, rollback on exception.
  - `tests/bet_maker/test_event_lookup.py` — StubEventLookup seed + retrieve + None-on-miss.
  - `tests/bet_maker/test_place_bet.py` — interactor: happy path, EventNotBettable cases (not found / past deadline / state != NEW), amount quantization roundtrip.
  - `tests/bet_maker/test_selectors.py` — list_bets ordering, get_bet_by_id, model_validate from_attributes.
  - `tests/bet_maker/test_bet_routes.py` — integration HTTP: POST happy 201 + 422 (event not bettable / amount <=0 / amount >2dp / amount missing / extra field), GET /bets ordering, GET /bet/{id} happy + 404, Decimal exact roundtrip ("10.00"→"10.00").
  - `tests/bet_maker/test_health.py` — расширение P1 smoke: 200 + `{"status":"ok","checks":{"postgres":"ok"}}`, при стопе PG (отдельный fixture с force-close engine pool) → 503 + `"status":"degraded"`.
  - `tests/bet_maker/test_lifespan.py` — startup retry: контейнер недоступен → tenacity retries → eventual RuntimeError если все retries исчерпаны (можно поставить `attempts=2` через override settings для скорости).
  - `tests/bet_maker/test_alembic.py` — `alembic upgrade head` + второй прогон идемпотентен (success criterion #5).
- **D-25:** `tests/bet_maker/conftest.py` — `client` fixture обновляется: вместо in-memory build_app использует `build_app()` с overridden settings указывающими на тестовый PG DSN. `app.dependency_overrides` для StubEventLookup при необходимости подкручивать seed.

### /health (BM-08 + D2 mitigation)
- **D-26:** **GET /health** — каждый запрос делает SELECT 1 через `engine.connect()` (или через session — но без UoW). Без кэша: ~5мс overhead для test-task scale несущественны, живые 503 critical для docker-compose healthcheck.
- **D-27:** **Lifespan startup retry** — `infrastructure/db/pings.py::wait_for_postgres()` декорирован `@retry(stop=stop_after_attempt(10), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)`, пингует SELECT 1. Lifespan вызывает в `try/except` — если не подключилось за 10 попыток (~суммарно ~50s), `RuntimeError("postgres unreachable")` и сервис падает с понятным structlog-логом. Закрывает D2 mitigation из ROADMAP.
- **D-28:** **Response format** — расширяемый JSON:
  - 200: `{"status":"ok","checks":{"postgres":"ok"}}`
  - 503: `{"status":"degraded","checks":{"postgres":"down"}}`
  P5 добавит ключи `checks.rabbitmq`, `checks.subscriber_count`. **P1 контракт `{"status":"ok"}` остаётся backwards-compatible** — поле `status` сохраняется; новое поле `checks` — дополнение. P1 smoke-тест `test_health_returns_status_ok` (assertion `body == {"status": "ok"}`) **сломается** — первый task в Wave HTTP-routes должен обновить ассерт до `body["status"] == "ok"` (subset-check) или подставить полный новый объект.
- **D-29:** Реализация: `entrypoints/api/health.py` использует `Depends(get_engine)` и пытается `await conn.scalar(text("SELECT 1"))` в `try/except SQLAlchemyError → return JSONResponse(status_code=503, content={"status":"degraded",...})`. structlog.bind health.check.failed на отказе.

### Logging / структура каталогов / связи с P1/P2
- **D-30:** Каталог `src/bet_maker/` достраивается по paste-ready дереву из ARCHITECTURE.md §`src/bet_maker/ — paste-ready tree` строки 176–246. В P3 заполняются: `models/`, `schemas/`, `repositories/`, `facades/uow.py`, `facades/event_lookup.py`, `facades/deps.py`, `interactors/place_bet.py`, `selectors/list_bets.py`, `selectors/get_bet.py`, `helpers/money.py`, `helpers/status.py` (заглушка `event_state_to_bet_status` для P5), `infrastructure/db/engine.py`, `infrastructure/db/pings.py`, `entrypoints/api/bets.py`, `entrypoints/api/health.py` (replace), `entrypoints/lifespan.py` (extend). НЕ заполняются: `entrypoints/consumers/`, `entrypoints/workers/`, `infrastructure/broker/`, `facades/line_provider_client.py`, `facades/cache.py`, `selectors/list_active_events.py`, `selectors/list_pending_event_ids.py`, `interactors/settle_bets_for_event.py`, `interactors/reconcile_pending_bets.py`, `models/` для других сущностей — это P4/P5/P6.
- **D-31:** **A7 contextvars middleware** — уже есть в `bet_maker/entrypoints/middleware.py` из P1 (Plan 01-04). Не трогать в P3.
- **D-32:** `BetMakerSettings` — уже определён в P1 (Plan 01-04) с `postgres_dsn: PostgresDsn`, `rabbitmq_url: AmqpDsn`, etc. В P3 не меняется. Lifespan читает `settings.postgres_dsn` через `Depends(get_settings)`.

### Claude's Discretion
- Точная сигнатура fixtures (которые pytest-asyncio + testcontainers + Alembic) — на planner; главное соблюсти D-21/D-22/D-23.
- Способ запуска Alembic из тестов: subprocess (`uv run alembic upgrade head`) vs programmatic (`alembic.command.upgrade`). Programmatic быстрее и чище для async runtime — предпочтительно, но planner решает по эргономике.
- Стиль определения BetStatus enum (`(str, Enum)` vs `StrEnum`) — фиксируется решением P2 D-13 STATE.md `(str, Enum)` из-за Python 3.10. Planner следует.
- `Mapped[uuid.UUID]` vs `Mapped[UUID]` импорт — стилистическое.
- Точная форма `EventNotBettable` exception (одно сообщение vs три класса) — на planner.
- Где живёт `BetStatus` — `src/bet_maker/schemas/bets.py` (consistent с BetCreate/BetRead) или отдельный `models/enums.py`. Planner выбирает; главное — **один импорт** из всего кода (single source of truth).

### Folded Todos
None — no open todos in this project.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth — ТЗ
- `./Тестовое задание Middle Python developer.pdf` (страницы 1–4) — **первоисточник всех требований**. BM-* в `REQUIREMENTS.md` — это наша трактовка; при конфликте побеждает ТЗ. Ключевые цитаты:
  - стр. 1: «коэффициент ставки на выигрыш — строго положительное число с двумя знаками после запятой» — атрибут события в line-provider, **не Bet**.
  - стр. 3 `POST /bet`: тело = `{идентификатор события, сумма ставки}` — **никакого coefficient**.
  - стр. 3 `GET /bets`: «массив JSON-объектов, содержащих информацию о ставках: их идентификаторы и текущие статусы» — наш `BetRead {id, event_id, amount, status, created_at}` шире (maturity-расширение).
  - стр. 3 (диаграмма): `GET /bet/{bet_id}` — есть на диаграмме, отсутствует в текстовом описании → реализуем (D-02).
  - стр. 4 «надёжность интеграции… невозможности зависания ставки в состоянии ещё не сыграла» — Core Value; в P3 закладывается defense-in-depth через `EventLookup` (даже если P4/P5 ещё не готовы, в P3 валидация event_id экранирует ставки на несуществующие события от попадания в PENDING-навсегда).

### Проектные документы
- `./CLAUDE.md` §«Technology Stack» + §«Stack Patterns by Variant» — пинованные версии (SQLAlchemy 2.0.49, asyncpg 0.31.0, Alembic 1.18.4, tenacity 9.1.4, pytest 9.0.3, pytest-asyncio 1.1.0, pytest-cov 7.1.0, httpx 0.28.1).
- `./CLAUDE.md` §«Custom rules» — `SingleStore queries: always use context7` (не применимо, мы на PG); `DB: run only readonly commands` (для discussion / verification); «No emojis in docs and code».
- `.planning/PROJECT.md` — Core Value, Constraints (in-memory line-provider — критично для понимания почему bet-maker не имеет общей БД), Out of Scope (нет user balance, нет idempotency-key в обязательной части).
- `.planning/REQUIREMENTS.md` — BM-01..BM-08 (P3) + BM-13 (новый, добавится в первом sync-task). **NB:** BM-01/BM-05 содержат «coefficient» — устаревшая трактовка ТЗ, первый task P3 синхронизирует (см. D-01).
- `.planning/ROADMAP.md` §«Phase 3: bet-maker domain (DB)» — 6 success criteria, pitfalls preventing. **NB:** success criterion #6 («Decimal round-trip exact `"10.00"`») фиксирует D-19 contract.
- `.planning/STATE.md` — accumulated decisions из P1/P2; Plan 01-04 уже создал alembic skeleton + BetMakerSettings; не повторять.
- `.planning/phases/01-skeleton-infrastructure/01-CONTEXT.md` — D-04 (Dockerfile параметризован `ARG SERVICE`), D-05 (compose сервис `postgres:16-alpine`), D-15 (BetMakerSettings env_prefix=BET_MAKER_), D-18 (A7 middleware reused). НЕ менять эти решения.
- `.planning/phases/02-line-provider-domain/02-CONTEXT.md` — D-05 (event_id=UUID4 везде), D-13 (`EventFinishedMessage` в `schemas/messages.py` готов к P5), `EventState` enum locations + parity rule. **EventState на стороне bet-maker дублируется** — D-12 этого файла.

### Architecture / Research
- `.planning/research/ARCHITECTURE.md` §«src/bet_maker/ — paste-ready tree» (строки 176–246) — итоговая структура каталогов; В P3 заполняется частично, см. D-30.
- `.planning/research/ARCHITECTURE.md` §«Pattern 1: Async Unit of Work + Repository (concrete shape)» (строки 257–405) — точный shape UoW, BetRepository, get_pending_locked (P5), interactor settle_bets_for_event (P5), selector list_bets. Pattern 1 — основа P3.
- `.planning/research/ARCHITECTURE.md» §«Pattern 4: FastAPI + FastStream lifespan composition» (строки 571–668) — образец lifespan; в P3 используется только PG-часть (DB-pool, async_sessionmaker startup/shutdown). FastStream broker — P5.
- `.planning/research/ARCHITECTURE.md» §«Phase 3: bet-maker domain (DB-only, no AMQP)» (строки 795–814) — buildlist того же phase.
- `.planning/research/ARCHITECTURE.md» §«Anti-Pattern 1: Committing in a repository» — D-18 обоснование.
- `.planning/research/ARCHITECTURE.md» §«Anti-Pattern 3: Sharing one AsyncSession across requests» — D-15 обоснование.
- `.planning/research/ARCHITECTURE.md» §«Anti-Pattern 7: Mixing alembic configuration with app settings» — закрыто в P1 Plan 01-04, не нарушать.

### Pitfalls (mitigations locked here)
- `.planning/research/PITFALLS.md` §«Pitfall A1: `MissingGreenlet` / `greenlet_spawn` on lazy-load after commit» — D-15 (`expire_on_commit=False`) + D-14 (`model_validate` внутри session).
- `.planning/research/PITFALLS.md» §«Pitfall A2: Sharing one `AsyncSession` across concurrent tasks» — D-15 (per-request UoW).
- `.planning/research/PITFALLS.md» §«Pitfall A3: asyncpg connection pool too small» — D-16 (pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800).
- `.planning/research/PITFALLS.md» §«Pitfall A4: Decimal coercion drift — Pydantic v2 string serialization» — D-19 (accept string, document, test with string compare).
- `.planning/research/PITFALLS.md» §«Pitfall A5: NUMERIC ↔ Decimal precision loss via asyncpg's float fallback» — D-09 (`Mapped[Decimal] = mapped_column(Numeric(12, 2))`).
- `.planning/research/PITFALLS.md» §«Pitfall A6: Awaiting `AsyncSession` from a sync context (Alembic env.py)» — уже закрыто в P1 Plan 01-04 (alembic async template + env.py читает BetMakerSettings).
- `.planning/research/PITFALLS.md» §«Pitfall A7: structlog contextvars cross-task contamination» — middleware уже в P1; не трогать.
- `.planning/research/PITFALLS.md» §«Pitfall D2: Healthcheck false positives (`pg_isready` before initdb)» — D-27 (tenacity retry в lifespan) + D-26 (live SELECT 1 в /health).
- `.planning/research/PITFALLS.md» §«Pitfall R3: Status update races between consumer and reconciler» — обоснование D-10 «индекс (event_id, status) + FOR UPDATE SKIP LOCKED в P5, не в P3».

### FEATURES (что НЕ делаем в P3)
- `.planning/research/FEATURES.md» §«Differentiators / D4 Idempotency on POST /bet» — упомянуть в README extension section в P7, не реализовывать в P3.
- `.planning/research/FEATURES.md» §«Not Doing» строки 174–175 (rate limiting, Outbox) — confirmed out of scope.

### External docs (когда понадобится planner / researcher)
- SQLAlchemy 2.0 async docs (engine/sessionmaker/typed Mapped) — через Context7 `/websites/sqlalchemy_en_20` (HIGH confidence, использовался в архитектурном research).
- Alembic async template — `alembic init -t async`; уже выполнено в P1, изменений в env.py в P3 НЕТ.
- testcontainers-python (postgres support) — стандартный API `PostgresContainer("postgres:16-alpine").start()`; researcher может уточнить детали через Context7 если нужны нюансы wait-strategy.
- tenacity 9.x — `@retry(stop=stop_after_attempt(N), wait=wait_exponential(...))`, `reraise=True`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from P1)
- `src/bet_maker/entrypoints/middleware.py` — `RequestContextMiddleware` с A7 double-clear (P1 D-18). НЕ менять, переиспользуется.
- `src/bet_maker/settings/config.py` (или `bet_maker/__init__.py` — уточнить в planner) — `BetMakerSettings(BaseAppSettings)` с `postgres_dsn: PostgresDsn`, `rabbitmq_url: AmqpDsn`, `line_provider_base_url: HttpUrl`, `reconciliation_interval_s: int = 30`, `host: str = "0.0.0.0"`, `port: int = 8001`. В P3 не дополняется (всё уже есть). Provider `get_settings` уже зарегистрирован.
- `src/config/time.py::utc_now` — единственный источник «текущего времени» для freeze-time в тестах. Использовать в D-14 для `snapshot.deadline <= utc_now()`.
- `src/config/logging.py::configure_structlog` — уже вызывается в lifespan (P1 D-17). НЕ дублировать.
- `alembic/env.py` — уже умеет читать `BetMakerSettings.postgres_dsn` (P1 Plan 01-04). НЕ редактировать — только добавить новые миграции в `alembic/versions/`.
- `alembic.ini` — без `sqlalchemy.url` (Anti-Pattern 7 mitigated). НЕ редактировать.
- `tests/bet_maker/conftest.py` — `client` fixture с `ASGITransport(app=build_app())` уже есть (P1 D-11/D-12). **БУДЕТ ИЗМЕНЁН** в P3: добавится PG-зависимая фабрика settings, autouse TRUNCATE fixture, StubEventLookup seed-fixture.

### Established Patterns (зеркало P2)
- **Facade Protocol + Stub реализация → реальная реализация в следующей фазе.** P2 D-11: `EventBus(Protocol)` + `NoopEventBus` → P5 `RabbitEventBus`. P3 повторяет: `EventLookup(Protocol)` + `StubEventLookup` → P4 `HttpEventLookup`.
- **Intentional schema duplication между сервисами** (P2 D-13 для `EventFinishedMessage`). P3 повторяет для `EventState` enum (D-12).
- **Sync-task в первом плане фазы** для синхронизации REQUIREMENTS.md (P2 Plan 02-01 sync'ил LP-02 str→UUID4). P3 Plan 03-01 sync'ит BM-01/BM-05/BM-13 + ROADMAP P3 success criteria.
- **REQ-ID в docstrings тестов** (P2 Plan 02-02 ввёл convention) — каждый тест ссылается на BM-XX / QA-07 / D-XX для grep-traceability.
- **`extra="forbid"` на всех Pydantic schemas** — P2 ввёл в EventCreate/EventUpdate/Event; P3 применяет к BetCreate/BetRead.

### Integration Points
- `src/bet_maker/__main__.py::main()` — уже вызывает `uvicorn.run("bet_maker.app:build_app", factory=True, host="0.0.0.0", port=8001, log_config=None)` (P1 D-03). В P3 не меняется.
- `entrypoints/lifespan.py` — точка сборки. P1 версия делает только `configure_structlog`. P3 расширяет: создаёт engine + sessionmaker, ждёт PG (D-27), регистрирует `app.state.engine`, `app.state.sessionmaker`, `app.state.event_lookup`. P5 добавит broker; P6 добавит worker. **Все добавления — `app.state.*`, никаких module-level singletons** (PITFALLS A2).
- `entrypoints/api/health.py` — заменяется (P1 был stub). P5 расширит. **P1 smoke-тест `test_health_returns_status_ok` сломается** — обновить в первом implementing-task P3 (см. D-28).
- `docker-compose.yml` — `bet-maker` сервис уже зависит от `postgres: { condition: service_healthy }` (P1 D-05). В P3 правок compose НЕ требуется.
- `pyproject.toml` — добавить prod-deps `sqlalchemy[asyncio]==2.0.49`, `asyncpg==0.31.0`, `alembic==1.18.4`, `tenacity==9.1.4`; добавить dev-deps `testcontainers[postgresql]` (новая зависимость), `pytest-cov` (уже добавлен в P2 Plan 02-01 dev-deps — verify).

</code_context>

<specifics>
## Specific Ideas

- **«это один и тот же сервис же»** — реплика пользователя на старте обсуждения, скорректирована со ссылкой на ТЗ + CLAUDE.md Constraints. Важно: в P5 reconciliation job + RabbitMQ consumer закрывают Core Value не через общую БД, а через durable queue + HTTP poll. Это краеугольный камень архитектуры; planner должен подсветить разделение в первом sync-task.
- **«посмотри ссылку на тз и проверь»** — пользователь явно требует verification против первоисточника перед фиксированием решений. Это поведенческое правило для всех будущих фаз: при конфликте `REQUIREMENTS.md` ↔ ТЗ.pdf побеждает ТЗ; REQUIREMENTS.md синхронизируется первым task'ом фазы.
- **«по бест практикам SQLAlchemy»** — для `updated_at`. Реализация D-09: `server_default=func.now()` для DDL-уровневого default + `onupdate=func.now()` для ORM-инициированных UPDATE. Эта пара — каноничный SA-2.0 pattern.

</specifics>

<deferred>
## Deferred Ideas

- **Idempotency-Key header на POST /bet** — FEATURES.md D4. ТЗ не требует. Реализовать как «extension» в README P7 ровно одним абзацем + не строить.
- **Rate limiting на POST /bet** — out of scope (FEATURES.md, REQUIREMENTS.md API-03).
- **GET /bets pagination + filtering** — out of scope для P3 (ТЗ не требует, test-task volume).
- **`(event_id, status)` композитный индекс** — добавить в P5 отдельной Alembic-миграцией `0002_idx_bets_event_id_status.py`. Это часть P5 «settle path» работы.
- **`(created_at DESC)` индекс для GET /bets** — добавить только если в P7 perf-тест покажет необходимость. Сейчас seq scan на ~десятках строк — норма.
- **PG `events`-FK на `bets.event_id`** — невозможен по дизайну (events в другом сервисе, in-memory). Отмечено как architectural decision.
- **EventState parity tests между line-provider и bet-maker schemas** — добавить в P5 e2e (когда оба сервиса в одном тесте).
- **OpenAPI tags/summaries/examples для bet-maker** — заполняются в P7 (DOC-02).

### Reviewed Todos (not folded)
None.

</deferred>

---

*Phase: 03-bet-maker-domain-db*
*Context gathered: 2026-05-15*
