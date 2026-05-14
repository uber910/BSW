# BSW Betting System

[![ci](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)

Тестовое задание Middle Python developer: микросервисная система приёма ставок на спортивные события. Два асинхронных сервиса (`line-provider`, `bet-maker`), интеграция через RabbitMQ, история ставок в PostgreSQL, reconciliation как защита от потерянных сообщений.

Полная архитектура и требования: [.planning/PROJECT.md](.planning/PROJECT.md), [.planning/ROADMAP.md](.planning/ROADMAP.md).

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

Оба должны вернуть `{"status":"ok"}`.

RabbitMQ Management UI: http://127.0.0.1:15672 (логин/пароль: `guest` / `guest`).

> **Note:** `guest:guest` — это дефолтные test-credentials RabbitMQ, использующиеся только в локальной разработке. Management UI забинден на `127.0.0.1` (loopback) и недоступен извне хоста; AMQP-порт 5672 не публикуется наружу. Эти credentials НЕ предназначены для production или любого non-local развёртывания — перед публичным деплоем нужно сменить и применить тонкую настройку доступа RabbitMQ.

Остановить стек:

```bash
docker compose down
```

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
```

Установить pre-commit хуки в локальный clone:

```bash
uv run pre-commit install
```

Миграции для bet-maker (создаются начиная с Phase 3):

```bash
uv run alembic upgrade head
```

## Architecture

TODO: подробности в [.planning/research/ARCHITECTURE.md](.planning/research/ARCHITECTURE.md). Будет наполнено в Phase 7.

## Reliability

TODO: гарантии durable queue, manual ack, DLQ, reconciliation job, `FOR UPDATE SKIP LOCKED`. Будет наполнено в Phase 7.

## Project status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Skeleton + Infrastructure | in progress |
| 2 | line-provider domain | pending |
| 3 | bet-maker domain (DB) | pending |
| 4 | bet-maker HTTP integration | pending |
| 5 | RabbitMQ integration | pending |
| 6 | Reconciliation job | pending |
| 7 | Polish + Documentation | pending |
