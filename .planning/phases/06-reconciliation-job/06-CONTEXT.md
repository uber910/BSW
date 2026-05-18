# Phase 6: Reconciliation job - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 6 закрывает Core Value инвариант **defence-in-depth**: ставка никогда не остаётся в `PENDING` после того, как событие LP вышло из NEW, даже если AMQP-сообщение Phase 5 потерялось.

Реализация — asyncio background task `"reconciliation"` в одном процессе bet-maker'а (HTTP API + RMQ consumer Phase 5 + reconciler), запускаемая в lifespan **после** declare RMQ-топологии и **до** `yield`. Каждые `RECONCILIATION_INTERVAL_S` (default 30s, pydantic-settings):

1. `BetRepository.get_pending_event_ids()` → `SELECT DISTINCT event_id FROM bets WHERE status='PENDING'`.
2. Для каждого `event_id` — `HttpEventLookup.get_event(event_id)` через **отдельный** `app.state.reconciler_event_lookup` (5 attempts, max_backoff=10s — P4 D-04). Возможные исходы:
   - `EventSnapshot.state in {FINISHED_WIN, FINISHED_LOSE}` → `settle_bets_for_event(uow, event_id=..., terminal_state=..., settled_via="reconciler")` — переиспользуется interactor Phase 5 D-17 без изменений.
   - `None` (404 от LP — событие пропало) → новый `cancel_bets_for_event(uow, event_id=..., cancelled_via="reconciler")` → bet'ы переходят в `BetStatus.CANCELLED`.
   - `state == NEW` → skip (даже если deadline в прошлом — это не наша проблема, LP ещё не перевёл; следующий tick попробует снова).

`/health` расширяется: 503 если `task.done() is True` (R8 формулировка из ROADMAP). На shutdown: `task.cancel()` → `with suppress(asyncio.CancelledError): await task` — **первым** в finally lifespan'а (ДО `broker.close()` / `http_client.aclose()` / `engine.dispose()`).

