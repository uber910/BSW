# Phase 8: Flatten entrypoints/ → api/ - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 8-flatten-api
**Areas discussed:** Rabbit router placement, lifespan/middleware placement, messaging routing dir, tests scope

---

## Rabbit router placement

| Option | Description | Selected |
|--------|-------------|----------|
| `src/<svc>/api/messaging.py` рядом с HTTP | Flat api/ с 4 файлами: bets, events, health, messaging | ✓ |
| `src/<svc>/api/http/` + `src/<svc>/api/amqp/` | Nested по транспорту | |
| `src/<svc>/api/` HTTP + `src/<svc>/messaging/` RabbitRouter | RabbitRouter в существующем `messaging/` рядом с routing.py | |

**User's choice:** Flat api/ с messaging.py.
**Notes:** Соответствует исходному пожеланию «Rabbit — тоже API». Nested избыточен для двух файлов на транспорт.

---

## lifespan.py / middleware.py placement

| Option | Description | Selected |
|--------|-------------|----------|
| Рядом с app.py в корне сервиса | `src/<svc>/lifespan.py`, `src/<svc>/middleware.py` | ✓ |
| `src/<svc>/app/` пакет | app.py + lifespan.py + middleware.py в одном пакете | |
| В `src/<svc>/api/` | Рядом с роутами | |

**User's choice:** В корне сервиса.
**Notes:** lifespan и middleware — это app-wiring, не транспорт. `app/` как пакет добавил бы лишний уровень и потребовал бы `__main__.py` шуфлинг.

---

## messaging/ directory (AMQP routing constants)

| Option | Description | Selected |
|--------|-------------|----------|
| Оставить как есть | `src/<svc>/messaging/routing.py` не меняется | ✓ |
| Влить в api/messaging.py | Сложить константы в файл RabbitRouter'а | |
| Переименовать в `src/<svc>/amqp/` | Чёткий AMQP-ярлык | |

**User's choice:** Оставить.
**Notes:** Это чистые константы (Final[str] routing keys), отделение от runtime-кода RabbitRouter'а — благо. Phase 10 может вынести в shared при необходимости.

---

## Tests scope

| Option | Description | Selected |
|--------|-------------|----------|
| В локштепе с переездом | imports + audit-paths правим в той же фазе | ✓ |
| Только import-фикс в тестах | Остальные изменения тестов отложить | |

**User's choice:** В локштепе.
**Notes:** `tests/audit/test_static.py` читает `src/bet_maker/entrypoints/messaging.py` напрямую — без обновления путей audit падает, что блокирует REFACTOR-05 (тесты зелёные). Refactor самой структуры папок `tests/` остаётся out-of-scope.

---

## Claude's Discretion

- Порядок переезда (bet_maker первым vs line_provider первым) — на усмотрение planner'а
- Granularity коммитов внутри Phase 8 — planner определит
- Содержимое `api/__init__.py` (пустой vs агрегатор) — реализация
- Опциональный новый audit-тест `test_no_entrypoints_dir` — на усмотрение planner'а

## Deferred Ideas

- Nested `api/http/` + `api/amqp/` — отложено, не оправдано на текущем объёме файлов
- `src/<svc>/amqp/` package — кандидат для Phase 10 при shared-выносе AMQP
- `__init__.py` агрегат `api.routers = (...)` — техническое решение planner'а
- Refactor самой структуры `tests/` (фикстуры, папки) — не в Phase 8
