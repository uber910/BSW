# Phase 6: Reconciliation job - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-18
**Phase:** 06-reconciliation-job
**Areas discussed:** Polling strategy, Reconciler HTTP client, Per-event error isolation, /health + startup/shutdown

---

## Polling strategy

### Turn 1 — Как reconciler тащит terminal-state events?

| Option | Description | Selected |
|--------|-------------|----------|
| N×GET /event/{id} по DISTINCT pending event_id | Новый метод репозитория `BetRepository.get_pending_event_ids() -> list[UUID]` (SELECT DISTINCT event_id WHERE status='PENDING'). Дальше для каждого — GET /event/{id}, фильтруем события с state in {FINISHED_WIN, FINISHED_LOSE}. Точно, тривиально, переиспользует HttpEventLookup. Минус: N HTTP/tick, хватает для test-task scope. | |
| GET /events + diff (deadline-ы как hint) | GET /events (active = NEW + deadline > now) → active_ids. SELECT DISTINCT event_id WHERE PENDING → pending_ids. candidates = pending_ids - active_ids. Для каждого candidate → GET /event/{id} для подтверждения terminal state. Меньше HTTP в happy path, но два контрактных вызова + diff-логика и deadline-инварианты. | |
| Добавить GET /events?ids=... в line-provider | Расширить контракт LP и добавить batch-эндпоинт. Был deferred в P4 как perf-extension. Стоимость: + планы и тесты на line-provider, + схема. Оправдано только под большим N. | |

**User's free-text response:** «я думаю все у кого дедлайн прошел просто маркировать как зависшие и канселлитть все ставки».

### Turn 2 — Уточнение: что значит «канселить»?

| Option | Description | Selected |
|--------|-------------|----------|
| Держать текущий контракт (PENDING→WON/LOST) | Reconciler тащит GET /event/{id} для distinct event_id из PENDING, сеттлит только если LP вернул FINISHED_WIN/FINISHED_LOSE. Никаких упреждающих решений без LP. = вариант A выше. | |
| **Добавить CANCELLED и deadline-based fallback** | Расширить BetStatus CANCELLED (Alembic migration). Ревьюировать Bet ORM или хранить deadline при POST /bet. Реконсилер сначала спрашивает LP; если евент пропал/404 или сильно просрочен — кансели́ть. Новый контракт, не в ТЗ. | ✓ |
| Оптимизация: фильтровать по deadline перед LP | Reconciler сначала GET /events (active = NEW+future deadline), вычисляет candidates = pending_event_ids - active_event_ids (всё что нет в active и есть в PENDING — это либо finished, либо past deadline+NEW). По каждому candidate — GET /event/{id}, settle только на terminal state. Ставки на NEW+past-deadline events НЕ трогаются (вычёркивает предыдущий вариант B). | |

**User's choice:** Добавить CANCELLED и deadline-based fallback.

### Turn 3 — Какой trigger для CANCELLED?

| Option | Description | Selected |
|--------|-------------|----------|
| **LP вернул 404 (событие удалено)** | Только если GET /event/{id} → 404 — событие пропало из LP, settle невозможен. Без deadline-колонки в Bet (нет новых миграций). Риск: in-memory LP не удаляет события (по ТЗ), сценарий реально возникает только при рестарте LP (in-memory очищается) — фактически и есть тот случай, который пытаемся покрыть. | ✓ |
| Deadline + grace, не хранить в Bet | Каждый tick: GET /event/{id} → если state NEW и deadline + STALE_GRACE_S (новый setting, default 1h?) < now → cancel. Дедлайн видим из EventSnapshot (уже имеет deadline). Без новых колонок в Bet. Но риск упреждающего cancel выигрышной ставки если LP лагает больше часа — нужны cool параметры. | |
| Deadline + grace, хранить event_deadline в Bet | Bet ORM получает колонку event_deadline (Alembic). POST /bet берёт deadline из EventSnapshot при валидации. Reconciler SELECT WHERE PENDING AND event_deadline+GRACE<now — быстрый SQL-фильтр без HTTP. Дальше GET /event/{id} для подтверждения и cancel если всё ещё NEW. Больше схемы, лучше работает на тысячах ставок (ТЗ упоминает сценарий). | |

