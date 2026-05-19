---
phase: 09-uow-repository-removal
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - src/bet_maker/api/messaging.py
  - src/bet_maker/facades/deps.py
  - src/bet_maker/interactors/cancel_bets_for_event.py
  - src/bet_maker/interactors/place_bet.py
  - src/bet_maker/interactors/settle_bets_for_event.py
  - src/bet_maker/jobs/reconciler.py
  - src/bet_maker/selectors/get_pending_event_ids.py
  - src/bet_maker/selectors/get_pending_locked.py
  - src/bet_maker/uow/__init__.py
  - src/bet_maker/uow/abstract.py
  - src/bet_maker/uow/postgres.py
  - tests/audit/test_static.py
  - tests/bet_maker/integration/test_reconciler_consumer_race.py
  - tests/bet_maker/interactors/test_cancel_bets_for_event.py
  - tests/bet_maker/selectors/__init__.py
  - tests/bet_maker/selectors/test_get_pending_event_ids.py
  - tests/bet_maker/selectors/test_get_pending_locked.py
  - tests/bet_maker/test_place_bet.py
  - tests/bet_maker/test_settle.py
  - tests/bet_maker/test_uow.py
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Фаза 9: отчёт о ревью кода

**Reviewed:** 2026-05-19T00:00:00Z
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Декомпозиция UoW (ABC + Postgres-реализация) и переход на селекторы выполнены чисто: контракт `AbstractUnitOfWork` минимален, `PostgresUnitOfWork` корректно
оборачивает `async_sessionmaker.begin()`, селекторы `get_pending_locked` и `get_pending_event_ids` принимают чистую `AsyncSession` без транзакционной логики
(D-05 соблюдено). Тесты на оба селектора и на cancel-интерактор покрывают идемпотентность и SKIP LOCKED-race.

Однако один из вызывающих модулей -- AMQP-consumer `src/bet_maker/api/messaging.py` -- содержит критическую несовместимость с тем контрактом, который декларирует
`PostgresUnitOfWork`. Хендлер открывает UoW сам (`async with PostgresUnitOfWork(...) as uow:`) и передаёт уже-открытый объект внутрь
`settle_bets_for_event`, который повторно делает `async with uow:`. `PostgresUnitOfWork.__aenter__` не идемпотентен: повторный вход затирает `_cm`/`_session`,
а внешний `__aexit__` падает на `assert self._cm is not None`. На happy-path это означает: UPDATE коммитится (внутренний exit), затем внешний exit бросает
`AssertionError`, `await msg.ack()` пропускается, и сообщение уходит в DLQ через ветку `except Exception -> reject(requeue=False)`. Видимое состояние BD корректно
(ставка переходит в WON/LOST), но Core-Value-инвариант "manual-ack ladder" из docstring модуля нарушен: каждая успешная settle попадает в DLQ как
"settle.transient_exhausted". E2E-тест этого не ловит, потому что проверяет только конечный статус ставки. См. CR-01 ниже.

Помимо CR-01, есть несколько менее серьёзных моментов: документация в `reconciler.py:84` называет UoW "read-only", но он открыт через `begin()` и потому
транзакционный (WR-01); `_run_tick` ловит просто `Exception` без сохранения `event_id` в logger context для ВСЕЙ цепочки (WR-03); `EventTerminalState(snapshot.state.value)`
в reconciler может бросить ValueError на неожиданном состоянии LP (WR-04); и module-level `_sessionmaker` global в messaging.py противоречит принципу
"всё через app.state" из CLAUDE.md (WR-02). Остальное -- мелкие info-замечания.

## Critical Issues

### CR-01: Двойной вход в `PostgresUnitOfWork` в AMQP-хендлере ломает manual-ack ladder

**File:** `src/bet_maker/api/messaging.py:168-175`

**Issue:**
Хендлер `on_event_finished` открывает UoW сам:

```python
async with PostgresUnitOfWork(sessionmaker) as uow:
    await _settle_with_retry(
        uow,
        event_id=message.event_id,
        terminal_state=message.new_state,
        settled_via="consumer",
    )
await msg.ack()
```