**В скоупе:**
- **Sync-task** в первом плане (паттерн P2 02-01 / P3 03-01 / P4 04-01 / P5 05-10): обновить `REQUIREMENTS.md` BM-05 (расширить статусы до `PENDING | WON | LOST | CANCELLED`) и `ROADMAP.md` Phase 6 (Goal + Success Criteria) — зафиксировать CANCELLED как явный recovery-status.
- Alembic migration `0003` — `ALTER TYPE betstatus ADD VALUE IF NOT EXISTS 'cancelled'` (idempotent, см. P3 D-09 паттерн).
- `BetRepository.get_pending_event_ids() -> list[UUID]` — новый read-метод (паттерн P3 + P5 D-12, без commit/flush).
- `bet_maker/interactors/cancel_bets_for_event.py` — новый interactor, паттерн `settle_bets_for_event`: UoW + `get_pending_locked(event_id)` + `UPDATE status='cancelled', settled_at=func.now(), settled_via='reconciler'`. Возвращает `CancelResult` (паттерн `SettleResult`, без `terminal_state`).
- `bet_maker/entrypoints/reconciliation.py` — новый модуль с фабрикой `start_reconciliation_task(app, settings) -> asyncio.Task` и loop-функцией.
- `bet_maker/facades/http_event_lookup.py` — **НЕ меняется**, переиспользуется как есть. В lifespan создаётся второй экземпляр с reconciler-params.
- `BetMakerSettings` расширяется тремя полями (D-Settings).
- `bet_maker/entrypoints/lifespan.py` — расширение порядка startup/shutdown.
- `bet_maker/entrypoints/api/health.py` — расширение D-Health.
- `bet_maker/facades/deps.py` — `ReconcilerEventLookupDep` Annotated alias.
- Unit-тесты `cancel_bets_for_event` (паттерн `test_settle_bets_for_event`).
- Unit-тесты reconciler loop через mock `EventLookup` + in-memory `BetRepository` или через TestRabbitBroker-equivalent (см. D-Testing).
- Integration-тест concurrent reconciler + consumer на одном event_id через testcontainers PG (SC#4).
- E2E тест "drop publish" через testcontainers PG + RMQ (SC#5, QA-08).

**Не в скоупе:**
- Любое расширение line-provider (новый endpoint `GET /events?ids=...` — был deferred в P4, остаётся deferred).
- Reconciler НЕ публикует AMQP-сообщения. Settle/cancel — единственное действие; consumer Phase 5 продолжает быть основным путём.
- Idempotency-таблица (`processed_messages` / `reconciled_events`) — Phase 5 D-15 политика: status-filter + `FOR UPDATE SKIP LOCKED` — единственная точка истины.
- Метрики / Prometheus — info-логи + Management UI достаточны для приёмки (P5 deferred).
- Watch-dog auto-restart task — внешний supervisor (docker compose / uvicorn restart). Reconciler НЕ перезапускает себя; /health 503 → docker compose mark unhealthy → перезапуск контейнера.
- Jitter на interval — для single-instance bet-maker'а в docker-compose это не нужно.
- Grace period для свежих PENDING bet'ов — settle idempotent, лишний шум приемлем (default 0).
- `Idempotency-Key` на cancel-операции — out of scope (как и для POST /bet).

</domain>

<decisions>
## Implementation Decisions

### Polling Strategy & Branching

- **D-01:** `BetRepository.get_pending_event_ids() -> list[UUID]` — новый read-метод. SQL: `SELECT DISTINCT event_id FROM bets WHERE status='PENDING'`. Реализация через SQLAlchemy `select(Bet.event_id).where(Bet.status == BetStatus.PENDING).distinct()`. Метод без commit/flush, Anti-Pattern 1 сохраняется (P3 D-18).
- **D-02:** Per `event_id` reconciler делает один `HttpEventLookup.get_event(event_id)` через `app.state.reconciler_event_lookup` (5 attempts, P4 D-04). Брендч-таблица:
  - `EventSnapshot.state in {FINISHED_WIN, FINISHED_LOSE}` → `settle_bets_for_event(uow, event_id=event_id, terminal_state=event.state, settled_via="reconciler")`. Interactor возвращает `SettleResult(settled_count=N|0)`; 0 = другой консьюмер успел первым (`FOR UPDATE SKIP LOCKED` + status-filter — P5 D-12).
  - `None` (LP вернул 404) → `cancel_bets_for_event(uow, event_id=event_id, cancelled_via="reconciler")`. Семантика 404: событие удалено / LP пересоздан / in-memory store очищен — settle невозможен, ставка не должна висеть. Cancel — единственный recovery-выход. Idempotent через тот же `get_pending_locked(event_id)`.
  - `state == NEW` (включая случай с прошедшим `deadline`) → skip, log `reconciler.event.still_new`, идём дальше. LP ещё не перевёл event — это его контракт; следующий tick попробует снова. **Не упреждаем LP.**
- **D-03:** Расширение `BetStatus` enum — добавляется `CANCELLED = "cancelled"`. Изменения:
  - `bet_maker/schemas/bets.py` — `BetStatus.CANCELLED`.
  - Alembic migration `0003_bet_status_cancelled.py` — `ALTER TYPE betstatus ADD VALUE IF NOT EXISTS 'cancelled'`. Idempotent (P3 D-09 паттерн); rerun safe; `op.execute("ALTER TYPE ...").execution_options(autocommit=True)` если потребуется (researcher уточнит точный pattern для async Alembic).
  - Существующие колонки `Bet.status`, `Bet.settled_at`, `Bet.settled_via` (P5 D-13) — НЕ меняются.
  - `Bet` ORM — без новых колонок (deadline НЕ храним; reconciler полагается на LP как single source of truth state'а события).
- **D-04:** Новый interactor `cancel_bets_for_event(uow, *, event_id: UUID, cancelled_via: Literal["reconciler"]) -> CancelResult`:
  ```python
  async with uow:
      bets = await uow.bets.get_pending_locked(event_id)
      if not bets:
          log.info("cancel.noop", event_id=str(event_id), reason="no PENDING bets")
          return CancelResult(event_id=event_id, cancelled_count=0, cancelled_bet_ids=[], cancelled_via=cancelled_via, cancelled_at=...)
      bet_ids = [b.id for b in bets]
      await uow.session.execute(
          update(Bet).where(Bet.id.in_(bet_ids)).values(
              status=BetStatus.CANCELLED,
              settled_at=func.now(),
              settled_via=cancelled_via,
          )
      )
      log.info("cancel.committed", event_id=..., cancelled_count=len(bet_ids), reason="line_provider_404")
      return CancelResult(...)
  ```
  `CancelResult` — Pydantic DTO в `bet_maker/schemas/settle.py` (рядом с `SettleResult`): `(event_id, cancelled_count, cancelled_bet_ids: list[UUID], cancelled_via, cancelled_at)`. **Переиспользует те же колонки `settled_at` / `settled_via`** — общая observability семантика "когда и кто закрыл ставку".
- **D-05:** Reconciler **НЕ обрабатывает** `LineProviderUnavailable` особо: per-event try/except (D-Errors) ловит её как любой Exception → log + continue. Следующий tick попробует снова. Это соответствует контракту HttpEventLookup (P4 D-07) — exception не зависит от типа вызывающего.

### Reconciler HTTP Client

- **D-06:** В lifespan создаётся **отдельный** `HttpEventLookup` для reconciler'а с reconciler-params, пинится в `app.state.reconciler_event_lookup`. Оба экземпляра (`app.state.event_lookup` для роутов и `app.state.reconciler_event_lookup` для task'а) **разделяют** singleton `httpx.AsyncClient` (`app.state.line_provider_http_client`) — никакого второго pool'а.
  ```python
  app.state.reconciler_event_lookup = HttpEventLookup(
      http_client=http_client,
      attempts=settings.line_provider_reconciler_attempts,
      max_backoff=settings.line_provider_reconciler_backoff_max_s,
  )
  ```
- **D-07:** `bet_maker/facades/deps.py` расширяется:
  - `get_reconciler_event_lookup(request: Request) -> HttpEventLookup` — provider читает `app.state.reconciler_event_lookup`.
  - `ReconcilerEventLookupDep = Annotated[HttpEventLookup, Depends(get_reconciler_event_lookup)]`.
  Стиль строго симметричен `get_event_lookup` / `EventLookupDep` (P3 D-13). Reconciler task получает экземпляр напрямую из `app.state` (не через FastAPI Depends — task не в request-scope).
- **D-08:** Reconciler **НЕ** использует EventLookup Protocol abstraction для типа аргумента. Передаём конкретный `HttpEventLookup` (или мокаемый duck-type в тестах) — Protocol симметрия (P3 D-11) важна для interactor'ов в request-scope, а не для background task'ов. Это упрощает тесты (mock-class без Protocol-имплементации).

### Settings (P1 schema extension)

- **D-09:** `BetMakerSettings` расширяется тремя новыми полями (env_prefix `BET_MAKER_`):
  - `reconciliation_interval_s: float = Field(default=30.0, gt=0)` — период tick'а. ROADMAP BM-12 default = 30s. В e2e тестах будет переопределяться на ~1s.
  - `line_provider_reconciler_attempts: int = Field(default=5, ge=1, le=10)` — P4 D-04.
  - `line_provider_reconciler_backoff_max_s: float = Field(default=10.0, gt=0)` — P4 D-04.
  Существующие поля (`line_provider_base_url`, `line_provider_http_attempts`, `line_provider_http_backoff_max_s`) НЕ трогаем.

### Error Isolation Inside Tick

- **D-10:** Loop структура (двухуровневый try/except, R8 + liveness):
  ```python
  async def reconciliation_loop(
      app: FastAPI,
      *,
      interval_s: float,
  ) -> None:
      log = structlog.get_logger().bind(task="reconciliation")
      while True:
          try:
              await asyncio.sleep(interval_s)
              await _run_tick(app)
          except asyncio.CancelledError:
              log.info("reconciler.cancelled")
              raise  # propagate up to await task in shutdown
          except Exception:
              log.exception("reconciler.tick.failed")
              # loop continues — R8 invariant
  ```
- **D-11:** Внутри `_run_tick` структура:
  ```python
  async def _run_tick(app: FastAPI) -> None:
      sessionmaker = app.state.sessionmaker
      reconciler_lookup = app.state.reconciler_event_lookup
      async with AsyncUnitOfWork(sessionmaker) as uow:
          event_ids = await uow.bets.get_pending_event_ids()
      if not event_ids:
          log.debug("reconciler.tick.noop")
          return
      for event_id in event_ids:
          try:
              await _reconcile_event(sessionmaker, reconciler_lookup, event_id)
          except Exception:
              log.exception("reconciler.event.failed", event_id=str(event_id))
              continue
  ```
  Получение списка `event_ids` — отдельный UoW (read-only); settle/cancel каждого — свой UoW в `_reconcile_event`. Это позволяет:
  - Один битый event_id не отравляет транзакцию остальных.
  - Каждый UoW короче — меньше row-lock contention с consumer'ом.
- **D-12:** PG `OperationalError` на `get_pending_event_ids` пробрасывается из inner UoW в `_run_tick`, дальше — в outer try/except цикла → log + следующий tick. Lifespan-startup `wait_for_postgres` уже исключает badly-configured-DSN сценарий (P3 D-22).

### /health & Lifecycle

- **D-13:** `/health` extends текущий P5 D-20 чекер четвёртой проверкой:
  ```python
  reconciler_ok = not reconciliation_task.done()
  ```
  Возврат тела при degraded:
  ```json
  {
    "status": "degraded",
    "checks": {
      "postgres": "ok" | "down",
      "rabbitmq": "ok" | "down",
      "rabbitmq_consumer": "ok" | "no subscribers",
      "reconciler": "ok" | "dead"
    }
  }
  ```
  Без вызова `task.exception()` — оно бросает если `done()` ещё False, и lifecycle гарантирует, что после shutdown task собран. Простая `not task.done()` достаточна — R8 формулировка из ROADMAP.
- **D-14:** Reconciliation task пинится в `app.state.reconciliation_task: asyncio.Task[None]`. Provider в `facades/deps.py`:
  - `get_reconciliation_task(request) -> asyncio.Task[None]`
  - `ReconciliationTaskDep = Annotated[asyncio.Task[None], Depends(get_reconciliation_task)]`
  Health route получает её через Depends (паттерн P5 D-20).
- **D-15:** Startup-порядок lifespan (расширяет P5 D-21):
  ```
  1. configure_structlog
  2. create_engine_and_sessionmaker
  3. wait_for_postgres
  4. httpx.AsyncClient singleton
  5. router.broker.connect()
  6. declare DLX + DLQ + bindings
  7. set_sessionmaker (messaging consumer)
  8. app.state pins:
     - settings, engine, sessionmaker
     - line_provider_http_client
     - event_lookup = HttpEventLookup(attempts=3)        ← P4
     - reconciler_event_lookup = HttpEventLookup(attempts=5)  ← NEW P6
  9. reconciliation_task = asyncio.create_task(
         reconciliation_loop(app, interval_s=settings.reconciliation_interval_s),
         name="reconciliation",
     )
     app.state.reconciliation_task = reconciliation_task
  10. yield
  ```
  `create_task` помещается **после** declare topology, потому что reconciler в принципе не зависит от RMQ — но семантически tick может проходить параллельно с consumer'ом, и порядок declare → create_task → yield исключает race "consumer ещё не зарегистрирован, /health 503".
- **D-16:** Shutdown-порядок lifespan (reverse, nested try/finally — P4 D-20 паттерн):
  ```python
  try:
      yield
  finally:
      log.info("bet_maker.shutdown")
      reconciliation_task.cancel()
      try:
          with suppress(asyncio.CancelledError):
              await reconciliation_task
      finally:
          try:
              await rabbit_router.broker.close()
          finally:
              try:
                  await http_client.aclose()
              finally:
                  await engine.dispose()
      log.info("bet_maker.shutdown.complete")
  ```
  Reconciler — **первый** в finally, потому что:
  - Он внутри tick'а держит UoW (PG-сессию из sessionmaker) и httpx requests (через http_client). Закрытие http_client / engine ДО завершения task'а вызовет `OperationalError` / `RuntimeError` в in-flight операции.
  - `cancel + await` гарантирует чистый выход: tick перехватывает `CancelledError`, propagate через outer except, lifespan видит её через `suppress`.
- **D-17:** First-tick timing: `await asyncio.sleep(interval_s)` **перед** первым tick. Holds:
  - Без шума на cold-start: lifespan только закончил wiring, consumer ещё прогревается, reconciler не делает спекулятивных HTTP-запросов на пустой БД.
  - Если interval=30s, первый tick через 30s после startup. Для test-task scope это адекватно.
  - В e2e тестах `RECONCILIATION_INTERVAL_S=1.0` (через ENV override на testcontainer-приложение) — первый tick через ~1s.
- **D-18:** Task name `"reconciliation"` фиксирован (ROADMAP R8). Используется для grep'а в логах и в debug отображении asyncio.

### Testing

- **D-19:** **Unit-тесты `cancel_bets_for_event`** (`tests/bet_maker/test_cancel_bets_for_event.py`) — testcontainers PG (паттерн `test_settle_bets_for_event` Phase 5):
  - happy path: 2 PENDING bets → cancel → status=CANCELLED, settled_at filled, settled_via='reconciler', cancelled_count=2.
  - noop: 0 PENDING bets → noop, cancelled_count=0.
  - idempotency: вызов на event с уже CANCELLED bets → noop (status filter в get_pending_locked).
  - concurrency: два gather'а на тот же event_id → один настоящий cancel, другой noop (`FOR UPDATE SKIP LOCKED`).
- **D-20:** **Unit-тесты reconciler loop** (`tests/bet_maker/test_reconciliation.py`):
  - Mock `EventLookup` (duck-typed): возвращает разные state'ы (FINISHED_WIN / FINISHED_LOSE / NEW) или `None` для разных event_id.
  - Реальный testcontainer PG с seed данными.
  - Сценарии: `_run_tick` с 3 event_id (1 settled, 1 cancelled через None, 1 NEW skip) — проверить статусы в БД после tick'а.
  - Per-event exception isolation: mock-lookup бросает RuntimeError на одном event_id → остальные обрабатываются, log содержит `reconciler.event.failed`.
  - tick exception isolation: mock-lookup бросает на ВСЕХ → outer try/except логирует `reconciler.tick.failed`, loop не выходит (тест проверяет следующий tick).
  - sleep order: первый `asyncio.sleep` происходит ДО первого tick'а (через `freezegun` или счётчик вызовов `asyncio.sleep`).
- **D-21:** **Integration-тест /health reconciler-aware** (`tests/bet_maker/test_health.py` — добавление класса `TestHealthReconciler`):
  - Setup: build_app() с testcontainer dependencies; до этапа `yield` сразу же насильно `app.state.reconciliation_task.cancel(); await app.state.reconciliation_task; assert task.done()`. GET /health → 503 + `reconciler: "dead"`.
  - Healthy: task не cancel'нут → GET /health → 200 + `reconciler: "ok"`.
- **D-22:** **Concurrent integration-тест SC#4** (`tests/bet_maker/test_reconciliation_concurrent.py`) — testcontainers PG:
  - Setup: создать 1 event_id, 3 PENDING bet'а.
  - `asyncio.gather(settle_bets_for_event(uow_a, ...), cancel_bets_for_event(uow_b, ...))` — на параллельные UoW (разные sessionmaker'а сессии).
  - Альтернативно: `gather(settle_via_consumer, reconciler._reconcile_event)` — реалистичнее.
  - Assert: после gather все 3 bet'а в одном статусе (WON или CANCELLED — не оба); `settled_count + cancelled_count == 3`; ровно один из двух interactor'ов "выиграл" (`FOR UPDATE SKIP LOCKED`).
- **D-23:** **E2E "drop publish" QA-08 / SC#5** (`tests/bet_maker/test_reconciliation_e2e.py`) — testcontainers PG + RMQ (паттерн `test_e2e_rabbitmq.py` Phase 5):
  - **Сценарий 1 (consumer happy path):** create event (LP) → POST /bet → set_event_state(FINISHED_WIN) — publish идёт нормально → consumer settle'ит → GET /bets → status=WON.
  - **Сценарий 2 (reconciler recovery):** create event → POST /bet → `monkeypatch.setattr(RabbitEventBus, "publish", AsyncMock())` (стереть publish line-provider'а) → set_event_state(FINISHED_WIN) — message пропал в никуда → ждём `RECONCILIATION_INTERVAL_S + ε` (тест запускает с `RECONCILIATION_INTERVAL_S=1.0` через ENV override testcontainer-приложения; ε=0.5s buffer) → GET /bets → status=WON, settled_via='reconciler'.
  - **Сценарий 3 (cancel при 404):** create event → POST /bet → удалить event из in-memory store LP напрямую (или рестартовать LP testcontainer — простой подход: monkeypatch на `_TerminalStateLookup` в LP) → reconciler tick видит 404 → GET /bets → status=CANCELLED.
- **D-24:** `RECONCILIATION_INTERVAL_S` в e2e тестах = 1.0s через `BET_MAKER_RECONCILIATION_INTERVAL_S=1.0` env var, передаваемый в testcontainer-приложение через fixture (паттерн P5 e2e fixture). Тест ждёт `interval + 0.5s` после "drop publish" trigger.

### Sync-task (Plan 06-01)

- **D-25:** Первый план Phase 6 — sync-task (паттерн P2 02-01 / P3 03-01 / P4 04-01 / P5 05-10):
  - **`REQUIREMENTS.md` BM-05** — расширить статусы ставки: `PENDING | WON | LOST | CANCELLED`. Добавить пояснение: «CANCELLED — recovery-статус: bet помечается reconciler'ом при 404 от line-provider (событие удалено)».
  - **`REQUIREMENTS.md` BM-12** — добавить пункт CANCELLED branch описания (помимо WON/LOST).
  - **`ROADMAP.md` Phase 6 Goal** — добавить «либо `CANCELLED` если LP вернул 404 на терминальный опрос».
  - **`ROADMAP.md` Phase 6 SC** — расширить SC#1 и SC#5 описанием cancel-ветки.
  - **README P7 (DOC-02)** — упомянуть CANCELLED как «инженерная трактовка для recovery; ТЗ не требует»; ссылка на memory `feedback_verify_against_tz`.

### Claude's Discretion

- Точный путь Alembic-миграции для `ALTER TYPE betstatus ADD VALUE` в async-template — researcher уточнит (Context7 `/alembic` или `/sqlalchemy`). Обычно требует `autocommit_block` или `migration_context.run_migrations()` модификацию. Idempotent через `ADD VALUE IF NOT EXISTS` (PG 9.6+, у нас 16).
- Размещение `reconciliation_loop`: `bet_maker/entrypoints/reconciliation.py` (current pick) vs `bet_maker/messaging/reconciliation.py`. Я склоняюсь к `entrypoints/` потому что это lifecycle-композиция (как `messaging.py` consumer), а не routing module.
- Точная реализация `monkeypatch.setattr(RabbitEventBus, "publish", AsyncMock())` для D-23 Сценарий 2 — researcher проверит, можно ли это сделать через fixture override без перезапуска line-provider testcontainer. Альтернатива — autouse'ный `_drop_publish_mode` маркер pytest, который активируется per-test.
- Логирование структура `reconciler.event.{settled,cancelled,still_new,failed}` + `reconciler.tick.{start,end,noop,failed}` — точные имена и поля planner определит, главное — single namespace `reconciler.` для grep.
- `_reconcile_event` подпись (отдельная функция vs метод класса) — planner выберет читаемость. `Reconciler` класс с `__init__(sessionmaker, event_lookup)` и методом `run_tick` — возможно чище для тестов; loop-функция тогда становится тонкой обёрткой над `Reconciler.run()`.
- Стиль cancel-result: переиспользовать `SettleResult` с `terminal_state=None` vs отдельный `CancelResult` DTO. Я указал отдельный DTO (D-04) — две сущности проще отличать в логах и тестах. Planner может оспорить.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth — ТЗ
- `./Тестовое задание Middle Python developer.pdf` — **первоисточник**. Релевантно для P6:
  - стр.1: «надёжности (к примеру, невозможности зависания ставки)» — Core Value, формирует существование reconciler'а как defence-in-depth.
  - стр.2: «Bet может иметь один из трёх статусов: ещё не сыграла / выиграна / проиграна» — `CANCELLED` отсутствует в ТЗ. D-25 sync-task документирует расширение как наша инженерная трактовка.
  - Memory `feedback_verify_against_tz` — sync-task в Plan 06-01 обновляет REQUIREMENTS.md и ROADMAP.md под наше расширение.

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` BM-12 — reconciliation job требование. BM-05 — статусы ставки (будет расширено D-25).
- `.planning/REQUIREMENTS.md` QA-08 — e2e сценарий create→bet→finish→assert reconciler.
- `.planning/ROADMAP.md` §«Phase 6: Reconciliation job» — Goal, 5 SC, 4 pitfalls (R8/R3/R9 + integration gotcha). После D-25 sync — Goal + SC#1 + SC#5 расширены `CANCELLED` веткой.

### Прошлые фазы — locked decisions
- `.planning/phases/01-skeleton-infrastructure/01-CONTEXT.md` D-15 (`BetMakerSettings`), D-17/D-18 (structlog `bind_contextvars` / middleware), D-19 (`wait_for_postgres`).
- `.planning/phases/03-bet-maker-domain-db/03-CONTEXT.md` D-09 (Bet schema), D-11 (`EventLookup` Protocol), D-12 (cross-service schema duplication policy), D-13 (`app.state` DI + `Annotated[..., Depends(...)]` paттерн), D-18 (`AsyncUnitOfWork`), D-22 (`wait_for_postgres` в lifespan).
- `.planning/phases/04-bet-maker-http-integration-with-line-provider/04-CONTEXT.md` D-02 (singleton `httpx.AsyncClient` в lifespan), D-04 (**reconciler retry policy 5 attempts / max_backoff 10s** — реализуется здесь), D-07 (`LineProviderUnavailable`), D-11 (`make_retry_decorator` factory), D-13 (`EventRead` schema), D-20 (reverse-order shutdown с nested try/finally).
- `.planning/phases/05-rabbitmq-integration/05-CONTEXT.md` D-12/D-15 (idempotency: `get_pending_locked` + status filter), D-13 (Bet `settled_at`/`settled_via` колонки — reconciler пишет туда же), D-17 (`settle_bets_for_event` сигнатура — переиспользуется здесь), D-19 (single bet-maker process), D-20 (`/health` с PG + RMQ + subscribers — расширяется здесь), D-21 (strict lifespan startup order — расширяется здесь).

### Project instructions
- `./CLAUDE.md` §«Recommended Stack» — `pydantic-settings 2.14.1` для D-09 трёх новых полей. `tenacity 9.1.4` — переиспользуется через `make_retry_decorator`.
- `./CLAUDE.md` §«Constraints» — async всюду, Python 3.10.x.

### Existing code — call sites & extension points
- `src/bet_maker/entrypoints/lifespan.py` — расширяется по D-15/D-16 (новый pin `reconciler_event_lookup` + create_task + cancel/await в shutdown).
- `src/bet_maker/entrypoints/api/health.py` — расширяется по D-13 (4-я проверка `not task.done()`).
- `src/bet_maker/entrypoints/reconciliation.py` (**новый**) — loop + per-event обработчик (D-10/D-11).
- `src/bet_maker/interactors/cancel_bets_for_event.py` (**новый**) — D-04 паттерн settle.
- `src/bet_maker/interactors/settle_bets_for_event.py` — **НЕ меняется**, переиспользуется (P5 D-17). `Literal["consumer", "reconciler"]` уже принимает 'reconciler'.
- `src/bet_maker/repositories/bets.py` — добавляется `get_pending_event_ids() -> list[UUID]` (D-01).
- `src/bet_maker/schemas/bets.py` — `BetStatus.CANCELLED` (D-03).
- `src/bet_maker/schemas/settle.py` — `CancelResult` рядом с `SettleResult` (D-04).
- `src/bet_maker/facades/deps.py` — `get_reconciler_event_lookup` + `ReconcilerEventLookupDep` + `get_reconciliation_task` + `ReconciliationTaskDep` (D-07/D-14).
- `src/bet_maker/facades/http_event_lookup.py` — **НЕ меняется**.
- `src/bet_maker/settings/config.py` — три новых поля (D-09).
- Alembic `migrations/versions/0003_bet_status_cancelled.py` (**новый**) — D-03.

### External docs (researcher / planner)
- `tenacity` 9.1.4 — для reconciler-retry политики (через `make_retry_decorator`). Через Context7 `/jd/tenacity`.
- `asyncio.Task` cancellation patterns — стандартная библиотека, Python 3.10 docs. `task.cancel()` + `await` + `CancelledError` propagation.
- Alembic + PG `ALTER TYPE ... ADD VALUE` async pattern — Context7 `/sqlalchemy/alembic` (researcher уточнит autocommit/transactional-DDL детали).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`settle_bets_for_event` interactor** (`src/bet_maker/interactors/settle_bets_for_event.py`) — переиспользуется без изменений. Сигнатура уже принимает `settled_via=Literal["consumer", "reconciler"]` (P5 D-17). Идемпотентность через `get_pending_locked` (P5 D-12).
- **`BetRepository.get_pending_locked`** (`src/bet_maker/repositories/bets.py`) — переиспользуется в `cancel_bets_for_event`. Тот же `FOR UPDATE SKIP LOCKED` + status filter — concurrent с consumer'ом гарантированно безопасно (P5 D-12).
- **`HttpEventLookup`** (`src/bet_maker/facades/http_event_lookup.py`) — переиспользуется как class. Constructor уже параметризован `(http_client, attempts, max_backoff)` — никаких правок. Возвращает `EventSnapshot | None` (404 → None) — P4 D-09.
- **`EventSnapshot`** (`src/bet_maker/facades/event_lookup.py`) — frozen Pydantic с `event_id, deadline, state` (P3 D-11 + P4 D-13). Поле `state` — это `EventState` enum (NEW / FINISHED_WIN / FINISHED_LOSE). Reconciler читает напрямую без доп. парсинга.
- **`AsyncUnitOfWork`** (`src/bet_maker/facades/uow.py`) — переиспользуется. Reconciler создаёт UoW на каждый tick (для `get_pending_event_ids`) и на каждый event_id (для settle/cancel) — short-lived транзакции, минимальный contention.
- **`make_retry_decorator`** (`src/bet_maker/facades/line_provider_client.py`) — переиспользуется. Reconciler вызывает с (attempts=5, max_backoff=10.0) через конструктор HttpEventLookup.
- **`SettleResult`** (`src/bet_maker/schemas/settle.py`) — `CancelResult` (D-04) пишется рядом по тому же паттерну.
- **structlog `bind_contextvars` / `clear_contextvars`** — reconciler loop делает `log.bind(task="reconciliation")` (D-10).
- **testcontainers PG fixture** (`tests/bet_maker/conftest.py`, паттерн P3 D-23 + P5) — переиспользуется в D-19/D-22.
- **testcontainers RMQ fixture** (`tests/bet_maker/conftest.py`, P5 Plan 05-09) — переиспользуется в D-23 e2e.
- **lifespan testing fixtures** (`tests/bet_maker/conftest.py`, P4 Plan 04-07 `line_provider_app`) — pattern для D-23 e2e (two FastAPI apps в одном процессе).

### Established Patterns
- **DI через `Annotated` + `Depends` + `app.state`** (P3 D-13) — для `ReconcilerEventLookupDep` и `ReconciliationTaskDep`.
- **Lifespan reverse-order shutdown + nested try/finally** (P4 D-20) — расширяется в D-16 (reconciler task — первая отмена).
- **Pydantic `extra="forbid"` + `frozen=True`** — `CancelResult` пишется с теми же опциями.
- **`Literal["..."]` поля** (P5 D-17 `settled_via`) — `cancelled_via: Literal["reconciler"]` (одно значение пока, расширяемо).
- **Idempotent Alembic migrations** (P3 D-09 `CREATE TYPE ... IF NOT EXISTS`) — `ALTER TYPE ... ADD VALUE IF NOT EXISTS 'cancelled'`.
- **Sync-task в первом плане фазы** (P2 02-01 / P3 03-01 / P4 04-01 / P5 05-10) — D-25.
- **Service-boundary: НЕ импортируем из соседнего сервиса** (P3 D-12) — `BetStatus.CANCELLED` существует только в bet-maker; line-provider о нём не знает.

### Integration Points
- `entrypoints/lifespan.py` — единая точка композиции: новый pin `reconciler_event_lookup`, `create_task(reconciliation_loop, name="reconciliation")`, `cancel + await` в shutdown finally.
- `entrypoints/reconciliation.py` (**новый**) → `repositories.bets.get_pending_event_ids` + `facades.http_event_lookup.HttpEventLookup.get_event` + `interactors.settle_bets_for_event` + `interactors.cancel_bets_for_event`.
- `entrypoints/api/health.py` — добавляется 4-я проверка task health через `ReconciliationTaskDep`.
- `facades/deps.py` — два новых provider'а + два новых Dep alias'а.
- `models/bet.py` — **НЕ меняется** (нет новых колонок; `BetStatus.CANCELLED` — это enum value, не схема).
- `schemas/bets.py` — добавление `CANCELLED` в `BetStatus`.
- `schemas/settle.py` — добавление `CancelResult`.
- Alembic `versions/0003_bet_status_cancelled.py` — single ALTER TYPE миграция.
- `pyproject.toml` — **НЕ меняется** (нет новых deps; всё уже pinned).
- `docker-compose.yml` — **НЕ меняется** (RECONCILIATION_INTERVAL_S через env с default; .env.example можно дополнить).

</code_context>

<specifics>
## Specific Ideas

- **«маркировать как зависшие и канселить ставки»** — выбор пользователя в обсуждении 1/4. После уточнения trigger — **только 404 от LP** (без deadline-based fallback). Это minimum-viable семантика CANCELLED, не уптрегающая LP. Future hardening: deadline+grace fallback — отложено.
- **Расширение BetStatus до 4-х значений** — `PENDING | WON | LOST | CANCELLED`. ТЗ-drift документирован в D-25 (sync-task) + README P7 (`feedback_verify_against_tz`).
- **Отдельный экземпляр HttpEventLookup для reconciler'а** — пользовательский выбор в обсуждении 2/4. Чисто, симметрично P3 D-11 / P4 D-14; разделяет singleton httpx pool с роутами.
- **`not task.done()` для /health** — буквальная формулировка R8 из ROADMAP, выбор пользователя в 4/4.
- **`sleep(interval)` перед первым tick** — пользовательский выбор; нет шума на cold-start.
- **`task.cancel() + await task` первым в shutdown** — пользовательский выбор. Гарантия: in-flight UoW / httpx не оборвутся.

</specifics>

<deferred>
## Deferred Ideas

- **Deadline-based cancel fallback** — пользователь явно отверг в обсуждении 1/4 (выбрал только 404-trigger). Future hardening: добавить `event_deadline` колонку в Bet ORM и `STALE_GRACE_S` setting; SQL-фильтр `WHERE PENDING AND event_deadline + GRACE < now()` без HTTP — для очень больших N. README P7 «next-step extension».
- **GET /events?ids=... batch endpoint в line-provider** — был deferred в P4 D-04 / P4 deferred-section. P6 остаётся per-event N×GET /event/{id} — для test-task scope (десятки event_id) этого достаточно.
- **Reconciler-публикация в RMQ** — out of scope. Reconciler — terminal sink; consumer Phase 5 — основной путь publish→consume. Если в будущем понадобится «реплей в RMQ для аудитория outside-of-bet-maker», добавим отдельный модуль.
- **Auto-restart reconciler task'а через /health watchdog** — отказались в обсуждении 4/4. Внешний supervisor (docker compose / uvicorn) перезапускает контейнер при 503.
- **Jitter для interval** — single-instance docker-compose, не нужен. Multi-instance HA — отдельная фаза «production hardening» (если будет).
- **Метрики `reconciler.ticks_total` / `reconciler.events_settled_total` / `reconciler.events_cancelled_total`** — info-логи + grep'абельный namespace `reconciler.*` достаточны для приёмки. Prometheus — production hardening.
- **CANCELLED-cause колонка** (`cancelled_reason: Literal["line_provider_404"]`) — для test-task пока хватит `settled_via='reconciler'` + log entry. Если расширим cancel-причины (deadline-based, manual admin cancel) — добавим колонку.
- **Reconciler в отдельном процессе** — out of scope. P5 D-19 закрепил «один процесс bet-maker».
- **Grace period для свежих PENDING bet'ов** — отвергли (settle idempotent, лишний шум приемлем).
- **Concurrent HTTP внутри tick через asyncio.gather + semaphore** — sequential loop хватает для test-task. Future hardening при N > 100 event_id/tick.
- **EventState parity test между line_provider/schemas/events.EventState и bet_maker/schemas/events.EventState** — P4 deferred → P7 e2e (где оба сервиса в одном тесте через testcontainers).

### Reviewed Todos (not folded)
None — no open todos in this project.

</deferred>

---

*Phase: 06-reconciliation-job*
*Context gathered: 2026-05-18*