**User's choice:** LP вернул 404 (событие удалено).

**Notes:** Это минимально-инвазивный путь — CANCELLED только при явном 404. Никаких deadline-based решений, никаких новых колонок Bet ORM, никакого упреждения LP. ТЗ говорит про 3 статуса; расширение до 4 — наша инженерная трактовка, документируется sync-task в Plan 06-01 (REQUIREMENTS.md BM-05 + ROADMAP.md Phase 6 Goal/SC) + README P7 как «инженерная трактовка для recovery».

---

## Reconciler HTTP client

| Option | Description | Selected |
|--------|-------------|----------|
| **Отдельный HttpEventLookup в lifespan** | lifespan создаёт второй HttpEventLookup(http_client=..., attempts=5, max_backoff=10.0), пинит как app.state.reconciler_event_lookup. Reconciler task берёт его из app.state. Оба экземпляра разделяют singleton httpx.AsyncClient (без двойного pool). Просто и реиспользует EventLookup Protocol. | ✓ |
| Inline retry-decorator в reconciler | Без нового экземпляра. Reconciler сам берёт http_client и строит `make_retry_decorator(5, 10.0)` внутри; не использует HttpEventLookup. Плюс: реконсилер видит raw httpx, может различать 404 явно без None-mapping. Минус: дублируется логика HttpEventLookup. | |
| Параметризовать get_event(attempts, max_backoff) | Изменить сигнатуру EventLookup Protocol в P3 D-11. Нарушает симметрию Protocol (StubEventLookup не понимает retry-params). Отрицается — не ломать P3 Protocol. | |

**User's choice:** Отдельный HttpEventLookup в lifespan.

**Notes:** P4 D-04 уже зафиксировал retry-policy (5 attempts, max_backoff=10s) и settings name pattern. Этот выбор сохраняет симметрию с P3 D-11 / P4 D-14 (стиль `app.state.event_lookup` для production EventLookup).

---

## Per-event error isolation

| Option | Description | Selected |
|--------|-------------|----------|
| **Try-per-event-id: log + continue** | Каждый event_id обрабатывается в своём try/except Exception — логируем и идём к следующему. Снаружи try/except Exception на весь tick (R8: луп никогда не выходит молча). Максимальная liveness, типичный паттерн для фоновых jobs. | ✓ |
| Whole-tick try/except | Одна try/except на весь tick. Первый падение прерывает tick, оставшиеся event_id ждут следующего interval. Проще, но одна битая ставка останавливает весь batch. | |
| Гибрид: HTTP-ошибки isolated, PG кладёт tick | LineProviderUnavailable и cancel/settle interactor ошибки ловятся per-event (continue). PG OperationalError/DBAPIError — бросается из inner loop в outer try/except, весь tick падает (потому что PG-blip вероятно распространится на все event_id). Более точный, но сложнее. | |

**User's choice:** Try-per-event-id: log + continue.

