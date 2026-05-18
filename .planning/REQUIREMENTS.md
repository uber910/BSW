# Requirements: BSW Betting System

**Defined:** 2026-05-13
**Core Value:** Ставка никогда не остаётся в статусе PENDING после того, как её событие завершилось.

## v1 Requirements

### Infrastructure (INFR)

- [x] **INFR-01**: Монорепо с src/ layout: `src/line_provider/` и `src/bet_maker/`, общий `pyproject.toml`
- [x] **INFR-02**: uv как менеджер пакетов, `uv.lock` коммитится в репозиторий
- [x] **INFR-03**: Dockerfile для каждого сервиса на базе `python:3.10-slim-bookworm` (без rolling tag)
- [x] **INFR-04**: docker-compose.yml поднимает 4 сервиса: postgres, rabbitmq, line-provider, bet-maker
- [x] **INFR-05**: Healthcheck в docker-compose для postgres (`pg_isready`) и rabbitmq (`rabbitmq-diagnostics ping`); сервисы используют `service_healthy`
- [x] **INFR-06**: Alembic с async-окружением (`alembic init -t async`) для bet-maker — env.py reads DSN from BetMakerSettings (Anti-Pattern 7 mitigated); alembic.ini + async env.py + script.py.mako + versions/ skeleton delivered in plan 01-04. Initial migration creating schema lands in P3.
- [x] **INFR-07**: `.env.example` и pydantic-settings для типизированной конфигурации (DSN, RabbitMQ URL, log level, reconciliation interval) — pydantic-settings BaseAppSettings parent class delivered in plan 01-02; `.env.example` deferred to plan 01-05
- [x] **INFR-08**: structlog с JSON-форматом и `bind_contextvars` для request_id-пропагации

### line-provider (LP)

- [x] **LP-01**: Хранение событий в in-memory структуре, защищённой `asyncio.Lock` от гонок
- [x] **LP-02**: Модель `Event`: event_id (UUID4, client-generated), coefficient (Decimal, ровно 2 знака после запятой, > 0), deadline (UTC-aware datetime), state (NEW / FINISHED_WIN / FINISHED_LOSE). Per D-05 (Phase 2 CONTEXT.md): event_id — UUID4, не str; согласовано через line-provider, AMQP `EventFinishedMessage.event_id` и `bet_maker.bets.event_id`.
- [x] **LP-03**: `PUT /event` — создание нового события или обновление существующего (с валидацией перехода статуса)
- [x] **LP-04**: `GET /event/{event_id}` — получение события по id; 404 если не найдено
- [x] **LP-05**: `GET /events` — список активных событий (`deadline > now`)
- [ ] **LP-06**: При смене статуса с NEW на FINISHED_WIN/FINISHED_LOSE — публикация сообщения `EventFinishedMessage` в RabbitMQ exchange `events` (topic) с routing key `event.finished.{win|lose}`
- [x] **LP-07**: Endpoint `GET /health` с проверкой подключения к RabbitMQ
- [x] **LP-08**: Валидация бизнес-инвариантов: coefficient > 0, deadline в будущем при создании, запрет обратных переходов FINISHED → NEW

### bet-maker (BM)

- [x] **BM-01**: SQLAlchemy 2.0 async модели для ставок (id UUID, event_id UUID, amount Decimal 12.2, status enum (PENDING/WON/LOST), created_at, updated_at). Per D-01 (Phase 3 CONTEXT.md): coefficient НЕ хранится в Bet — это атрибут события, живёт в line-provider; ТЗ стр. 3 `POST /bet` body = `{идентификатор события, сумма ставки}` без coefficient.
- [x] **BM-02**: Unit of Work как async context manager поверх `async_sessionmaker.begin()`, репозитории флашат, UoW коммитит
- [x] **BM-03**: Слоистая архитектура: entrypoints / facades / interactors / selectors / helpers (множественное число; helpers — pure functions)
- [ ] **BM-04**: `GET /events` — проксирует список активных событий из line-provider через httpx с retry (tenacity). Per D-01 (Phase 4 CONTEXT.md): TTL cache не реализуется в P4 — ТЗ кэш не требует, только разрешает отставание в свежести; кэш отложен в README P7 как "next-step extension".
- [x] **BM-05**: `POST /bet` — приём ставки; в теле `{event_id, amount}` (amount > 0, ровно 2 знака после запятой); ответ — 201 с BetRead `{id, event_id, amount, status, created_at}`; status=PENDING при создании. Per D-01 (Phase 3 CONTEXT.md): coefficient snapshot НЕ хранится — coefficient остаётся в line-provider; ТЗ стр. 3 не требует coefficient в Bet payload.
- [x] **BM-06**: Валидация: проверка существования и активности события (deadline > now, state == NEW) перед сохранением ставки
- [x] **BM-07**: `GET /bets` — история всех ставок с полями id, event_id, amount, status (PENDING / WON / LOST), created_at
- [x] **BM-08**: Endpoint `GET /health` с проверкой PostgreSQL (`SELECT 1`) и RabbitMQ
- [ ] **BM-09**: FastStream RabbitRouter consumer на очереди `bet_maker.events.finished` с `AckPolicy.MANUAL`, `prefetch_count=10` (через `Channel(prefetch_count=10)` на `RabbitRouter`), durable=true
- [ ] **BM-10**: Interactor `settle_bets_for_event(event_id, outcome)`: вызывается консьюмером И reconciler'ом; идемпотентный; использует `SELECT FOR UPDATE SKIP LOCKED` чтобы не было гонок
- [ ] **BM-11**: DLX `events.dlx` + DLQ `bet_maker.events.finished.dlq` с bounded retries (max 3) через `x-death` header
- [ ] **BM-12**: Reconciliation job — asyncio background task в lifespan, период через pydantic-settings (default 30s); выбирает PENDING-ставки, тянет статус события из line-provider, доводит до WON/LOST
- [x] **BM-13**: `GET /bet/{bet_id}` — получение ставки по id; 200 + BetRead `{id, event_id, amount, status, created_at}` или 404 `{"detail":"bet {id} not found"}`. Per D-02 (Phase 3 CONTEXT.md): эндпоинт присутствует на диаграмме ТЗ стр. 3 (отсутствует в текстовом описании); реализуется в P3.

