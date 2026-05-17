# BSW Betting System

## What This Is

Тестовое задание на позицию Middle Python developer: микросервисная система приёма ставок на спортивные события. Состоит из двух независимых асинхронных сервисов — `line-provider` (источник событий и их статусов) и `bet-maker` (приём ставок, история, начисление статусов). Цель — продемонстрировать инженерную зрелость: чистую слоистую архитектуру, асинхронность сквозь стек, надёжную интеграцию через очередь, полное покрытие тестами и type hints, production-уровень инфраструктуры.

## Core Value

**Ставка никогда не остаётся в статусе «ещё не сыграла» после того, как событие завершилось.** Это явное требование ТЗ. Вся архитектура интеграции (durable queue + manual ack + reconciliation job) подчинена именно этому инварианту.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Сервис line-provider:**

- [ ] Управление событиями в памяти (event_id, coefficient, deadline, state)
- [ ] Утилитарное API создания/обновления событий
- [ ] API получения списка активных событий (deadline > now)
- [ ] API получения одного события по id
- [ ] Публикация события о смене статуса (NEW → FINISHED_WIN / FINISHED_LOSE) в RabbitMQ

**Сервис bet-maker:**

- [ ] `GET /events` — список активных событий (с допустимым отставанием от line-provider)
- [ ] `POST /bet` — приём ставки (event_id, amount > 0, две знаков после запятой)
- [ ] `GET /bets` — история всех ставок со статусом (PENDING / WON / LOST)
- [ ] Хранение ставок в PostgreSQL через async SQLAlchemy + Unit of Work
- [ ] Consumer событий из RabbitMQ → атомарное обновление статусов связанных ставок
- [ ] Reconciliation job — периодически добирает статус для PENDING-ставок по завершённым событиям (защита от потери сообщений)

**Инфраструктура:**

- [ ] Docker-образы для line-provider и bet-maker (Python 3.10, slim)
- [ ] docker-compose: оба сервиса + PostgreSQL + RabbitMQ + management UI
- [ ] Alembic-миграции для bet-maker
- [ ] Healthcheck-эндпоинты `/health` (проверка PG и RabbitMQ)
- [ ] Structured logging (structlog, JSON-формат)

**Качество:**

- [ ] Полные type hints (mypy strict проходит без ошибок)
- [ ] Pytest: unit-тесты на interactor/selector/helper, integration на API + очередь
- [ ] Линтер ruff (lint + format) и pre-commit hooks
- [ ] GitHub Actions CI: lint + typecheck + tests
- [ ] README с инструкцией запуска

### Out of Scope

- **Аутентификация/авторизация пользователей** — ТЗ не требует, добавит сложности без ценности для оценки
- **UI / фронтенд** — ТЗ описывает только HTTP API
- **Несколько типов ставок (только выигрыш первой команды)** — явно ограничено в ТЗ
- **Ничьи в событиях** — явно исключены в ТЗ
- **Outbox-pattern для line-provider** — требует БД в line-provider, что противоречит требованию in-memory хранения
- **Kafka / горизонтальное шардирование** — overkill для тестового задания, RabbitMQ покрывает требования по производительности
- **Реальная балансировка нагрузки / k8s** — docker-compose достаточно для демонстрации

## Context

**Природа проекта:** Тестовое задание — короткий цикл разработки, оценивается работодателем по чек-листу инженерных компетенций. Важна не только функциональность, но и видимое качество: структура, читаемость, тесты, документация.

**Шаблон line-provider:** GitLab-репозиторий `sandbox8861731/bsw-test-line-provider` содержит минимальный пример (один файл `app.py`, dict в памяти, 3 эндпоинта, без интеграции). Решено писать line-provider с нуля для единства стиля с bet-maker и демонстрации навыков, но логика (in-memory, простое API) переиспользуется концептуально.

**Производительность:** В реальном мире тысячи активных событий и на порядки больше ставок. Архитектура должна это выдерживать — отсюда выбор асинхронности по всему стеку, индексов в PG, durable очереди вместо синхронных вызовов.

**Надёжность интеграции:** Главный риск — потерянное сообщение о завершении события приводит к «зависшей» ставке. Защита эшелонирована: durable очередь + manual ack + DLQ + периодический reconciliation job (subscribe PENDING-ставок и пуллинг статуса события напрямую из API line-provider).

## Constraints

- **Tech stack**: Python 3.10 — фиксировано ТЗ как рекомендованная версия
- **Tech stack**: FastAPI — рекомендованный ТЗ фреймворк
- **Tech stack**: Полностью асинхронное взаимодействие сервисов и БД — явное требование ТЗ
- **Tech stack**: Хранение событий line-provider только in-memory — требование ТЗ
- **Infrastructure**: Все компоненты докеризованы, запуск через `docker compose up` — требование ТЗ
- **Quality**: PEP8, type hints, тесты — указаны как плюсы; в нашей трактовке — обязательные
- **Timeline**: Тестовое задание — оценивается готовый результат, ориентир разумный (несколько дней работы)
- **Reliability**: Невозможность зависания ставки в PENDING после завершения события — явное требование ТЗ

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Микросервисы: line-provider + bet-maker | Жёсткое требование ТЗ | — Pending |
| PostgreSQL для bet-maker (asyncpg + SQLAlchemy 2.0 async) | Реляционная модель ставок, ACID, удобные запросы истории | — Pending |
| In-memory dict в line-provider | Требование ТЗ | — Pending |
| RabbitMQ + FastStream для межсервисного обмена | Надёжность (durable + ack + DLQ), декларативный FastStream, естественная асинхронность | — Pending |
| Reconciliation job в bet-maker | Закрывает требование «ставка не зависает» если сообщение потеряно | — Pending |
| Unit of Work + Repository pattern для PG | Lazy commits, единая транзакция на бизнес-операцию, тестируемость | — Pending |
| Слоистая архитектура (entrypoints / facades / interactors / selectors / helpers) | Чёткое разделение ответственности, CQRS lite (interactors=write use cases, selectors=read-only queries), helpers — чистые функции без сайд-эффектов, удобное unit-тестирование | — Pending |
| Монорепо, src/ layout, 2 пакета | `src/line_provider/` + `src/bet_maker/`, общий pyproject и dev-deps, меньше дублирования | — Pending |
| uv как менеджер пакетов | Современный, быстрый, lockfile, замена pip+venv+pip-tools | — Pending |
| structlog для логов | JSON-логи с контекстом, production-style — показывает зрелость | — Pending |
| Alembic для миграций | Стандарт для SQLAlchemy, демонстрирует production-готовность | — Pending |
| Healthcheck-эндпоинты `/health` | Проверка зависимостей (PG, RabbitMQ), нужны для docker-compose healthchecks | — Pending |
| ruff (lint + format) + mypy strict + pre-commit | Современная toolchain, заменяет flake8+black+isort, единый стандарт | — Pending |
| GitHub Actions CI | Автоматическая проверка PR, видимый признак инженерной зрелости | — Pending |
| Писать line-provider с нуля, не брать шаблон | Единый стиль с bet-maker, демонстрация навыков, шаблон слишком минимален | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-17 after Phase 04 (bet-maker HTTP integration with line-provider) — BM-04 validated; 244 tests passing; coverage src/bet_maker 95.35%.*