**Notes:** Двухуровневая структура try/except закреплена в D-10/D-11 CONTEXT.md. PG OperationalError на `get_pending_event_ids` пробрасывается из inner UoW в outer try/except (потому что без списка event_id'ов tick невозможен) — log+continue до следующего interval.

---

## /health + startup/shutdown

### Turn 1 — /health: когда выдать 503 по reconciler?

| Option | Description | Selected |
|--------|-------------|----------|
| **task.done() == True → 503** | Reconciliation предполагает бесконечный цикл. Любое done() = либо падение, либо cancel. Одна проверка `not task.done()`. Просто и хватает для СЦ#3. (Буква ROADMAP R8.) | ✓ |
| task.done() OR task.exception() not None → 503 | Параноидальная версия: помимо done() явно вызывать .exception() (потребует done()). Даёт логу reason. Но .exception() падает если not done() — нужен guard. Эквивалентно (с done() подразумевается exception). | |
| Авторестарт task при фейле | /health watch-dog re-creates task если done(). Сложнее и риск flapping; обычно это работа внешнего supervisor'а (uvicorn/docker). Не рекомендую для test-task. | |

**User's choice:** task.done() == True → 503.

### Turn 2 — Стартовый tick и shutdown reconciler'а?

| Option | Description | Selected |
|--------|-------------|----------|
| **sleep(interval) перед первым tick + cancel+await на shutdown** | Startup: в lifespan создаётся asyncio.create_task(reconciliation_loop, name="reconciliation") ПОСЛЕ declare topology. Loop: await asyncio.sleep(interval) ПЕРЕД первым tick — без лишнего шума на холодном старте. Shutdown: task.cancel(); await task (suppress CancelledError) первым в finally-блоке, ДО broker.close() и http_client.aclose(). | ✓ |
| Первый tick сразу + cancel+await | Loop: tick → sleep → tick. События обрабатываются сразу после startup (полезно если были простои randomly). Shutdown тот же. | |
| Первый tick сразу без await task на shutdown | task.cancel() без последующего await — риск in-flight HTTP/PG не закрыться чисто. Не рекомендуется — task.cancel() в asyncio всегда должен сопровождаться await чтобы повысить CancelledError. | |

**User's choice:** sleep(interval) перед первым tick + cancel+await на shutdown.

**Notes:** В D-16 CONTEXT.md: reconciler — **первый** в finally lifespan'а потому что он держит UoW (PG-сессию) и httpx requests внутри tick. Закрытие http_client / engine ДО завершения task'а вызовет OperationalError / RuntimeError в in-flight операциях. Cancel + await + suppress — чистый выход.

---

## Claude's Discretion

- Точный путь Alembic-миграции для `ALTER TYPE betstatus ADD VALUE` в async-template — researcher уточнит (Context7 alembic/sqlalchemy). Idempotent через `ADD VALUE IF NOT EXISTS` (PG 9.6+).
- Размещение `reconciliation_loop`: `bet_maker/entrypoints/reconciliation.py` vs `bet_maker/messaging/reconciliation.py`. Предпочтительно entrypoints/ (lifecycle-композиция, не routing).
- Точная реализация monkeypatch на `RabbitEventBus.publish` для D-23 Сценарий 2 — researcher уточнит fixture-pattern.
- Логирование namespaces `reconciler.tick.{start,end,noop,failed}` + `reconciler.event.{settled,cancelled,still_new,failed}` — точные имена planner определит.
- `_reconcile_event` стиль (отдельная функция vs метод Reconciler класса с `__init__(sessionmaker, event_lookup)`).
- `CancelResult` vs reuse `SettleResult` с `terminal_state=None`. CONTEXT.md D-04 выбрал отдельный DTO; planner может оспорить.

## Deferred Ideas

- Deadline-based cancel fallback — отвергнут пользователем (только 404-trigger). Future hardening.
- GET /events?ids=... batch endpoint в LP — был deferred в P4, остаётся.
- Reconciler-публикация в RMQ — out of scope.
- Auto-restart task через /health watchdog — отвергли, внешний supervisor.
- Jitter для interval — single-instance, не нужен.
- Метрики Prometheus — info-логи достаточны.
- CANCELLED-cause колонка — пока только settled_via='reconciler' + log.
- Reconciler в отдельном процессе — P5 D-19 закрепил один процесс.
- Grace period для свежих PENDING bet'ов — settle idempotent, не нужен.
- Concurrent HTTP внутри tick через gather+semaphore — sequential loop достаточен.
- EventState parity test между сервисами — отложен на P7.
