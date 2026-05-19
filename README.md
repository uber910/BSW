# BSW Betting System

[![ci](https://github.com/uber910/BSW/actions/workflows/ci.yml/badge.svg)](https://github.com/uber910/BSW/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-94%25-brightgreen.svg)]()

Микросервисная система приёма ставок на спортивные события. Два полностью асинхронных сервиса (`line-provider`, `bet-maker`), интеграция через RabbitMQ, история ставок в PostgreSQL, reconciliation как защита от потерянных сообщений.

**Core Value:** ставка никогда не остаётся в статусе PENDING после того, как событие завершилось. Вся архитектура интеграции (durable queue + manual ack + reconciliation job) подчинена этому инварианту.

## Quick start

Запуск всего стека из корня репозитория:

```bash
cp .env.example .env
docker compose up -d
```

Дождаться `(healthy)` на всех сервисах (около 30 секунд):

```bash
docker compose ps
```

Проверить health-эндпоинты обоих сервисов:

```bash
curl -s http://localhost:8000/health   # line-provider
curl -s http://localhost:8001/health   # bet-maker
```

Оба должны вернуть `{"status":"ok"}` (для bet-maker — `{"status":"ok", "checks": {...}}`).

RabbitMQ Management UI: http://127.0.0.1:15672 (логин/пароль: `guest` / `guest`).

> **Note:** `guest:guest` — это дефолтные test-credentials RabbitMQ, использующиеся только в локальной разработке. Management UI забинден на `127.0.0.1` (loopback) и недоступен извне хоста; AMQP-порт 5672 не публикуется наружу. Эти credentials НЕ предназначены для production или любого non-local развёртывания — перед публичным деплоем нужно сменить и применить тонкую настройку доступа RabbitMQ.

OpenAPI документация: http://localhost:8000/docs (line-provider) и http://localhost:8001/docs (bet-maker). AsyncAPI документация publish/consume контракта: http://localhost:8000/asyncapi и http://localhost:8001/asyncapi.

Полный happy-path сценарий — см. раздел [Reviewer walkthrough](#reviewer-walkthrough) ниже.

Остановить стек:

```bash
docker compose down
```

## Reviewer walkthrough

Полный happy-path сценарий «создать событие → поставить ставку → завершить событие → проверить settle» в 5 шагов (≤ 1 минуты после `docker compose up -d`):

```bash
# 1. start stack (если ещё не запущен)
cp .env.example .env && docker compose up -d

# 2. дождаться healthy
docker compose ps   # ожидаем (healthy) на postgres / rabbitmq / line-provider / bet-maker

# 3. создать событие в line-provider (state=NEW по умолчанию)
EVENT_ID=00000000-0000-0000-0000-000000000001
curl -s -X POST http://localhost:8000/event \
  -H 'content-type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\",\"coefficient\":\"1.50\",\"deadline\":\"2030-01-01T00:00:00+00:00\"}"

# 4. положить ставку в bet-maker
curl -s -X POST http://localhost:8001/bet \
  -H 'content-type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\",\"amount\":\"10.00\"}"

# 5. завершить событие FINISHED_WIN -> consumer settle -> bet становится WON
curl -s -X PUT http://localhost:8000/event/$EVENT_ID \
  -H 'content-type: application/json' \
  -d '{"coefficient":"1.50","deadline":"2030-01-01T00:00:00+00:00","state":"FINISHED_WIN"}'

# 6. убедиться, что ставка settled (status=WON, обычно через ~1с — consumer; reconciler — fallback)
sleep 1
curl -s http://localhost:8001/bets | jq '.[] | {id, status, amount}'
```

Ожидаемый итог 6-го шага: `{"status": "WON", "amount": "10.00", ...}`. Атрибут `settled_via` (значения `consumer` / `reconciler`) пишется в колонку `bets.settled_via` сервером и виден через `psql` или structlog-событие `settle.committed`; в HTTP-ответе `GET /bets` / `GET /bet/{id}` он не сериализуется — `BetRead` намеренно минимальна. На happy-path settle проходит через consumer; при потерянном AMQP-сообщении reconciler через `RECONCILIATION_INTERVAL_S` (default 30s) доводит до того же `WON`.

Сценарий drop-publish (демонстрация reconciler-ветки) автоматизирован в `tests/bet_maker/integration/test_reconciler_drop_publish.py`.

## Architecture

```
                  HTTP (reviewer curl)
                    |
                    v
+----------------+   POST/PUT/GET   +----------------+
| reviewer cli   | ---------------> | line-provider  |
+----------------+                  |    :8000       |
                                    |  (in-memory)   |
                                    +-------+--------+
                                            | AMQP publish
                                            | exchange: bsw.events
                                            | routing: event.finished.{win|lose}
                                            v
                                    +----------------+
                                    |   RabbitMQ     | --(x-dead-letter-exchange)--> DLX -> DLQ
                                    |   :5672        |   bsw.events.dlx
                                    +-------+--------+   bet_maker.events.finished.dlq
                                            | AMQP consume
                                            | queue: bet_maker.events.finished
                                            | manual ack, prefetch=10
                                            v
+----------------+   POST/GET /bet  +----------------+   FOR UPDATE     +----------------+
| reviewer cli   | ---------------> |   bet-maker    | SKIP LOCKED      |  PostgreSQL    |
+----------------+                  |    :8001       | ---------------> |    :5432       |
                                    | + reconciler   |   SELECT/UPDATE  |   (bsw DB)     |
                                    +-------+--------+                  +----------------+
                                            | HTTP GET /event/{id}
                                            | (reconciler defence-in-depth)
                                            +-----> line-provider
```

**Слои** (одинаково для обоих сервисов):
- `api/` — FastAPI routes + FastStream RabbitRouter handler (Rabbit = транспорт API) + lifespan + middleware
- `facades/` — DI-провайдеры (UoW, EventBus, http-клиенты) и Protocol-абстракции
- `interactors/` — бизнес-операции (`create_event`, `set_event_state`, `place_bet`, `settle_bets_for_event`, `cancel_bets_for_event`)
- `selectors/` — read-only запросы поверх `AsyncSession` (`get_event_by_id`, `list_active_events`, `get_pending_locked`, `get_pending_event_ids`, `list_bets`, `get_bet_by_id`)
- `uow/` — `AbstractUnitOfWork` (ABC) + `PostgresUnitOfWork` (только bet-maker; собственник транзакции, единственный канал к `AsyncSession`)
- `helpers/` — чистые функции (state-machine, `quantize_amount`, `quantize_coefficient`)
- `schemas/` — Pydantic v2 DTO (request/response + AMQP-сообщения; `ErrorDetail`)
- `infrastructure/` — engine + sessionmaker (bet-maker); in-memory store (line-provider)
- `jobs/` — reconciliation background task (только bet-maker)
- `messaging/` — routing keys (константы)

**RabbitMQ топология:**
- Exchange `bsw.events` (topic, durable). Routing key `event.finished.{win|lose}`.
- Queue `bet_maker.events.finished` (durable, manual ack, prefetch=10). Bound через wildcard `event.finished.*`.
- DLX `bsw.events.dlx` + DLQ `bet_maker.events.finished.dlq` для poison-сообщений (`ValidationError` / `UnsupportedSchemaVersion` / `IntegrityError`).

**Unit of Work (bet-maker):** одна `AsyncSession` на бизнес-операцию. Контракт публичен через `AbstractUnitOfWork(ABC)` — интеракторы зависят от абстракции, FastAPI-DI возвращает `PostgresUnitOfWork`. Транзакция управляется только `async with uow:` (`__aenter__` / `__aexit__`), публичных `commit()`/`rollback()`/`execute()` нет. `uow.session` — единственный handle, к которому обращаются интеракторы; `expire_on_commit=False` позволяет безопасно читать ORM-атрибуты после `await session.flush()`. Чтения (включая `FOR UPDATE SKIP LOCKED` + status-фильтр) живут в `selectors/`, принимают `AsyncSession` напрямую и не управляют транзакцией.

**Reconciliation** — `asyncio.Task` в lifespan, период = `RECONCILIATION_INTERVAL_S` (default 30s). Тянет PENDING-`event_id` через `selectors/get_pending_event_ids`, дёргает `GET /event/{id}` у line-provider; если LP вернул FINISHED — settle через тот же `settle_bets_for_event` interactor, что и consumer; если LP вернул 404 — `cancel_bets_for_event` помечает ставки `CANCELLED`. Per-event-id корреляция протягивается в логи через `structlog.contextvars.bound_contextvars(event_id=…)`.

AsyncAPI документация AMQP-контракта: `:8000/asyncapi` (publisher side) и `:8001/asyncapi` (consumer side). Генерируется FastStream автоматически из `@router.publisher` / `@router.subscriber` декораторов — никаких ручных YAML.

## Reliability

Core Value: **ставка никогда не остаётся в статусе PENDING после того, как событие завершилось.** Эшелонированные защиты:

1. **Durable queue + persistent messages.** RabbitMQ-сообщения переживают рестарт брокера. Queue `bet_maker.events.finished` и exchange `bsw.events` объявлены `durable=True`. См. `src/bet_maker/api/messaging.py` (`RabbitQueue(..., durable=True)` + `RabbitExchange(..., durable=True)`).
2. **Manual ack ПОСЛЕ commit транзакции.** Consumer-handler передаёт `uow: AbstractUnitOfWork` в interactor; interactor единолично владеет `async with uow:` блоком — handler ack-ает сообщение только после успешного выхода из interactor. На любом исключении до commit — `reject(requeue=False)` (poison → DLQ) или эквивалент через выход из tenacity-retry. См. `src/bet_maker/api/messaging.py` (`ack_policy=AckPolicy.MANUAL`). Регрессионный тест с реальным RabbitMQ + PG в `tests/bet_maker/test_messaging.py` доказывает, что хендлер не open-ит UoW сам (предотвращает double-`__aenter__` на не-реентерабельной UoW).
3. **FOR UPDATE SKIP LOCKED.** При одновременной работе consumer и reconciler против одного `event_id` row-lock с `skip_locked=True` гарантирует, что один из них получает строки на settle, второй наблюдает 0 строк и идёт в no-op-ветку. Status-фильтр `WHERE status='PENDING'` довершает идемпотентность для redelivery после успешного settle. См. `src/bet_maker/selectors/get_pending_locked.py` (статический audit в `tests/audit/test_static.py` фиксирует инвариант).
4. **DLX + DLQ + bounded in-handler retries.** Poison (`ValidationError` / `UnsupportedSchemaVersion` / `IntegrityError`) → `reject(requeue=False)` → DLQ сразу. Transient (`OperationalError`, `asyncio.TimeoutError`) — 3 попытки с exponential backoff внутри handler через tenacity; на исчерпании — тоже `reject(requeue=False)` → DLQ (reconciler доберёт). `nack(requeue=True)` НЕ используется — это путь к unbounded requeue loops. См. `src/bet_maker/api/messaging.py`.
5. **Reconciler defence-in-depth.** Если AMQP-сообщение всё-таки потерялось (broker рестарт без durable, queue не bound в нужный момент, race на startup) — `asyncio.Task` каждые `RECONCILIATION_INTERVAL_S` опрашивает line-provider, доводит PENDING-ставки до WON/LOST или CANCELLED. Loop body обёрнут в `try/except Exception:` — одна неудачная итерация не убивает worker. `/health` возвращает 503 если task мёртв. См. `src/bet_maker/jobs/reconciler.py`. Read-only тик берёт сессию через bare `sessionmaker()` (не транзакционный UoW) — никакого лишнего `BEGIN/COMMIT` на чтение.
6. **Lifespan order + SIGTERM exec-form CMD.** Lifespan поднимает PG → httpx → broker → reconciler в нужном порядке; шатдаун — в обратном. `CMD ["python", ...]` exec-form в Dockerfile + `stop_grace_period: 30s` в docker-compose обеспечивают, что SIGTERM доходит до процесса, consumer успевает дренажить in-flight сообщения, и `docker compose down` выходит чисто.

**CANCELLED — extension сверх минимальной спецификации.** Базовое описание задачи перечисляет три статуса ставки: PENDING / WON / LOST. Мы ввели четвёртый — `CANCELLED` — как recovery-статус: reconciler помечает ставки `CANCELLED`, если `GET /event/{id}` у line-provider вернул 404 (событие удалено или line-provider пересоздан без истории). Без CANCELLED ставка осталась бы в PENDING навсегда, что прямо нарушает Core Value.

## Development

Установить зависимости (требуется `uv` 0.11.x, Python 3.10.x):

```bash
uv sync
```

Запустить сервисы локально (без Docker, нужны PG + RabbitMQ доступными):

```bash
uv run python -m line_provider   # порт 8000
uv run python -m bet_maker       # порт 8001
```

Линтеры и тесты:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src tests
uv run pytest -q
uv run pytest -q --cov=src --cov-report=term-missing --cov-fail-under=85   # локальный coverage gate
```

Установить pre-commit хуки в локальный clone:

```bash
uv run pre-commit install
```

Миграции для bet-maker:

```bash
uv run alembic -c src/bet_maker/alembic.ini upgrade head
```

## Tech stack

- **Python** 3.10.x
- **FastAPI** 0.136 + **Uvicorn** (HTTP)
- **FastStream** 0.6 (RabbitMQ через FastAPI `RabbitRouter`; AMQP-клиент `aio-pika` подтягивается транзитивно)
- **SQLAlchemy** 2.0 async + **asyncpg** + **Alembic** 1.18 (только bet-maker)
- **Pydantic** 2.13 + **pydantic-settings** (DTO + типизированный config)
- **httpx** 0.28 (bet-maker → line-provider HTTP-клиент + тестовый `AsyncClient`)
- **structlog** 25 (JSON-логи с per-request `request_id` и per-event `event_id` в contextvars)
- **tenacity** 9 (in-handler retries с exponential backoff)
- **PostgreSQL** 16, **RabbitMQ** 4.2 (management UI)
- **uv** 0.11 (lockfile + venv)
- **ruff** 0.15, **mypy --strict**, **pytest** 9 + **pytest-asyncio** 1, **pre-commit** 4

## Project status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Skeleton + Infrastructure | complete |
| 2 | line-provider domain | complete |
| 3 | bet-maker domain (DB) | complete |
| 4 | bet-maker HTTP integration with line-provider | complete |
| 5 | RabbitMQ integration | complete |
| 6 | Reconciliation job | complete |
| 7 | Polish + Documentation | complete |
| 8 | Flatten `entrypoints/` → `api/` | complete |
| 9 | UoW redesign + Repository removal | complete |

Текущий снимок качества: **355 tests passed, coverage 94.25%, mypy --strict clean, ruff clean**.
