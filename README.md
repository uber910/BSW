# BSW Betting System

[![ci](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
[![coverage](https://img.shields.io/badge/coverage-85%25-brightgreen.svg)]()

Тестовое задание Middle Python developer: микросервисная система приёма ставок на спортивные события. Два асинхронных сервиса (`line-provider`, `bet-maker`), интеграция через RabbitMQ, история ставок в PostgreSQL, reconciliation как защита от потерянных сообщений.

**Core Value:** ставка никогда не остаётся в статусе PENDING после того, как событие завершилось. Вся архитектура интеграции (durable queue + manual ack + reconciliation job) подчинена этому инварианту.

Полная архитектура: [.planning/research/ARCHITECTURE.md](.planning/research/ARCHITECTURE.md). Каталог требований: [.planning/REQUIREMENTS.md](.planning/REQUIREMENTS.md). Каталог известных pitfalls: [.planning/research/PITFALLS.md](.planning/research/PITFALLS.md).

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

Ожидаемый итог 6-го шага: `{"status": "WON", "amount": "10.00", ...}`. `settled_via` в response доступен через `GET /bet/{id}` — на happy-path equals `"consumer"`; если AMQP-сообщение потеряно, через `RECONCILIATION_INTERVAL_S` (default 30s) reconciler доводит до того же `WON` с `settled_via="reconciler"`.

Сценарий drop-publish (демонстрация reconciler-ветки) автоматизирован в `tests/bet_maker/test_reconciliation_e2e.py` (см. Phase 6).

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
- `entrypoints/` — FastAPI routes + FastStream RabbitRouter handler + lifespan + middleware
- `facades/` — DI-провайдеры (UoW, EventBus, http-клиенты) и Protocol-абстракции
- `interactors/` — бизнес-операции (create_event, set_event_state, place_bet, settle_bets_for_event, cancel_bets_for_event)
- `selectors/` — read-only запросы (get_event_by_id, list_active_events, list_bets, get_bet_by_id)
- `repositories/` — SQLAlchemy 2.0 async-репозитории (только bet-maker; не коммитят — UoW владеет транзакцией)
- `helpers/` — чистые функции (state-machine, quantize_amount, quantize_coefficient)
- `schemas/` — Pydantic v2 DTO (request/response + AMQP-сообщения; ErrorDetail)
- `infrastructure/` — engine + sessionmaker (bet-maker); in-memory store (line-provider)
- `jobs/` — reconciliation background task (только bet-maker)
- `messaging/` — routing keys (константы)

**RabbitMQ топология:**
- Exchange `bsw.events` (topic, durable). Routing key `event.finished.{win|lose}`.
- Queue `bet_maker.events.finished` (durable, manual ack, prefetch=10). Bound через wildcard `event.finished.*`.
- DLX `bsw.events.dlx` + DLQ `bet_maker.events.finished.dlq` для poison-сообщений (ValidationError / UnsupportedSchemaVersion / IntegrityError).

**Unit of Work + Repository:** одна `AsyncSession` на бизнес-операцию, открывается `async_sessionmaker.begin()`, репозитории добавляют/читают, UoW коммитит на успешном выходе. `expire_on_commit=False` — после commit можно безопасно читать ORM-атрибуты.

**Reconciliation** — `asyncio.Task` в lifespan, period = `RECONCILIATION_INTERVAL_S` (default 30s). Тянет PENDING-event_id через `BetRepository.get_pending_event_ids()`, дёргает `GET /event/{id}` у line-provider; если LP вернул FINISHED — settle через тот же `settle_bets_for_event` interactor, что и consumer; если LP вернул 404 — `cancel_bets_for_event` помечает ставки `CANCELLED`.

Подробная топология, лестницы вызовов, и обоснования каждого решения — [.planning/research/ARCHITECTURE.md](.planning/research/ARCHITECTURE.md).

AsyncAPI документация AMQP-контракта: `:8000/asyncapi` (publisher side) и `:8001/asyncapi` (consumer side). Генерируется FastStream автоматически из `@router.publisher` / `@router.subscriber` декораторов — никаких ручных YAML.

## Reliability

Core Value: **ставка никогда не остаётся в статусе PENDING после того, как событие завершилось.** Эшелонированные защиты:

1. **Durable queue + persistent messages.** RabbitMQ-сообщения переживают рестарт брокера. Queue `bet_maker.events.finished` и exchange `bsw.events` объявлены `durable=True`. См. `src/bet_maker/entrypoints/messaging.py` (`RabbitQueue(..., durable=True)` + `RabbitExchange(..., durable=True)`).
2. **Manual ack ПОСЛЕ commit транзакции.** Consumer вызывает `await msg.ack()` только после успешного выхода из `async with AsyncUnitOfWork(...)`. На любом исключении до commit — `reject(requeue=False)` (poison → DLQ) или `nack`-эквивалент через выход из tenacity-retry. См. `src/bet_maker/entrypoints/messaging.py` (`ack_policy=AckPolicy.MANUAL`).
3. **FOR UPDATE SKIP LOCKED.** При одновременной работе consumer и reconciler против одного `event_id` row-lock с `skip_locked=True` гарантирует, что один из них получает строки на settle, второй наблюдает 0 строк и идёт в no-op-ветку. Status-фильтр `WHERE status='PENDING'` довершает идемпотентность для redelivery после успешного settle. См. `src/bet_maker/repositories/bets.py::get_pending_locked`.
4. **DLX + DLQ + bounded in-handler retries.** Poison (`ValidationError` / `UnsupportedSchemaVersion` / `IntegrityError`) → `reject(requeue=False)` → DLQ сразу. Transient (`OperationalError`, `asyncio.TimeoutError`) — 3 попытки с exponential backoff внутри handler через tenacity; на исчерпании — тоже `reject(requeue=False)` → DLQ (reconciler доберёт). `nack(requeue=True)` НЕ используется — это путь к unbounded requeue loops. См. `src/bet_maker/entrypoints/messaging.py`.
5. **Reconciler defence-in-depth.** Если AMQP-сообщение всё-таки потерялось (broker рестарт без durable, queue не bound в нужный момент, race на startup) — `asyncio.Task` каждые `RECONCILIATION_INTERVAL_S` опрашивает line-provider, доводит PENDING-ставки до WON/LOST или CANCELLED. Loop body обёрнут в `try/except Exception:` — одна неудачная итерация не убивает worker. `/health` возвращает 503 если task мёртв. См. `src/bet_maker/jobs/reconciler.py`.
6. **Lifespan order + SIGTERM exec-form CMD.** Lifespan поднимает PG → httpx → broker → reconciler в нужном порядке; шатдаун — в обратном. `CMD ["python", ...]` exec-form в Dockerfile + `stop_grace_period: 30s` в docker-compose обеспечивают, что SIGTERM доходит до процесса, consumer успевает дренажить in-flight сообщения, и `docker compose down` выходит чисто.

**CANCELLED — extension сверх ТЗ.** ТЗ описывает три статуса ставки: PENDING / WON / LOST. Мы ввели четвёртый — `CANCELLED` — как recovery-статус: reconciler помечает ставки `CANCELLED`, если `GET /event/{id}` у line-provider вернул 404 (событие удалено или line-provider пересоздан без истории). Это инженерная трактовка ТЗ, явно задокументированная в [REQUIREMENTS.md](.planning/REQUIREMENTS.md) BM-05 и memory `feedback_verify_against_tz`. Без CANCELLED ставка осталась бы в PENDING навсегда, что прямо нарушает Core Value.

Полный перечень pitfalls и их митигаций: [.planning/research/PITFALLS.md](.planning/research/PITFALLS.md). Codified-аудит «Looks Done But Isn't» с pytest-evidence по каждой проверке: [.planning/phases/07-polish-documentation/07-AUDIT.md](.planning/phases/07-polish-documentation/07-AUDIT.md).

## Development

Установить зависимости (требуется `uv` 0.11.x, Python 3.10.20):

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
uv run mypy src
uv run pytest -q
uv run pytest -q --cov --cov-report=term-missing --cov-fail-under=85   # локальный coverage gate
```

Установить pre-commit хуки в локальный clone:

```bash
uv run pre-commit install
```

Миграции для bet-maker:

```bash
uv run alembic -c src/bet_maker/alembic.ini upgrade head
```

## Next-step extensions

Намеренно не реализовано в v1 — упомянуто для transparency:

- **TTL cache `GET /events`** — отложено в P4 D-01 (ТЗ кэш не требует). Готовая точка расширения — `src/bet_maker/selectors/list_active_events.py`.
- **Prometheus / OpenTelemetry / Grafana** — v2 OBS-01..03 (см. REQUIREMENTS.md).
- **AsyncAPI snapshot offline** — `curl :8001/asyncapi -o asyncapi.json` снимает endpoint в JSON-файл. Endpoint достаточен для онлайн-просмотра; в репо не коммитим, чтобы не дрифтить.
- **Codecov / Coveralls динамический badge** — overkill для test-task. Сейчас static Shields.io 85%. При переходе на public Github можно добавить codecov upload step + динамический badge.
- **`Idempotency-Key` / API versioning / Rate limiting / RFC7807** — v2 API-01..04.
- **Quorum queues / Outbox / Saga** — v2 REL-01..03.

## Project status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Skeleton + Infrastructure | complete |
| 2 | line-provider domain | complete |
| 3 | bet-maker domain (DB) | complete |
| 4 | bet-maker HTTP integration | complete |
| 5 | RabbitMQ integration | complete |
| 6 | Reconciliation job | complete |
| 7 | Polish + Documentation | complete |