а затем передаёт уже-открытый `uow` в `settle_bets_for_event`, который снова делает `async with uow:` (`src/bet_maker/interactors/settle_bets_for_event.py:63`).
`PostgresUnitOfWork.__aenter__` (`src/bet_maker/uow/postgres.py:54-57`) ничего не знает про реентерабельность:

```python
async def __aenter__(self) -> Self:
    self._cm = self._sessionmaker.begin()
    self._session = await self._cm.__aenter__()
    return self
```

Второй вход выбрасывает внешний `_cm`/`_session` и создаёт новые. Внутренний `__aexit__` (после успешного UPDATE) затем сбрасывает `_cm = None`,
`_session = None`. На clean-exit из внешнего `async with` Python вызывает внешний `__aexit__`, который падает на `assert self._cm is not None`
(`src/bet_maker/uow/postgres.py:65`). AssertionError ловится `except Exception` в хендлере (`messaging.py:185-191`), логируется как
"settle.transient_exhausted" и завершается `await msg.reject(requeue=False)` -- сообщение уходит в DLQ.

Наблюдаемые последствия:
- DB-инвариант "ставка не остаётся в PENDING" сохраняется (внутренний UPDATE коммитится до AssertionError), поэтому пользователь видит корректный итоговый статус.
- Manual-ack контракт нарушен: КАЖДАЯ успешная settle уходит в DLQ через ветку reject. Каждая happy-path settle логируется как ошибка.
- DLQ перестаёт быть индикатором проблем: его контент перемешан с happy-path acks.
- Reconciler в реальности никогда не подхватывает "consumer fallback" сценарий, потому что DB уже обновлена ДО AssertionError. Но мониторинг по DLQ-длине теряет смысл.
- Инвариант R1/F1 ("ack только после успешного commit") формально соблюдён (commit состоялся), но семантически нарушен: вместо ack уходит reject.

Тестовое покрытие этого не ловит:
- `tests/bet_maker/test_messaging.py` использует mocked `_settle_with_retry` (`AsyncMock`), поэтому второй `async with uow:` не выполняется.
- `tests/bet_maker/test_e2e_rabbitmq.py::test_consumer_settles_bet_after_lp_transitions_to_finished_win` проверяет только конечный статус ставки через GET /bets, но не проверяет, попало ли сообщение в DLQ или было ack-нуто.

Контракт интеракторов (CONTEXT.md D-03) -- "Interactors write to `uow.session` directly... через `async with uow:`" -- т.е. интерактор ВСЕГДА входит сам.
Значит ошибка именно в messaging.py.

**Fix:**
Убрать внешний `async with`; передавать неоткрытый UoW в интерактор и ack-ать после возврата. См. `jobs/reconciler.py:113-129`, где это сделано правильно.

```python
sessionmaker = _require_sessionmaker()
uow = PostgresUnitOfWork(sessionmaker)
await _settle_with_retry(
    uow,
    event_id=message.event_id,
    terminal_state=message.new_state,
    settled_via="consumer",
)
await msg.ack()
```

Дополнительно: добавить отдельный E2E/unit-тест, который явно ассертит, что happy-path сообщение НЕ оказывается в DLQ (например, через `dlq.declare_queue(...)`+проверку
`message_count == 0` после успешной settle). Существующий test_poison-only-тест на DLQ оставить, но добавить контрольную проверку для зеркальной ветки.

Документацию в module docstring (`messaging.py:11`) -- "await msg.ack() is the LAST statement after async with uow: exits cleanly" -- переписать на новую форму:
"after `await _settle_with_retry(uow, ...)` returns (UoW context owned by interactor)".

---

## Warnings

### WR-01: Reconciler открывает транзакционный UoW для чисто read-only селектора

**File:** `src/bet_maker/jobs/reconciler.py:74-89`

**Issue:**
В `_run_tick` для получения work-list:

```python
async with PostgresUnitOfWork(sessionmaker) as uow:
    event_ids = await get_pending_event_ids(uow.session)
```

`PostgresUnitOfWork` использует `sessionmaker.begin()` (`src/bet_maker/uow/postgres.py:55`), который ОТКРЫВАЕТ транзакцию. Селектор `get_pending_event_ids` -- это
один SELECT DISTINCT без FOR UPDATE; держать ради него транзакцию (пусть и read-only) лишнее: пустой `COMMIT` уходит в PG на каждом тике каждые
`RECONCILIATION_INTERVAL_S` секунд. Docstring в `reconciler.py:78-79` называет это "Read-only UoW", но Postgres-UoW не имеет read-only-режима.