### Quality (QA)

- [ ] **QA-01**: Полные type hints во всём коде; `mypy --strict` проходит без ошибок
- [x] **QA-02**: `ruff check` + `ruff format` без замечаний; конфигурация в pyproject.toml
- [x] **QA-03**: pre-commit hooks: ruff, mypy, end-of-file, trailing-whitespace, toml-lint
- [x] **QA-04**: Unit-тесты на каждый слой (interactors/selectors/helpers/repositories) — pytest + pytest-asyncio (line-provider: schemas/state-machine/store/facades/interactors/selectors unit-тесты в плагинах 02-02..02-06; bet-maker — Phase 3 / Phase 5)
- [x] **QA-05**: Integration-тесты на API через httpx AsyncClient (line-provider и bet-maker) (line-provider: 23-тестная HTTP-матрица через httpx.AsyncClient + ASGITransport + LifespanManager landed in plan 02-07; bet-maker — Phase 3)
- [ ] **QA-06**: Consumer тесты через `TestRabbitBroker` (FastStream native)
- [x] **QA-07**: PG-тесты с реальной БД через testcontainers (НЕ SQLite, чтобы ловить `FOR UPDATE` баги)
- [ ] **QA-08**: Один e2e сценарий: создать событие → поставить ставку → завершить событие → проверить, что ставка стала WON/LOST через consumer + ещё одну через reconciler
- [ ] **QA-09**: pytest-cov с минимальным порогом покрытия (≥80%)
- [x] **QA-10**: GitHub Actions CI: lint + typecheck + unit + integration на каждый push/PR

### Documentation (DOC)

- [ ] **DOC-01**: README.md с описанием системы, диаграммой компонентов, инструкцией запуска через `docker compose up`
- [ ] **DOC-02**: Раздел «Architecture» — слои, UoW, RabbitMQ топология, reconciliation, ссылка на ARCHITECTURE.md
- [ ] **DOC-03**: Раздел «Development» — uv install, миграции, запуск тестов, линтеров
- [ ] **DOC-04**: Раздел «Reliability» — описание гарантий доставки и защиты от «зависших» ставок

## v2 Requirements

Не входят в рамки тестового задания, но обсуждались в research.

### Observability

- **OBS-01**: Prometheus метрики (bet counter, queue lag, reconciliation success rate)
- **OBS-02**: OpenTelemetry tracing межсервисных вызовов
- **OBS-03**: Grafana дашборды

### API hardening

- **API-01**: `Idempotency-Key` header на `POST /bet`
- **API-02**: API versioning (`/v1/...`)
- **API-03**: Rate limiting на `POST /bet`
- **API-04**: RFC7807 error format

### Reliability

- **REL-01**: Outbox pattern (требует БД в line-provider, конфликтует с in-memory ТЗ)
- **REL-02**: Quorum queues вместо classic queues
- **REL-03**: Saga pattern для отмены ставок

## Out of Scope

Намеренно исключено из v1 и v2 — стандартные фичи реальной betting-платформы, не подходящие для тестового задания.

