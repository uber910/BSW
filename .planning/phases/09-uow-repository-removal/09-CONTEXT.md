# Phase 9: UoW redesign + Repository removal - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

`AsyncUnitOfWork` превращается в абстрактный контракт + конкретную Postgres-реализацию по образцу `~/Interexy/Metrikus/metrikus-app/api_common/unit_of_work/`: `AbstractUnitOfWork(ABC)` + `PostgresUnitOfWork(AbstractUnitOfWork)`. Интеракторы принимают `uow: AbstractUnitOfWork` через FastAPI DI и работают только через `uow.session` (никаких `uow.bets.*`).

Слой `src/bet_maker/repositories/` удаляется целиком: запись (`add`) уходит в write-интеракторы (`place_bet`, `settle_bets_for_event`, `cancel_bets_for_event`) через прямой `uow.session.add(...)`; чтения (`get_pending_locked`, `get_pending_event_ids`, `get_by_id`) переезжают в `src/bet_maker/selectors/` как тонкие SQL-обёртки над `AsyncSession` (без commit/flush).

Поведенческого изменения нет: API surface, AMQP-контракт, e2e fixture-выводы и 355+ тестов остаются неизменными (REFACTOR-05 как cross-cutting quality bar). mypy strict, ruff, coverage ≥85% — без новых `# type: ignore` или `# noqa`.

</domain>

<decisions>
## Implementation Decisions

### Abstract контракт (REFACTOR-03)
- **D-01:** `AbstractUnitOfWork(ABC)` с `@abstractmethod` на `__aenter__`, `__aexit__`, `session` (property). Это буквальное зеркало Metrikus-структуры (`api_common/unit_of_work/abstract.py`). Не Protocol — roadmap явно указывает на Metrikus-эталон, ABC даёт явное наследование и mypy strict ловит пропущенные методы при инстанциировании `PostgresUnitOfWork`. Существующий codebase-паттерн `EventLookup(Protocol)` остаётся в своём слое (facades) и не пересекается.
- **D-02:** Интеракторы и тесты типизируются на `AbstractUnitOfWork` (или его aliased import `UnitOfWork`); конкретный тип `PostgresUnitOfWork` фигурирует только в DI-провайдере (`get_uow`). Линт-инвариант: `git grep "PostgresUnitOfWork" src/bet_maker/interactors src/bet_maker/selectors` → 0 hits.

### Metrikus shape (REFACTOR-03)
- **D-03:** Структурное зеркало, НЕ буквальное. Переносим из Metrikus: разделение на abstract + concrete файлы; `session` как property; lifecycle через `__aenter__/__aexit__`. НЕ переносим: публичные `commit()/rollback()/execute()/delete()/query()/fetch()/fetch_one()` — у нас интерактор пишет в `uow.session` напрямую через SQLAlchemy 2.0 API (`session.add`, `session.execute(update(...))`, `session.flush()`). Это сохраняет Anti-Pattern 1 v1.0 baseline и существующий аудит `tests/audit/.../test_uow_has_no_public_commit_or_rollback`.
- **D-04:** Транзакция управляется внутри класса: `__aenter__` входит в `async_sessionmaker.begin()` (как сейчас); `__aexit__` пускает SQLAlchemy auto-commit / auto-rollback. Никаких ручных `await uow.commit()` снаружи — текущий тест `test_uow_has_no_public_commit_or_rollback` остаётся в силе на новом классе (`AbstractUnitOfWork` и `PostgresUnitOfWork`).

### Selector сигнатуры (REFACTOR-02)
- **D-05:** Все selectors принимают `AsyncSession` (не `AbstractUnitOfWork`). Унифицированный контракт: selector — это thin SQL wrapper над session, без знаний про UoW (соответствует формулировке roadmap «thin SQL wrappers, no commit/flush»).
  - Текущие `list_bets(session)`, `get_bet_by_id(session, bet_id)` — без изменений.
  - Переезжающие из repositories/: `get_pending_locked(session, event_id)`, `get_pending_event_ids(session)`.