Дополнительно: это противоречит спирту D-05 ("селекторы не знают про UoW, не commit-ят/flush-ят"). Cleaner pattern -- использовать `sessionmaker()` напрямую,
как в `facades/deps.py::get_session` (`facades/deps.py:34-42`), без `.begin()`.

**Fix:**
Заменить UoW на голую сессию:

```python
async with sessionmaker() as session:
    event_ids = await get_pending_event_ids(session)
```

или вынести в helper аналогично `get_session` в DI.

### WR-02: Module-level mutable global `_sessionmaker` в messaging.py противоречит "everything via app.state"

**File:** `src/bet_maker/api/messaging.py:90-107`

**Issue:**
`_sessionmaker: async_sessionmaker[AsyncSession] | None = None` -- module-level state, мутируемый через `set_sessionmaker()` из lifespan. CLAUDE.md в разделе
"Stack Patterns by Variant" явно требует: "NO module-level httpx singleton; every long-lived object goes through app.state + cast() provider". Тот же
аргумент применим к sessionmaker:

- Состояние теряется между перезапусками тестов в той же сессии pytest, если кто-то забывает вызвать `set_sessionmaker` снова.
- Невозможно подменить sessionmaker на per-test-scope без `patch` (видно в `tests/bet_maker/test_messaging.py:71-74` -- autouse-fixture, чтобы не разъехалось).
- FastStream `RabbitRouter` инициализирован на уровне модуля (`router = RabbitRouter(...)`) -- альтернативой было бы хранить sessionmaker на `router.state`
  или дотягиваться до него через `app.state` (по образцу `jobs/reconciler.py`, который читает `app.state.sessionmaker`).

Не критично (single-event-loop, single-process), но мешает тестируемости и расходится с архитектурными принципами проекта.

**Fix:**
Прокинуть sessionmaker через context: получить его из FastStream `router.context` либо переписать handler-фактори так, чтобы он принимал sessionmaker как замыкание.
Минимальный фикс -- продолжать использовать global, но задокументировать как осознанный компромисс и продублировать в CLAUDE.md (Stack Patterns) исключение для
FastStream-handler scope. Желательнее -- передавать sessionmaker через `router.lifespan_context` или DI.

### WR-03: Reconciler теряет per-event `event_id` контекст в логах ошибок

**File:** `src/bet_maker/jobs/reconciler.py:91-96`

**Issue:**
В `_run_tick`:

```python
for event_id in event_ids:
    try:
        await _reconcile_event(sessionmaker, lookup, event_id)
    except Exception:
        _log.exception("reconciler.event.failed", event_id=str(event_id))
        continue
```

`structlog.contextvars` не привязывается к `event_id` -- передаётся только как kwarg в этом конкретном log-вызове. Если внутри `_reconcile_event` падает
вложенный лог (например, в `settle_bets_for_event`), у него `event_id` уже есть как kwarg, но другие вспомогательные логи в HTTP-клиенте или DB-слое не будут
содержать `event_id`. На фоне того, что consumer-хендлер (`messaging.py:157-161`) явно делает `bind_contextvars(event_id=...)`, reconciler выбивается из паттерна.

Не баг, но снижает диагностируемость в продакшене: при множестве параллельных tick-логов сложнее проследить causal chain отдельного event_id.

**Fix:**
Завернуть тело цикла в `with structlog.contextvars.bound_contextvars(event_id=str(event_id)):` (или старый `bind_contextvars` + `clear_contextvars`),
по образцу `messaging.py:154-194`.

### WR-04: `EventTerminalState(snapshot.state.value)` бросает ValueError на не-терминальном/неизвестном состоянии

**File:** `src/bet_maker/jobs/reconciler.py:123`

**Issue:**

```python
if snapshot.state == EventState.NEW:
    _log.debug("reconciler.event.still_new", event_id=str(event_id))
    return

uow = PostgresUnitOfWork(sessionmaker)
terminal_state = EventTerminalState(snapshot.state.value)
```