| Feature | Reason |
|---------|--------|
| User accounts / authentication | ТЗ не требует, добавит сложности без ценности для оценки |
| User balances | Требует accounts, расширяет scope |
| KYC / age verification | Нерелевантно для тестового задания |
| Multiple bet types (over/under, handicap) | ТЗ явно ограничивает «выигрышем первой команды» |
| Draws (ничьи) | ТЗ явно запрещает |
| Live odds updates / market streaming | Не указано в ТЗ, требует WebSocket-инфраструктуру |
| Payment integration | Out of scope для тестового задания |
| Admin UI / user UI | ТЗ описывает только HTTP API |
| Multi-language / i18n | Тестовое задание для одного reviewer'а |
| Multi-region deployment | docker-compose достаточно |
| Fraud detection | Требует ML-инфраструктуру, out of scope |
| Soft delete / event history | Не указано в ТЗ |
| Webhooks для клиентов | Не указано в ТЗ |
| Push-notifications | Не указано в ТЗ |
| Redis cache событий | line-provider in-memory уже быстрый |
| Kafka вместо RabbitMQ | Overkill для тестового задания |
| Kubernetes deployment | docker-compose достаточно |
| Outbox pattern в line-provider | Требует БД, конфликтует с in-memory ТЗ |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFR-01 | Phase 1 | Complete |
| INFR-02 | Phase 1 | Complete |
| INFR-03 | Phase 1 | Complete |
| INFR-04 | Phase 1 | Complete |
| INFR-05 | Phase 1 | Complete |
| INFR-06 | Phase 1 | Complete (plan 01-04) |
| INFR-07 | Phase 1 | In progress (pydantic-settings parent done plan 01-02; .env.example pending plan 01-05) |
| INFR-08 | Phase 1 | Complete |
| LP-01 | Phase 2 | Complete |
| LP-02 | Phase 2 | Complete |
| LP-03 | Phase 2 | Complete |
| LP-04 | Phase 2 | Complete |
| LP-05 | Phase 2 | Complete |
| LP-06 | Phase 5 | Pending |
| LP-07 | Phase 2 | Complete |
| LP-08 | Phase 2 | Complete |
| BM-01 | Phase 3 | Complete (Plan 03-09) |
| BM-02 | Phase 3 | Complete (Plan 03-09) |
| BM-03 | Phase 3 | Complete (Plan 03-09) |
| BM-04 | Phase 4 | Pending |
| BM-05 | Phase 3 | Complete (Plan 03-09) |
| BM-06 | Phase 3 | Complete (Plan 03-09) |
| BM-07 | Phase 3 | Complete (Plan 03-09) |
| BM-08 | Phase 3 | Complete (Plan 03-09) |
| BM-09 | Phase 5 | Pending |
| BM-10 | Phase 5 | Pending |
| BM-11 | Phase 5 | Pending |
| BM-12 | Phase 6 | Pending |
| BM-13 | Phase 3 | Complete (Plan 03-09) |
| QA-01 | Phase 7 | Pending |
| QA-02 | Phase 1 | Complete |
| QA-03 | Phase 1 | Complete |
| QA-04 | Phase 2 | Complete |
| QA-05 | Phase 2 | Complete |
| QA-06 | Phase 5 | Pending |
| QA-07 | Phase 3 | Complete (Plan 03-09) |
| QA-08 | Phase 6 | Pending |
| QA-09 | Phase 7 | Pending |
| QA-10 | Phase 1 | Complete |
| DOC-01 | Phase 7 | Pending |
| DOC-02 | Phase 7 | Pending |
| DOC-03 | Phase 7 | Pending |
| DOC-04 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 43 total
- Mapped to phases: 43 (100%)
- Unmapped: 0

**Per-phase distribution:**
- Phase 1 (Skeleton + Infrastructure): 12 requirements (INFR-01..08, QA-02, QA-03, QA-10) — note QA-01 enforcement starts here but ownership accepted in Phase 7
- Phase 2 (line-provider domain): 9 requirements (LP-01..05, LP-07, LP-08, QA-04, QA-05)
- Phase 3 (bet-maker DB): 9 requirements (BM-01..03, BM-05..08, BM-13, QA-07)
- Phase 4 (HTTP integration): 1 requirement (BM-04)
- Phase 5 (RabbitMQ integration): 5 requirements (LP-06, BM-09..11, QA-06)
- Phase 6 (Reconciliation): 2 requirements (BM-12, QA-08)
- Phase 7 (Polish + Documentation): 5 requirements (DOC-01..04, QA-01, QA-09)

Note: QA-01 (`mypy --strict`) is **enforced from Phase 1** (CI gate established with QA-10) but **owned** by Phase 7 because final-pass verification of zero strict-mode errors across both packages is the polish-phase deliverable.

---
*Requirements defined: 2026-05-13*
*Last updated: 2026-05-15 after Phase 3 completion (Plan 03-09 — BM-01..03, BM-05..08, BM-13, QA-07 complete)*