- **D-06:** Write-интерактор передаёт `uow.session` явно в lock-selector внутри открытого UoW-контекста:
  ```python
  async with uow:
      bets = await get_pending_locked(uow.session, event_id)
      ...
  ```
  Read-роуты используют `get_session` DI напрямую (как сейчас в `GET /bets`, `GET /bet/{id}`).
- **D-07:** `BetRepository.add` упраздняется. В `place_bet`:
  ```python
  async with uow:
      bet = Bet(event_id=event_id, amount=quantize_amount(amount))
      uow.session.add(bet)
      await uow.session.flush()
      await uow.session.refresh(bet)
  ```

### Audit fate (REFACTOR-02)
- **D-08:** `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` переименовывается в `test_pending_locked_selector_uses_for_update_skip_locked` и перенацеливается на `src/bet_maker/selectors/get_pending_locked.py`. Инвариант R3 (FOR UPDATE SKIP LOCKED) остаётся под static-сетью на новом seam — быстрый, детерминированный, без PG.
- **D-09:** Дополнительный «no repositories dir» аудит не добавляем — это уже покрывается DOD #3 в success criteria phase 9 (`git grep 'class BetRepository'` = 0) и логикой удаления каталога. Не плодим static-аудиты сверх необходимого (контрапример: phase 8 D-04 удерживал ровно тот же scope).

### Claude's Discretion
- Файловое размещение: либо `src/bet_maker/uow/{abstract.py, postgres.py}` (Metrikus-зеркало 1-в-1), либо одиночный `src/bet_maker/facades/uow.py` с обоими классами. Планнеру решить, исходя из объёма кода (если concrete > 80 LOC, package оправдан).
- Имя абстрактного класса: `AbstractUnitOfWork` (Metrikus) vs `UnitOfWork` (более короткое). По умолчанию — Metrikus-имя ради близости к источнику.
- Шаг DI-провайдера: текущий паттерн — `def get_uow(request) -> AsyncUnitOfWork` возвращает свежий не-вошедший UoW; интерактор сам делает `async with uow:`. Этот паттерн сохраняется (не переключаемся на generator-style `yield uow`). Это инвариант v1.0.
- Гранулярность коммитов в плане — планнеру. Лучше: (1) ввести abstract+concrete параллельно с repositories, (2) перевести интеракторы по одному, (3) перевести selectors, (4) удалить repositories + переименовать audit.
- Удаление `tests/bet_maker/test_repositories.py` и `tests/bet_maker/repositories/test_get_pending_event_ids.py`: переписать под selectors (новые имена тестов на новом seam) — это default-выбор; планнеру допустимо вынести в отдельные планы.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope
- `.planning/ROADMAP.md` §Phase 9 — goal, success criteria, pitfalls-prevented (UoW redesign + Repository removal)
- `.planning/REQUIREMENTS.md` §v1.1 — REFACTOR-02 (repositories removal), REFACTOR-03 (UoW redesign), REFACTOR-05 (quality bar)

### Metrikus reference (mandatory — D-01/D-03)
- `~/Interexy/Metrikus/metrikus-app/api_common/unit_of_work/abstract.py` — эталон `AbstractUnitOfWork(ABC)` (sync, sync-методы). У нас async-зеркало.
- `~/Interexy/Metrikus/metrikus-app/api_common/unit_of_work/postgres.py` — эталон `PostgresUnitOfWork`. Внимание: мы НЕ переносим публичные `commit()/rollback()/execute()/delete()/query()/fetch()` (D-03).
- `~/Interexy/Metrikus/metrikus-app/api_common/unit_of_work/exceptions.py` — `UnitOfWorkNotStartedError` (актуально для guard на `session` property).

