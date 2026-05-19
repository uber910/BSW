---
phase: 09-uow-repository-removal
verified: 2026-05-19T12:00:00Z
status: passed
score: 18/18 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
requirements_satisfied:
  - REFACTOR-02
  - REFACTOR-03
  - REFACTOR-05
---

# Фаза 9: UoW Redesign + Repository Removal — отчёт о верификации

**Phase Goal (из ROADMAP.md):** `AsyncUnitOfWork` становится абстрактным контрактом + конкретной Postgres-реализацией по образцу `~/Interexy/Metrikus/metrikus-app/api_common/unit_of_work/`; интеракторы принимают `uow: AsyncUnitOfWork` как DI-параметр и обращаются к сессии только через `uow.session`. Слой `repositories/` удалён целиком — чтения переезжают в `selectors/`, записи — в `interactors/`.

**Verified:** 2026-05-19T12:00:00Z
**Status:** passed
**Re-verification:** No — initial verification (после code-review-fix цикла)

---

## Goal Achievement — Success Criteria (ROADMAP §Phase 9)

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| SC-1 | UoW-пакет экспортирует `AbstractUnitOfWork` AND `PostgresUnitOfWork`; интеракторы и тесты зависят от абстрактного типа; конкретный тип возвращается FastAPI Depends-провайдером. | VERIFIED | `src/bet_maker/uow/__init__.py` экспортирует все 3 имени; runtime-проверка через `uv run python -c "..."` подтверждает `inspect.isabstract(AbstractUnitOfWork) == True`. `typing.get_type_hints(get_uow)['return'] is AbstractUnitOfWork`. `src/bet_maker/facades/deps.py:45-52` возвращает `PostgresUnitOfWork(sessionmaker)`, типизировано как `AbstractUnitOfWork`. |
| SC-2 | `async with uow:` управляет одной транзакцией; `uow.session` — единственная сессионная ручка; ни один интерактор не открывает `AsyncSession` напрямую. `git grep -E 'async_sessionmaker\|AsyncSession' src/bet_maker/interactors src/bet_maker/selectors` → 0 hits. | VERIFIED (с уточнением) | `git grep -E 'async_sessionmaker\|AsyncSession' src/bet_maker/interactors` → 0 hits (interactors clean). В selectors 8 hits легитимны: `get_pending_locked.py`, `get_pending_event_ids.py`, `get_bet.py`, `list_bets.py` принимают `session: AsyncSession` как параметр — это D-05 (zlocked в CONTEXT.md, документировано в Plan 09-02 SC#5 и Plan 09-03 SC#3). SC#2 как написано буквально в ROADMAP не выполнено по букве в части selectors, но архитектурный инвариант (никакой интерактор не открывает session напрямую) удовлетворён, и автор плана/контекста явно перевёл этот SC в форму «scoped to interactors only» в Plan 09-03 SC#3. |
| SC-3 | `src/bet_maker/repositories/` не существует; `git grep 'class BetRepository'` → 0 hits в src/ и tests/. | VERIFIED | `find src -type d -name repositories` → empty. `find tests -type d -name repositories` → empty. `git grep -n 'class BetRepository' src tests` → exit 1 (0 hits). `git grep -n 'BetRepository' src tests` → exit 1 (0 hits — даже строковое упоминание отсутствует). |
| SC-4 | `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` удалён или заменён эквивалентом. | VERIFIED | `tests/audit/test_static.py:41` содержит новую функцию `test_pending_locked_selector_uses_for_update_skip_locked`. Старое имя отсутствует. Аудит читает `src/bet_maker/selectors/get_pending_locked.py` и проверяет литерал `with_for_update(skip_locked=True)`. Тест проходит (`uv run pytest tests/audit/test_static.py` → 8 passed). |
| SC-5 | v1.0 behavioural surface unchanged: 355+ тестов green, mypy strict clean, ruff clean, coverage ≥85% (REFACTOR-05); POST /bet / GET /bets / consumer / reconciler производят byte-identical responses на e2e-фикстуре. | VERIFIED (автоматическая часть); behavioural smoke approved by user | Автоматическая часть проверена локально: `uv run pytest -q --cov=src --cov-fail-under=85` → 355 passed, 26 warnings, coverage 94.41%. `uv run mypy --strict src tests` → Success, 153 files. `uv run ruff check src tests` → All checks passed. `uv run ruff format --check src tests` → 153 files already formatted. Поведенческие smoke-тесты (docker compose + 5 curl-проверок) выполнены пользователем локально (per user note: «Plan 09-03 Task 2 human-verify smoke was completed locally by the user before this verification run»). |

**Score:** 5/5 success-criteria verified

---

## PLAN Frontmatter Must-Haves

### Plan 09-01 (selectors seam) — Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Два новых selector-а в `src/bet_maker/selectors/` владеют FOR UPDATE SKIP LOCKED и DISTINCT PENDING запросами. | VERIFIED | `src/bet_maker/selectors/get_pending_locked.py:34` содержит `.with_for_update(skip_locked=True)` + `Bet.status == BetStatus.PENDING`. `src/bet_maker/selectors/get_pending_event_ids.py:23` содержит `.distinct()` + `Bet.status == BetStatus.PENDING`. |
| 2 | D-05: оба selector-а принимают `AsyncSession` напрямую (без UoW knowledge), без commit/flush/rollback. | VERIFIED | `get_pending_locked.py:12` подпись `async def get_pending_locked(session: AsyncSession, event_id: UUID) -> list[Bet]`. `get_pending_event_ids.py:12` подпись `async def get_pending_event_ids(session: AsyncSession) -> list[UUID]`. `grep -E '\.(commit\|flush\|rollback)\(' src/bet_maker/selectors/get_pending_*.py` → no matches. Импортов `AbstractUnitOfWork`/`PostgresUnitOfWork` в selectors — 0. |
| 3 | D-08: audit retargeted на `test_pending_locked_selector_uses_for_update_skip_locked` против selectors/get_pending_locked.py. | VERIFIED | `tests/audit/test_static.py:41` функция переименована; `read_text()` указывает на `selectors/get_pending_locked.py`. Тест passes. |
| 4 | D-09: дополнительного «no repositories dir» audit нет — phase SC #3 enforces filesystem state. | VERIFIED | В `tests/audit/test_static.py` нет «no repositories dir» теста. Контракт enforced через `find src -type d -name repositories` + git grep (см. SC-3 выше). |
| 5 | Full pytest suite green после plan 01 — additive changes. | VERIFIED | Финальный suite 355 passed (post-review-fix). |

### Plan 09-02 (UoW redesign + production rewire) — Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 6 | D-01: `src/bet_maker/uow/abstract.py` экспортирует `AbstractUnitOfWork(ABC)` с `@abstractmethod` на `__aenter__`, `__aexit__`, и `session` property — ABC, не Protocol. | VERIFIED | `src/bet_maker/uow/abstract.py:23` `class AbstractUnitOfWork(ABC):`; lines 38-52 содержат `@property @abstractmethod def session`, `@abstractmethod async def __aenter__`, `@abstractmethod async def __aexit__`. `inspect.isabstract(AbstractUnitOfWork) == True` (runtime check). |
| 7 | D-02: интеракторы и selectors типизированы на `AbstractUnitOfWork`; `PostgresUnitOfWork` появляется только в 4 не-DI seams (`facades/deps.py`, `api/messaging.py`, `jobs/reconciler.py` ×2). `git grep 'PostgresUnitOfWork' src/bet_maker/interactors src/bet_maker/selectors` → 0. | VERIFIED | `git grep -n 'PostgresUnitOfWork' src/bet_maker/interactors src/bet_maker/selectors` → exit 1 (0 hits). Интеракторы `place_bet.py:14`, `settle_bets_for_event.py:43`, `cancel_bets_for_event.py:45` импортируют `AbstractUnitOfWork`. `PostgresUnitOfWork` встречается в `facades/deps.py:52`, `api/messaging.py:172`, `jobs/reconciler.py:127,153` (4 construction sites после WR-01 fix — было 3+1, теперь reconciler читает work-list через bare `sessionmaker()`). |
| 8 | D-03: structural mirror — ABC/concrete split, `session` property, lifecycle через `__aenter__/__aexit__`. NO public `commit()/rollback()/execute()/delete()/query()/fetch()/fetch_one()`. | VERIFIED | `hasattr(AbstractUnitOfWork, 'commit') == False`, `hasattr(AbstractUnitOfWork, 'rollback') == False`, same for `PostgresUnitOfWork` (runtime check). Интеракторы пишут через `uow.session.add(...)` / `uow.session.execute(update(...))` напрямую (SQLAlchemy 2.0 API). |
| 9 | D-04: транзакция управляется внутри concrete class — `__aenter__` входит в `async_sessionmaker.begin()`, `__aexit__` доверяет SQLAlchemy auto-commit/auto-rollback. | VERIFIED | `src/bet_maker/uow/postgres.py:54-57` — `__aenter__` вызывает `self._sessionmaker.begin()` + `await self._cm.__aenter__()`. Lines 59-68 — `__aexit__` вызывает `await self._cm.__aexit__(exc_type, exc, tb)`, что и обеспечивает SQLAlchemy commit/rollback. |
| 10 | D-06: write-интеракторы (`settle`, `cancel`) вызывают lock-selector через `uow.session` внутри открытого UoW. | VERIFIED | `settle_bets_for_event.py:63-64` — `async with uow:` → `bets = await get_pending_locked(uow.session, event_id)`. `cancel_bets_for_event.py:56-57` — same pattern. |
| 11 | D-07: `BetRepository.add` устранён — `place_bet` вызывает `uow.session.add(bet)` напрямую через SQLAlchemy 2.0 API. | VERIFIED | `src/bet_maker/interactors/place_bet.py:77` — `uow.session.add(bet)`. `BetRepository` класс не существует (SC-3). |
| 12 | `uow.session` — единственная сессионная ручка в interactor; ни `AsyncSession`, ни `async_sessionmaker` import не появляется в `src/bet_maker/interactors/`. | VERIFIED | `git grep -nE 'async_sessionmaker\|AsyncSession' src/bet_maker/interactors` → exit 1 (0 hits). Все три интерактора используют только `uow.session` через `AbstractUnitOfWork` параметр. |
| 13 | Доступ к `uow.session` вне `async with uow:` бросает `UnitOfWorkNotStartedError`. | VERIFIED | `src/bet_maker/uow/postgres.py:48-52` — property guard. `tests/bet_maker/test_uow.py::TestShape::test_session_raises_outside_context` + `test_session_raises_after_exit` зелёные. |
| 14 | Все 355+ тестов green; `src/bet_maker/facades/uow.py` deleted; `AsyncUnitOfWork` symbol больше не существует. | VERIFIED | Файл `src/bet_maker/facades/uow.py` отсутствует (ls → No such file or directory). `git grep -n 'AsyncUnitOfWork' src tests` → exit 1 (0 hits). 355 passed в финальном suite. |

### Plan 09-03 (BetRepository deletion + phase gate) — Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 15 | `src/bet_maker/repositories/` directory не существует. | VERIFIED | `find src -type d -name repositories` → empty. |
| 16 | `git grep 'class BetRepository' src tests` → 0 hits. | VERIFIED | exit 1 (0 hits). `git grep -n 'BetRepository' src tests` тоже 0 hits. |
| 17 | `git grep -E 'from bet_maker\.repositories' src tests` → 0 hits. | VERIFIED | exit 1 (0 hits). |
| 18 | Full pytest suite passes (≥355 tests, no new skips/xfails), mypy strict clean, ruff clean, coverage ≥85%. | VERIFIED | 355 passed, coverage 94.41%, mypy strict OK (153 files), ruff OK, ruff format OK. (Plan 09-03 SUMMARY указывало 353/94.54%; review-fix добавил 2 регресс-теста для CR-01, итог +2 теста / -0.13% coverage.) |

**Score (frontmatter truths):** 13/13 verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/bet_maker/uow/__init__.py` | Re-exports `AbstractUnitOfWork`, `PostgresUnitOfWork`, `UnitOfWorkNotStartedError` | VERIFIED | Файл существует, 19 строк; `__all__` явный список 3 имён. Import smoke OK. |
| `src/bet_maker/uow/abstract.py` | `AbstractUnitOfWork(ABC)` с `@abstractmethod session`, `__aenter__`, `__aexit__` | VERIFIED | 53 строки. Содержит `class AbstractUnitOfWork(ABC):` (line 23) + 3 abstractmethods. |
| `src/bet_maker/uow/postgres.py` | `PostgresUnitOfWork(AbstractUnitOfWork)` + `UnitOfWorkNotStartedError`; private `_session`, property guard, `_cm: Any` idiom | VERIFIED | 69 строк. `class PostgresUnitOfWork(AbstractUnitOfWork):` (line 36), `class UnitOfWorkNotStartedError(RuntimeError):` (line 32), private `_session: AsyncSession \| None` (line 46), property guard raises `UnitOfWorkNotStartedError` (lines 48-52). |
| `src/bet_maker/selectors/get_pending_locked.py` | `async def get_pending_locked(session, event_id) -> list[Bet]` с `with_for_update(skip_locked=True)` | VERIFIED | 37 строк. SQL содержит `with_for_update(skip_locked=True)` + `Bet.status == BetStatus.PENDING`. Нет commit/flush/rollback. |
| `src/bet_maker/selectors/get_pending_event_ids.py` | `async def get_pending_event_ids(session) -> list[UUID]` с `.distinct()` | VERIFIED | 26 строк. SQL: `select(Bet.event_id).where(Bet.status == BetStatus.PENDING).distinct()`. |
| `src/bet_maker/facades/deps.py` | `get_uow → AbstractUnitOfWork`; constructs `PostgresUnitOfWork`; `UoWDependency = Annotated[AbstractUnitOfWork, Depends(get_uow)]` | VERIFIED | Line 45 `def get_uow(request) -> AbstractUnitOfWork`. Line 52 `return PostgresUnitOfWork(sessionmaker)`. Line 100 `UoWDependency = Annotated[AbstractUnitOfWork, Depends(get_uow)]`. |
| `src/bet_maker/interactors/place_bet.py` | `uow: AbstractUnitOfWork`; `uow.session.add(bet)` | VERIFIED | Line 36 `uow: AbstractUnitOfWork`. Line 77 `uow.session.add(bet)`. Нет `uow.bets.add(...)`. |
| `src/bet_maker/interactors/settle_bets_for_event.py` | `uow: AbstractUnitOfWork`; `await get_pending_locked(uow.session, event_id)` | VERIFIED | Line 52 `uow: AbstractUnitOfWork`. Line 64 `bets = await get_pending_locked(uow.session, event_id)`. |
| `src/bet_maker/interactors/cancel_bets_for_event.py` | `uow: AbstractUnitOfWork`; `await get_pending_locked(uow.session, event_id)` | VERIFIED | Line 49 `uow: AbstractUnitOfWork`. Line 57 `bets = await get_pending_locked(uow.session, event_id)`. |
| `src/bet_maker/api/messaging.py` | Construction site `PostgresUnitOfWork(sessionmaker)` (handler scope) | VERIFIED (with CR-01 fix) | Line 172 `uow = PostgresUnitOfWork(sessionmaker)` — UoW конструируется, но НЕ открывается в handler-е (CR-01 fix: `async with PostgresUnitOfWork` в файле — 0 hits; interactor `settle_bets_for_event` сам открывает `async with uow:`). |
| `src/bet_maker/jobs/reconciler.py` | `PostgresUnitOfWork(sessionmaker)` на construction sites; `await get_pending_event_ids(uow.session)` | VERIFIED (with WR-01 fix) | После WR-01 fix `_run_tick` использует `async with sessionmaker() as session:` для work-list (line 89), без UoW-обёртки. `_reconcile_event` строит `PostgresUnitOfWork(sessionmaker)` на 2 construction sites (lines 127 cancel-branch, line 153 settle-branch). |
| `tests/bet_maker/test_uow.py` | TestShape rewritten — 4 случая (aenter exposes, raises outside, raises after exit, no-commit-no-rollback на обоих классах) | VERIFIED | Line 28 `class TestShape:` с 4 методами (test_aenter_exposes_session, test_session_raises_outside_context, test_session_raises_after_exit, test_uow_has_no_public_commit_or_rollback) — все 4 теста passed. `TestTransactionSemantics`, `TestConcurrency` используют `PostgresUnitOfWork(session_factory)`. |
| `tests/audit/test_static.py` | Функция `test_pending_locked_selector_uses_for_update_skip_locked` | VERIFIED | Line 41. Тест passes. Docstring очищен от литерала `BetRepository` (Plan 09-03 docstring scrub). |

**Score (artifacts):** 13/13 verified

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `facades/deps.py::get_uow` | `uow/postgres.py::PostgresUnitOfWork` | `return PostgresUnitOfWork(sessionmaker)` typed as `AbstractUnitOfWork` | WIRED | `facades/deps.py:52` matches pattern. mypy strict accepts (concrete is subtype of abstract). |
| `interactors/settle_bets_for_event.py` | `selectors/get_pending_locked.py` | `await get_pending_locked(uow.session, event_id)` | WIRED | `settle_bets_for_event.py:64` matches pattern. Import on line 42 `from bet_maker.selectors.get_pending_locked import get_pending_locked`. |
| `interactors/cancel_bets_for_event.py` | `selectors/get_pending_locked.py` | `await get_pending_locked(uow.session, event_id)` | WIRED | `cancel_bets_for_event.py:57` matches pattern. Import on line 44. |
| `jobs/reconciler.py::_run_tick` | `selectors/get_pending_event_ids.py` | `await get_pending_event_ids(uow.session)` → (after WR-01) `await get_pending_event_ids(session)` | WIRED (с архитектурно лучшим вариантом) | `jobs/reconciler.py:90` `event_ids = await get_pending_event_ids(session)` — WR-01 fix заменил транзакционный UoW на bare `sessionmaker()`. Архитектурно корректнее (read-only селектор не нуждается в транзакции). Import on line 50. |
| `api/messaging.py::on_event_finished` | `interactors/settle_bets_for_event.py` через `_settle_with_retry` | `PostgresUnitOfWork(sessionmaker)` → `_settle_with_retry(uow, ...)` | WIRED (с CR-01 fix) | `api/messaging.py:172-179` строит UoW unentered, передаёт в `_settle_with_retry`, ack-ает после возврата. Интерактор сам делает `async with uow:`. |
| `tests/audit/test_static.py::test_pending_locked_...` | `src/bet_maker/selectors/get_pending_locked.py` | `(SRC / "bet_maker" / "selectors" / "get_pending_locked.py").read_text()` + assert literal | WIRED | `tests/audit/test_static.py:49` читает целевой файл и проверяет наличие `with_for_update(skip_locked=True)`. |

**Score (key links):** 6/6 wired

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|---------------------|--------|
| `selectors/get_pending_locked.py` | `result` | `session.execute(select(Bet)...)` против Postgres | Yes — real `select() + with_for_update + status filter` | FLOWING |
| `selectors/get_pending_event_ids.py` | `result` | `session.execute(select(Bet.event_id).distinct())` против Postgres | Yes — real DISTINCT SQL | FLOWING |
| `interactors/place_bet.py` | `bet` (ORM объект) | `Bet(...)` + `uow.session.add(bet)` + `uow.session.flush()` + `uow.session.refresh(bet)` | Yes — фактическая запись в PG, refresh подтягивает server defaults | FLOWING |
| `interactors/settle_bets_for_event.py` | `bets`, `bet_ids` | `await get_pending_locked(uow.session, event_id)` → `update(Bet).where(Bet.id.in_(bet_ids))` | Yes — UPDATE применяется и commit-ится UoW-ом | FLOWING |
| `interactors/cancel_bets_for_event.py` | `bets`, `bet_ids` | Same pattern as settle | Yes | FLOWING |
| `jobs/reconciler.py::_run_tick` | `event_ids` | `await get_pending_event_ids(session)` через bare `sessionmaker()` контекст | Yes — DISTINCT query возвращает actual pending event ids | FLOWING |

**No hollow props / no static fallback / no disconnected data sources** — данные текут от Postgres через selectors в interactors → коммит в UoW.

---

## Behavioural Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| UoW package importable + ABC inspection | `uv run python -c "from bet_maker.uow import ...; assert inspect.isabstract(AbstractUnitOfWork)"` | `IMPORT_OK: abstract=<class 'bet_maker.uow.abstract.AbstractUnitOfWork'> concrete=...` | PASS |
| `get_uow` DI provider возвращает абстрактный тип | `typing.get_type_hints(get_uow)['return'] is AbstractUnitOfWork` | True (assertion passed) | PASS |
| AbstractUnitOfWork и PostgresUnitOfWork не имеют public commit/rollback | `not hasattr(AbstractUnitOfWork, 'commit')` × 2 классов × 2 атрибутов | All True | PASS |
| Audit test проходит на новом seam | `uv run pytest tests/audit/test_static.py::test_pending_locked_selector_uses_for_update_skip_locked -q` | passed | PASS |
| TestShape — все 4 регрессии работают | `uv run pytest tests/bet_maker/test_uow.py::TestShape -v` | 4 passed | PASS |
| Selectors integration suite | `uv run pytest tests/bet_maker/selectors/ -v` | 7 passed | PASS |
| Full quality bar | `uv run pytest -q --cov=src --cov-fail-under=85 && uv run mypy --strict src tests && uv run ruff check src tests` | 355 passed, coverage 94.41%, mypy clean, ruff clean | PASS |
| End-to-end docker smoke (POST /bet, GET /bets, consumer settle, reconciler settle, /health) | `docker compose up` + 5 curl checks (Plan 09-03 Task 2) | Confirmed by user locally before this verification run | PASS (user-confirmed) |

**Spot-checks:** 8/8 pass

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REFACTOR-02 | 09-01, 09-02, 09-03 | Слой `repositories/` удалён полностью; чтения в `selectors/`, записи в `interactors/` напрямую через UoW; `BetRepository` и `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` исчезли или заменены | SATISFIED | `src/bet_maker/repositories/` не существует. Audit retargeted на selectors/get_pending_locked.py. `git grep 'BetRepository' src tests` → 0 hits. `BetRepository.add` → `uow.session.add` в place_bet. `BetRepository.get_pending_*` → selectors/get_pending_*. REQUIREMENTS.md уже отмечен Complete. |
| REFACTOR-03 | 09-02 | `AsyncUnitOfWork` приведён к структуре Metrikus — абстрактный класс + конкретная Postgres-реализация, `async with uow:` управляет транзакцией, инжектится в interactor как `uow: AbstractUnitOfWork`. Никаких прямых сессий в интеракторах — только через `uow.session`. | SATISFIED | `src/bet_maker/uow/abstract.py` + `postgres.py` доставлены. Интеракторы типизированы на `AbstractUnitOfWork`. `git grep 'AsyncSession' src/bet_maker/interactors` → 0 hits. `git grep 'AsyncUnitOfWork' src tests` → 0 hits. REQUIREMENTS.md отмечен Complete. |
| REFACTOR-05 | 09-01, 09-02, 09-03 | Cross-cutting quality bar: 355+ тестов green, mypy strict, ruff clean, coverage ≥85%, никаких новых `# type: ignore` или `# noqa` сверх baseline. | SATISFIED | 355 passed (точно ≥355), coverage 94.41% (≥85%), mypy strict clean (153 files), ruff clean. Suppression counters: `type: ignore` = 55 (Phase 8 baseline 59, −4), `# noqa` = 55 (Phase 8 baseline 56, −1). Никаких новых suppressions; даже одна снята благодаря WR-02 fix (удаление `# noqa: PLW0603`). REQUIREMENTS.md отмечен «Phases 8, 9 met — pending Phase 10». |

**No orphaned requirements** — все 3 ID из PLAN frontmatters покрыты, ни одного дополнительного REFACTOR-XX не упоминается в REQUIREMENTS.md → Phase 9 mapping.

---

## Anti-Patterns Scan

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/bet_maker/uow/postgres.py` | 65 | `assert self._cm is not None` (защищается от `-O` в проде; review-IN-02 предложил заменить на explicit raise) | Info | Не блокер: review-fix scope was CR-01 + WR-01..04 (per `09-REVIEW-FIX.md` — IN-01..03 deferred); production Dockerfile не использует `-O`; явный property guard на `session` уже бросает `UnitOfWorkNotStartedError` для внешнего вызывающего кода. Recorded в REVIEW.md как future hardening. |
| `tests/bet_maker/selectors/test_get_pending_locked.py`, `test_get_pending_event_ids.py` | 46/60 | `def` (sync) внутри `@pytest.mark.asyncio(loop_scope="session")`-decorated class — pytest warning | Info | Не блокер: тот же паттерн уже встречается в `tests/bet_maker/test_uow.py::TestShape::test_uow_has_no_public_commit_or_rollback`; вытянуть sync-тесты в отдельный класс — IN-03 в review, помечено как deferred. Все тесты passing, no behavioural regression. |
| `src/bet_maker/api/messaging.py` | 99-101 | `_settings = BetMakerSettings()` на module level + `router = RabbitRouter(...)` module-level | Info | FastStream API требует declarations на module level (router декларирует subscribers через декораторы). Известный архитектурный compromise; ранее module-level `_sessionmaker` global был критическим WR-02 — снят в commit `ac752f4` (теперь через `router.context.set_global`). |

**Stub / hollow data check:** Все ключевые компоненты возвращают реальные данные из Postgres. Не обнаружено: hardcoded `[]`, hardcoded `{}`, `return null`, `pass`/`# TODO`/`# FIXME` в production коде Phase 9.

`grep -nE 'TODO|FIXME|XXX|HACK|PLACEHOLDER|not yet implemented' src/bet_maker/{uow,selectors,interactors,api/messaging.py,jobs/reconciler.py,facades/deps.py}` → 0 hits.

---

## Code Review Closure

Phase 9 прошёл полный review cycle (см. `09-REVIEW.md` и `09-REVIEW-FIX.md`):

- **CR-01 (Critical):** Двойной вход в `PostgresUnitOfWork` в AMQP-хендлере → fixed commit `eaaf3f1`. Handler больше не открывает UoW; интерактор владеет контекстом. Регрессионные тесты (static + behavioural через TestRabbitBroker counting subclass) добавлены.
- **WR-01:** Reconciler `_run_tick` использовал транзакционный UoW для read-only селектора → fixed commit `7bb6f74`. Заменён на bare `sessionmaker()` context.
- **WR-02:** Module-level mutable global `_sessionmaker` → fixed commit `ac752f4`. Sessionmaker теперь живёт на `router.context.set_global(...)`; handler читает через `Context()` DI marker. Также добавлен `extend-immutable-calls` для B008.
- **WR-03:** Reconciler терял `event_id` в logger context → fixed commit `24bff5b`. Wrapped per-event work в `structlog.contextvars.bound_contextvars(event_id=...)`.
- **WR-04:** `EventTerminalState(snapshot.state.value)` бросал ValueError на не-терминальном состоянии → fixed commit `c98eeb8`. Заменён на явный `match snapshot.state:` whitelist с `_` веткой для unexpected states.

**Findings status:** 5/5 in-scope fixed (Critical + 4 Warnings); IN-01..03 deferred per orchestrator scope (Info-level only).

Post-fix metrics:
- 355 passed (was 353 at Phase 9 closure; +2 регресс-теста для CR-01)
- coverage 94.41% (was 94.54%; −0.13% за счёт reuse-coverage в TestRabbitBroker)
- type: ignore total = 55 (unchanged), # noqa total = 55 (−1 from Phase 8 baseline 56, благодаря удалению `# noqa: PLW0603`)

---

## Suppression Baseline Check

| Counter | Phase 8 closeout (baseline) | Phase 9 closeout | Phase 9 post-review-fix | Status |
|---------|---:|---:|---:|---|
| `type: ignore` | 59 | 55 (−4) | 55 (unchanged from closeout) | PASS — ≤ baseline |
| `# noqa` | 56 | 56 (same) | 55 (−1 from baseline) | PASS — ≤ baseline |

REFACTOR-05 contract satisfied: никаких новых suppressions; net уменьшение.

---

## Deferred Items (Step 9b)

Нет deferred items. Все 5 success criteria относятся к Phase 9 целиком; ни один не делегирован в Phase 10. Phase 10 (Shared-code consolidation) — отдельная независимая работа над cross-service near-duplicates.

---

## Human Verification Required

Нет открытых human-verify items.

**Plan 09-03 Task 2 (docker compose + 5 curl-smoke checks: POST /bet, GET /bets, consumer settle, reconciler settle, /health на обоих сервисах) выполнен локально пользователем перед запуском верификации** (per phase context).

SC#5 behavioural clause (byte-identical responses на e2e fixture) подтверждён пользователем; этот verifier не повторяет docker-compose smoke автономно (no Docker daemon control assumed).

---

## Gaps Summary

**No blocking gaps.** Все 5 ROADMAP success criteria, все 13 PLAN-frontmatter truths и все 13 artifacts удовлетворены.

Тонкая интерпретация SC#2: ROADMAP пишет «`git grep -E 'async_sessionmaker|AsyncSession' src/bet_maker/interactors src/bet_maker/selectors` returns zero hits» как буквальное условие, но Plan 09-02 и Plan 09-03 явно перевели этот SC в «scoped to interactors only» (D-05 declares selectors legitimately take `AsyncSession` as parameter). Архитектурный инвариант (никаких прямых сессий в интеракторах + UoW владеет транзакцией) полностью выполнен. Это framing-clarification, а не gap; документирована в Plan 09-02 acceptance criteria и Plan 09-03 SC#3.

Все автоматические шесть gate-проверок (5 grep-проверок + suite + lint + typecheck) выполнены на момент верификации.

---

## Verification Conclusion

**Status: passed**

- Goal achieved: AsyncUnitOfWork → AbstractUnitOfWork + PostgresUnitOfWork pair доставлен; интеракторы зависят от абстрактного типа; `uow.session` — единственная сессионная ручка в интеракторах; `BetRepository` физически удалён; reads → selectors, writes → interactors через UoW.
- Quality bar: 355 passed / 94.41% coverage / mypy --strict clean (153 files) / ruff clean / suppression counters ниже Phase 8 baseline.
- Code review cycle closed: 1 critical + 4 warnings (in-scope) fixed atomically в commits `eaaf3f1`, `7bb6f74`, `24bff5b`, `c98eeb8`, `ac752f4`.
- Behavioural smoke confirmed by user (docker compose + 5 curl checks).
- Requirements: REFACTOR-02, REFACTOR-03, REFACTOR-05 → all SATISFIED, REQUIREMENTS.md уже обновлён, Progress table отражает 3/3 plans complete.

Phase 9 готов к закрытию. Phase 10 (Shared-code consolidation) разблокирован — interactor/selector/UoW boundaries stable.

---

_Verified: 2026-05-19T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
