# Phase 8: Flatten entrypoints/ → api/ - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

HTTP-роутеры и FastStream RabbitRouter обоих сервисов (`bet_maker`, `line_provider`) переезжают под `src/<svc>/api/`. Каталог `src/<svc>/entrypoints/` удаляется полностью. `lifespan.py` и `middleware.py` (app-wiring, не transport) переезжают в корень пакета сервиса, рядом с `app.py`. AMQP-константы в `src/<svc>/messaging/routing.py` остаются на месте.

Никакого поведенческого изменения: тот же API surface, тот же AsyncAPI на `/asyncapi`, те же 355+ тестов зелёные, mypy strict + ruff чистые, coverage ≥85% (REFACTOR-05 как cross-cutting quality bar).

</domain>

<decisions>
## Implementation Decisions

### Layout (REFACTOR-01)
- **D-01:** Flat `src/<svc>/api/` для всех транспортов. Никаких nested `api/http/` + `api/amqp/` — два транспорта, и они логически равноправны. Rabbit это тоже API.
  - `src/bet_maker/api/` → `bets.py`, `events.py`, `health.py`, `messaging.py`, `__init__.py`
  - `src/line_provider/api/` → `events.py`, `health.py`, `messaging.py`, `__init__.py`
- **D-02:** `lifespan.py` и `middleware.py` живут в корне пакета сервиса (`src/<svc>/lifespan.py`, `src/<svc>/middleware.py`) рядом с `app.py`. Это app-wiring, не transport. В `api/` они не идут — это путало бы границы. Отдельный пакет `app/` не создаём (`python -m <svc>` ищет `__main__.py`, лишний уровень не нужен).
- **D-03:** `src/<svc>/messaging/routing.py` (AMQP routing-key константы) остаётся как есть. Это чистые данные, не код транспорта. Phase 10 может вынести в shared, если решит, что это уместно — у LP и BM сейчас разные константы (LP публикует, BM читает), но граница тонкая.

### Migration scope (REFACTOR-05)
- **D-04:** Tests и audit обновляются в локштепе с переездом, в той же фазе. Конкретно:
  - все `from <svc>.entrypoints...` → `from <svc>....` (новые пути) — и в `src/`, и в `tests/`
  - `tests/audit/test_static.py::test_subscribers_have_manual_ack` и `test_durable_queue_and_exchange` сейчас читают `src/bet_maker/entrypoints/messaging.py` — путь обновить на `src/bet_maker/api/messaging.py`
  - `tests/audit/test_static.py::test_compose_command_exec_form` (новый из batch №1) не затронут
  - tests/conftest.py — если ссылается на entrypoints, обновить
  - после переезда: `git grep -rE 'from (bet_maker|line_provider)\.entrypoints'` должен возвращать 0 hits; `find src -type d -name entrypoints` — 0 каталогов
- **D-05:** Phase 8 НЕ трогает структуру самих тестов (директория `tests/`, fixture-разводка). Только imports и audit-paths.

### Claude's Discretion
- Порядок переезда (сначала bet_maker или line_provider) и granularity коммитов — на усмотрение planner'а в plan-phase. Лучше один сервис → второй сервис, чтобы коммиты были атомарны по сервису.
- `__init__.py` в `api/` — пустой или экспортирует все routers агрегатом — на усмотрение реализации. Текущий стиль (`from <svc>.entrypoints.api import bets, events, health` в `app.py`) можно сохранить как `from <svc>.api import bets, events, health, messaging`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/ROADMAP.md` §Phase 8 — goal, success criteria, pitfalls-prevented
- `.planning/REQUIREMENTS.md` §v1.1 — REFACTOR-01, REFACTOR-05
- `.planning/quick/20260518-batch1-cleanup/SUMMARY.md` §"Open / handed off to batch №2" — handoff context

### Current code (will move)
- `src/bet_maker/entrypoints/api/bets.py`, `events.py`, `health.py` — HTTP routes
- `src/bet_maker/entrypoints/messaging.py` — FastStream RabbitRouter (consumer)
- `src/bet_maker/entrypoints/lifespan.py`, `middleware.py`
- `src/bet_maker/app.py` — FastAPI factory (imports above)
- `src/line_provider/entrypoints/api/events.py`, `health.py`
- `src/line_provider/entrypoints/messaging.py` — FastStream RabbitRouter (publisher)
- `src/line_provider/entrypoints/lifespan.py`, `middleware.py`
- `src/line_provider/app.py` — FastAPI factory (imports above)

### Static audit that knows the old paths
- `tests/audit/test_static.py::test_subscribers_have_manual_ack` — reads `src/bet_maker/entrypoints/messaging.py`
- `tests/audit/test_static.py::test_durable_queue_and_exchange` — reads same file

### Invariants to preserve (no behavioural drift)
- `src/<svc>/messaging/routing.py` — AMQP routing-key constants stay put
- FastAPI `app.include_router(...)` wiring stays in `app.py` — only import paths change
- AsyncAPI docs at `/asyncapi` — must still resolve after move
- AckPolicy.MANUAL, prefetch=10, durable exchange/queue — invariants on the moved `messaging.py`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/bet_maker/app.py::build_app` — FastAPI factory pattern уже корректный, только import paths меняются
- `src/line_provider/app.py::build_app` — то же
- `src/<svc>/messaging/routing.py` — устойчивые AMQP-константы, не трогаем

### Established Patterns
- **One RabbitRouter per service** — инвариант, новый layout не должен дублировать router
- **app.py ничего не знает о деталях** — только `app.include_router(...)` и `app.add_middleware(...)`. Сохраняем
- **lifespan возвращает context manager и пиннит ресурсы в app.state** — сохраняем

### Integration Points
- `src/bet_maker/__main__.py` / `src/line_provider/__main__.py` — entry для `python -m <svc>`. Эти файлы сейчас импортируют `app.py`, не должны меняться
- `Dockerfile` — после batch №1 не COPY-ит `entrypoints/` отдельно, всё едет через `src/`. Не ломается
- Pyproject `[tool.hatch.build.targets.wheel]` — три пакета (`src/line_provider`, `src/bet_maker`, `src/config`). Не меняется
- `alembic/env.py` (теперь `src/bet_maker/alembic/env.py`) — импортирует `bet_maker.models`, не `entrypoints/`. Не затронут

</code_context>

<specifics>
## Specific Ideas

- Запасной grep-аудит для верификации после переезда: `git grep -E 'from (bet_maker|line_provider)\.entrypoints'` → 0 hits; `find src -type d -name entrypoints` → 0 каталогов.
- Возможный новый static audit (планировщику на рассмотрение): `tests/audit/test_static.py::test_no_entrypoints_dir` — assert `src/<svc>/entrypoints` не существует. Закрепляет регрессию.

</specifics>

<deferred>
## Deferred Ideas

- **Nested `api/http/` + `api/amqp/`** — отброшено как избыточное для двух транспортов и двух-трёх файлов на транспорт. Если появится gRPC или нужно будет разносить по транспортам — это уже отдельная фаза.
- **`src/<svc>/amqp/` package** — может появиться в Phase 10, если shared-пакет окажется тяжёлым на AMQP-стороне. Сейчас не нужен.
- **`__init__.py` агрегат `api.routers = (bets, events, health, messaging)`** — техническое решение planner'а, не decision-level.
- **Refactor структуры самих `tests/`** — отдельно, не в Phase 8.

</deferred>

---

*Phase: 8-flatten-api*
*Context gathered: 2026-05-18*