### Current code (will be modified or removed)
- `src/bet_maker/facades/uow.py` — текущий `AsyncUnitOfWork`. Либо переезжает в `src/bet_maker/uow/postgres.py`, либо переписывается inline с добавлением `AbstractUnitOfWork`.
- `src/bet_maker/repositories/bets.py` — `BetRepository` (add + get_by_id + get_pending_locked + get_pending_event_ids). Удаляется. Содержимое мигрирует.
- `src/bet_maker/facades/deps.py` §`get_uow` + `UoWDependency` — DI seam, тип меняется на `AbstractUnitOfWork`.
- `src/bet_maker/interactors/place_bet.py` — `uow.bets.add(bet)` → `uow.session.add(bet)`.
- `src/bet_maker/interactors/settle_bets_for_event.py` — `uow.bets.get_pending_locked(event_id)` → `await get_pending_locked(uow.session, event_id)`.
- `src/bet_maker/interactors/cancel_bets_for_event.py` — то же изменение, что и settle.
- `src/bet_maker/jobs/reconciler.py` §`_run_tick` — `uow.bets.get_pending_event_ids()` → `await get_pending_event_ids(uow.session)` (внутри короткой read-only UoW).
- `src/bet_maker/selectors/get_bet.py`, `selectors/list_bets.py` — без изменений сигнатур (уже принимают `AsyncSession`).

### Tests (will be modified)
- `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` → переименовать + перенацелить (D-08).
- `tests/audit/test_static.py::test_uow_has_no_public_commit_or_rollback` — обновить класс-цель (`PostgresUnitOfWork` + `AbstractUnitOfWork`).
- `tests/bet_maker/test_uow.py` — переписать под новый класс, сохранить семантику (commit on clean exit, rollback on exception, per-request isolation).
- `tests/bet_maker/test_repositories.py` — удалить или переписать под `selectors/get_pending_locked` (новое имя файла теста: `tests/bet_maker/selectors/test_get_pending_locked.py`).
- `tests/bet_maker/repositories/test_get_pending_event_ids.py` → `tests/bet_maker/selectors/test_get_pending_event_ids.py` (переезд + правка импортов).
- `tests/bet_maker/test_place_bet.py`, `test_settle.py`, `interactors/test_cancel_bets_for_event.py`, `integration/test_reconciler_consumer_race.py` — обновить mock'и/фикстуры (`uow.bets` → `uow.session`).