После early-return на NEW предполагается, что `snapshot.state` -- одно из `FINISHED_WIN`/`FINISHED_LOSE`. Но `EventState` enum мог быть расширен (например,
будущий статус `CANCELLED_BY_LP` или `POSTPONED`), и тогда `EventTerminalState(snapshot.state.value)` бросит `ValueError`. Это поймает `except Exception` в `_run_tick`
(`reconciler.py:94-96`), и event_id просто залогируется как "reconciler.event.failed" -- без классификации.

Не страшно (PENDING-инвариант защищён reconciler retry-loop), но:
- В логе будет шумный ValueError каждые 30 секунд для каждого "странного" event_id, пока LP не отдаст терминальное состояние.
- Difficult to distinguish from реально transient errors (DB down, LP timeout).

**Fix:**
Явный whitelist:

```python
match snapshot.state:
    case EventState.FINISHED_WIN:
        terminal_state = EventTerminalState.FINISHED_WIN
    case EventState.FINISHED_LOSE:
        terminal_state = EventTerminalState.FINISHED_LOSE
    case _:
        _log.warning(
            "reconciler.event.unexpected_state",
            event_id=str(event_id),
            state=snapshot.state.value,
        )
        return
```

или эквивалентный if/elif. Чёткое логирование "unexpected state" отделит этот путь от DB/HTTP-ошибок.

---

## Info

### IN-01: `_run_tick` использует `cast` без runtime-проверки наличия атрибутов на `app.state`

**File:** `src/bet_maker/jobs/reconciler.py:82-83`

**Issue:**
```python
sessionmaker = cast("async_sessionmaker[AsyncSession]", app.state.sessionmaker)
lookup = cast(HttpEventLookup, app.state.reconciler_event_lookup)
```

`cast` -- compile-time-only. Если lifespan забыл записать `app.state.sessionmaker` (например, при тестировании частичного wiring), здесь поднимется
`AttributeError`, что будет поймано outer `except Exception` и просто залогируется как "reconciler.tick.failed" -- без понятной причины.

**Fix:**
Использовать `getattr(app.state, "sessionmaker", None)` + early-return с явным warning либо assert-выражение с понятным сообщением. Минимально -- унифицировать с
`facades/deps.py:29-31` (там это сделано через `cast(... , request.app.state.sessionmaker)`, та же история, но в DI-провайдере -- failure mode там другой).

### IN-02: `assert self._cm is not None` в `PostgresUnitOfWork.__aexit__` -- хрупкий runtime-инвариант

**File:** `src/bet_maker/uow/postgres.py:65`

**Issue:**
`assert` стирается при запуске Python с `-O` (хотя production Dockerfile вряд ли его использует). Кроме того, такая защита через assert -- это именно то место,
которое падает в CR-01 (двойной вход). Замена на явный `if self._cm is None: raise UnitOfWorkNotStartedError(...)` (или хотя бы `RuntimeError`) сделает поведение
явным и устойчивым к `-O`.

**Fix:**
```python
async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
    if self._cm is None:
        raise UnitOfWorkNotStartedError(
            "PostgresUnitOfWork.__aexit__ called outside of an active context"
        )
    await self._cm.__aexit__(exc_type, exc, tb)
    self._cm = None
    self._session = None
```

### IN-03: Тестовые селекторы смешивают sync `def` и async tests в async-marked классе

**File:** `tests/bet_maker/selectors/test_get_pending_locked.py:46-50`, `tests/bet_maker/selectors/test_get_pending_event_ids.py:60-67`

**Issue:**
Классы декорированы `@pytest.mark.asyncio(loop_scope="session")`, что заставляет все методы быть async. Но `test_with_for_update_skip_locked_present` и
`test_no_commit_no_flush` -- обычные `def`. При `asyncio_mode = "auto"` это работает, но смешение стилей внутри одного class scope -- code smell. Логичнее вынести
sync-проверки в отдельный класс без `asyncio` mark (например, `class TestSelectorStaticInvariants:`).

**Fix:**
Вынести source-introspection-тесты в отдельный класс:

```python
class TestGetPendingLockedStaticInvariants:
    def test_with_for_update_skip_locked_present(self) -> None:
        ...
```

То же для `test_get_pending_event_ids.py`.

---

_Reviewed: 2026-05-19T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
