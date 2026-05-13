# Requirements: BSW Betting System

**Defined:** 2026-05-13
**Core Value:** Ставка никогда не остаётся в статусе PENDING после того, как её событие завершилось.

## v1 Requirements

### Infrastructure (INFR)

- [ ] **INFR-01**: Монорепо с src/ layout: `src/line_provider/` и `src/bet_maker/`, общий `pyproject.toml`
- [ ] **INFR-02**: uv как менеджер пакетов, `uv.lock` коммитится в репозиторий
- [ ] **INFR-03**: Dockerfile для каждого сервиса на базе `python:3.10-slim-bookworm` (без rolling tag)
- [ ] **INFR-04**: docker-compose.yml поднимает 4 сервиса: postgres, rabbitmq, line-provider, bet-maker
- [ ] **INFR-05**: Healthcheck в docker-compose для postgres (`pg_isready`) и rabbitmq (`rabbitmq-diagnostics ping`); сервисы используют `service_healthy`
- [ ] **INFR-06**: Alembic с async-окружением (`alembic init -t async`) для bet-maker
- [ ] **INFR-07**: `.env.example` и pydantic-settings для типизированной конфигурации (DSN, RabbitMQ URL, log level, reconciliation interval)
- [ ] **INFR-08**: structlog с JSON-форматом и `bind_contextvars` для request_id-пропагации

### line-provider (LP)

- [ ] **LP-01**: Хранение событий в in-memory структуре, защищённой `asyncio.Lock` от гонок
- [ ] **LP-02**: Модель `Event`: event_id (str), coefficient (Decimal, ровно 2 знака после запятой, > 0), deadline (timestamp), state (NEW / FINISHED_WIN / FINISHED_LOSE)
- [ ] **LP-03**: `PUT /event` — создание нового события или обновление существующего (с валидацией перехода статуса)
- [ ] **LP-04**: `GET /event/{event_id}` — получение события по id; 404 если не найдено
- [ ] **LP-05**: `GET /events` — список активных событий (`deadline > now`)
- [ ] **LP-06**: При смене статуса с NEW на FINISHED_WIN/FINISHED_LOSE — публикация сообщения `EventFinishedMessage` в RabbitMQ exchange `events` (topic) с routing key `event.finished.{win|lose}`
- [ ] **LP-07**: Endpoint `GET /health` с проверкой подключения к RabbitMQ
- [ ] **LP-08**: Валидация бизнес-инвариантов: coefficient > 0, deadline в будущем при создании, запрет обратных переходов FINISHED → NEW

### bet-maker (BM)

- [ ] **BM-01**: SQLAlchemy 2.0 async модели для ставок (id UUID, event_id, amount Decimal 12.2, coefficient Decimal 6.2, status enum, created_at, updated_at)
- [ ] **BM-02**: Unit of Work как async context manager поверх `async_sessionmaker.begin()`, репозитории флашат, UoW коммитит
- [ ] **BM-03**: Слоистая архитектура: entrypoints / facades / interactors / selectors / helpers (множественное число; helpers — pure functions)
- [ ] **BM-04**: `GET /events` — проксирует список активных событий из line-provider через httpx с retry (tenacity)
- [ ] **BM-05**: `POST /bet` — приём ставки; в теле `{event_id, amount}` (amount > 0, 2 знака); ответ — id созданной ставки; снимок coefficient на момент создания
- [ ] **BM-06**: Валидация: проверка существования и активности события (deadline > now, state == NEW) перед сохранением ставки
- [ ] **BM-07**: `GET /bets` — история всех ставок с полями id, event_id, amount, status (PENDING / WON / LOST), created_at
- [ ] **BM-08**: Endpoint `GET /health` с проверкой PostgreSQL (`SELECT 1`) и RabbitMQ
- [ ] **BM-09**: FastStream RabbitRouter consumer на очереди `bet_maker.events.finished` с `AckPolicy.MANUAL`, prefetch=20, durable=true
- [ ] **BM-10**: Interactor `settle_bets_for_event(event_id, outcome)`: вызывается консьюмером И reconciler'ом; идемпотентный; использует `SELECT FOR UPDATE SKIP LOCKED` чтобы не было гонок
- [ ] **BM-11**: DLX `events.dlx` + DLQ `bet_maker.events.finished.dlq` с bounded retries (max 3) через `x-death` header
- [ ] **BM-12**: Reconciliation job — asyncio background task в lifespan, период через pydantic-settings (default 30s); выбирает PENDING-ставки, тянет статус события из line-provider, доводит до WON/LOST

### Quality (QA)

- [ ] **QA-01**: Полные type hints во всём коде; `mypy --strict` проходит без ошибок
- [ ] **QA-02**: `ruff check` + `ruff format` без замечаний; конфигурация в pyproject.toml
- [ ] **QA-03**: pre-commit hooks: ruff, mypy, end-of-file, trailing-whitespace, toml-lint
- [ ] **QA-04**: Unit-тесты на каждый слой (interactors/selectors/helpers/repositories) — pytest + pytest-asyncio
- [ ] **QA-05**: Integration-тесты на API через httpx AsyncClient (line-provider и bet-maker)
- [ ] **QA-06**: Consumer тесты через `TestRabbitBroker` (FastStream native)
- [ ] **QA-07**: PG-тесты с реальной БД через testcontainers (НЕ SQLite, чтобы ловить `FOR UPDATE` баги)
- [ ] **QA-08**: Один e2e сценарий: создать событие → поставить ставку → завершить событие → проверить, что ставка стала WON/LOST через consumer + ещё одну через reconciler
- [ ] **QA-09**: pytest-cov с минимальным порогом покрытия (≥80%)
- [ ] **QA-10**: GitHub Actions CI: lint + typecheck + unit + integration на каждый push/PR

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

Будет заполнено roadmapper'ом после генерации ROADMAP.md.

**Coverage:**
- v1 requirements: 41 total
- Mapped to phases: 0 (TBD by roadmapper)
- Unmapped: 41 ⚠️ (will be 0 after roadmap)

---
*Requirements defined: 2026-05-13*
*Last updated: 2026-05-13 after initial definition*