### Invariants to preserve (REFACTOR-05 quality bar)
- 355+ existing tests must stay green; no skips, no xfails added (REFACTOR-05).
- `mypy --strict src` zero errors; ruff clean; coverage ≥85%.
- Anti-Pattern 1: external code never calls `await uow.commit()` / `await uow.rollback()`; verified by `test_uow_has_no_public_commit_or_rollback`.
- R3 (FOR UPDATE SKIP LOCKED): the query lives in `selectors/get_pending_locked.py` после переезда — проверяется static-аудитом на новом seam (D-08) + интеграционным `test_reconciler_consumer_race`.
- A1 (expire_on_commit=False) — `src/bet_maker/infrastructure/db/engine.py` уже корректен, фаза 9 его не трогает.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/bet_maker/facades/uow.py::AsyncUnitOfWork.__aenter__/__aexit__` — паттерн «вход в `async_sessionmaker.begin()` через `_cm: Any`» переносится в `PostgresUnitOfWork` буквально. Это уже отработанная идиома против mypy strict + private SQLAlchemy типа.
- `src/bet_maker/selectors/list_bets.py`, `selectors/get_bet.py` — эталон сигнатуры `(session: AsyncSession, ...) -> DTO`. Новые `get_pending_locked` и `get_pending_event_ids` следуют этому же контракту, но возвращают `list[Bet]` / `list[UUID]` соответственно (read-внутри-UoW, не DTO).
- `src/bet_maker/facades/event_lookup.py::EventLookup(Protocol)` — пример Protocol-контракта в codebase. Используется для контраста (D-01): UoW делаем ABC, не Protocol, потому что Metrikus-эталон и потому что abstract — это нечто, что инстанцируется ровно в DI seam.

### Established Patterns
- **Caller-driven transaction**: `async with uow:` всегда в interactor, не в роуте. После фазы 9 это правило не меняется.
- **No module-level sessionmaker leaks**: sessionmaker берётся из `app.state` через `get_sessionmaker` DI; UoW принимает `sessionmaker` через `__init__`. Сохраняем (D-01).
- **selectors возвращают DTO для роутов, ORM для интеракторов**: list_bets/get_bet возвращают `BetRead`; get_pending_locked возвращает `list[Bet]` (нужен `.id` для UPDATE). Новые selectors следуют этому разделению.
- **One AsyncSession per UoW per business operation** (A2): не меняется, каждый интерактор открывает свежий UoW.

### Integration Points
- `src/bet_maker/facades/deps.py::get_uow` — единственный seam, где конкретный `PostgresUnitOfWork` инстанциируется. После D-01 тип возврата: `AbstractUnitOfWork`. `UoWDependency = Annotated[AbstractUnitOfWork, Depends(get_uow)]`.
- `src/bet_maker/api/messaging.py::on_event_finished` — handler уже строит `AsyncUnitOfWork(sessionmaker)` напрямую (не через DI), потому что FastStream-handler вне Request-цикла. После фазы 9: `PostgresUnitOfWork(sessionmaker)`. Импорт меняется, паттерн нет.
- `src/bet_maker/jobs/reconciler.py::_run_tick`, `_reconcile_event` — те же `AsyncUnitOfWork(sessionmaker)` вызовы; обновить импорт + два call-site `uow.bets.get_pending_event_ids()` → `await get_pending_event_ids(uow.session)`.
- `src/bet_maker/app.py` / `lifespan.py` — никаких изменений (DI seam через `app.state.sessionmaker` уже корректен).

</code_context>

<specifics>
## Specific Ideas

- Эталон шага миграции: повторить структурный приём phase 8 (D-04) — `git grep` после фазы должен возвращать 0 hits на регрессии:
  - `git grep "class BetRepository" src tests` → 0 hits.
  - `find src -type d -name repositories` → 0 каталогов.
  - `git grep -E "uow\.bets" src tests` → 0 hits.
  - `git grep -E "from bet_maker\.repositories" src tests` → 0 hits.
- Имя файла теста selector: `tests/bet_maker/selectors/test_get_pending_locked.py` — параллельно с `test_get_bet.py`, `test_list_bets.py`. Не `repositories/` подкаталог.
- Постфикс name'а concrete UoW: `PostgresUnitOfWork` (Metrikus-зеркало), не `AsyncPostgresUnitOfWork` — async видна по сигнатурам `__aenter__/__aexit__`, постфикс избыточен.

</specifics>

<deferred>
## Deferred Ideas

- **SingleStore/Blob UoW реализации** — у Metrikus есть `singlestore.py` + `azure_blob.py`; в BSW не нужны. Появятся в v2, если будут.
- **`uow.session.execute()` обёртки** (`uow.execute`, `uow.fetch`) — Metrikus экспортирует их, но у нас SQLAlchemy 2.0 API + select() уже идиоматичны. Если кодовая база разрастётся — рассмотреть в follow-up.
- **Shared `AbstractUnitOfWork` в shared-пакете** — phase 10 (REFACTOR-04). Сейчас живёт в `bet_maker/uow/`; line-provider UoW не имеет (in-memory store). Не возникает дублирования, выносить нечего.
- **Generator-style DI provider (`async with uow: yield uow`)** — Metrikus делает именно так, но это меняет интерактор-контракт (UoW уже вошёл). Решили оставить текущий factory-style (D-04 / Claude's Discretion). Возможный refactor если появится несколько backends.
- **`runtime_checkable` на Protocol** — обсуждалось как часть варианта Protocol, но Protocol отброшен.

</deferred>

---

*Phase: 9-uow-repository-removal*
*Context gathered: 2026-05-18*
