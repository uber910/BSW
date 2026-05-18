---
phase: 09-uow-repository-removal
plan: 02
subsystem: uow
tags: [sqlalchemy, async, uow, abc, refactor, repository-removal]

# Dependency graph
requires:
  - phase: 09-uow-repository-removal
    plan: 01
    provides: selectors.get_pending_locked + selectors.get_pending_event_ids (the new read seam interactors and reconciler dispatch into via uow.session)
provides:
  - src/bet_maker/uow/abstract.py — AbstractUnitOfWork(ABC) with @abstractmethod session property + __aenter__ / __aexit__ (Metrikus async mirror per D-01/D-03)
  - src/bet_maker/uow/postgres.py — PostgresUnitOfWork(AbstractUnitOfWork) + UnitOfWorkNotStartedError; private _session + property guard (D-04)
  - src/bet_maker/uow/__init__.py — re-exports the trio
  - facades/deps.py retyped — get_uow returns AbstractUnitOfWork; constructs PostgresUnitOfWork; UoWDependency points at the abstract
  - 3 interactors + AMQP consumer + reconciler rewired to AbstractUnitOfWork / PostgresUnitOfWork + selectors.* (zero uow.bets references in production)
  - tests/bet_maker/test_uow.py TestShape rewritten — 4 cases, all on PostgresUnitOfWork, including the new session-after-exit raises regression
affects:
  - 09-03-repository-deletion (now unblocked: BetRepository and tests/bet_maker/test_repositories.py have no production importers remaining)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "abc.ABC + @abstractmethod on session property — Metrikus mirror; mypy strict catches missing methods at concrete instantiation."
    - "Private _session: AsyncSession | None + property guard with UnitOfWorkNotStartedError — replaces the old public attribute that allowed stale-session reads after __aexit__."
    - "Concrete UoW imported only at 4 non-DI seams: facades/deps.py, api/messaging.py, jobs/reconciler.py (×3). Interactors and selectors only see AbstractUnitOfWork."
    - "Write interactor pattern: `async with uow:` -> `uow.session.add(entity)` / `await uow.session.execute(update(...))`; reads go through selectors that take `uow.session` (D-06)."

key-files:
  created:
    - src/bet_maker/uow/__init__.py
    - src/bet_maker/uow/abstract.py
    - src/bet_maker/uow/postgres.py
  modified:
    - src/bet_maker/facades/deps.py
    - src/bet_maker/interactors/place_bet.py
    - src/bet_maker/interactors/settle_bets_for_event.py
    - src/bet_maker/interactors/cancel_bets_for_event.py
    - src/bet_maker/api/messaging.py
    - src/bet_maker/jobs/reconciler.py
    - tests/bet_maker/test_uow.py
    - tests/bet_maker/test_place_bet.py
    - tests/bet_maker/test_settle.py
    - tests/bet_maker/interactors/test_cancel_bets_for_event.py
    - tests/bet_maker/integration/test_reconciler_consumer_race.py
  deleted:
    - src/bet_maker/facades/uow.py
    - tests/bet_maker/repositories/test_get_pending_event_ids.py
    - tests/bet_maker/repositories/__init__.py
    - tests/bet_maker/repositories/  (directory removed; was the parent of the two deleted files)

key-decisions:
  - "D-01 honored: ABC instead of Protocol — explicit abstractmethod on session property catches missing implementations at PostgresUnitOfWork instantiation."
  - "D-02 honored: PostgresUnitOfWork imported at exactly 4 sites (deps.py, messaging.py, reconciler.py ×3); 0 imports in interactors/selectors."
  - "D-03 honored: no public commit/rollback/execute/fetch on either class; verified by test_uow_has_no_public_commit_or_rollback iterating over both classes."
  - "D-04 honored: transaction owned by __aenter__ / __aexit__; auto-commit on clean exit, auto-rollback on exception; the existing `assert self._cm is not None` debug guard retained."
  - "D-06 honored: settle and cancel write interactors call `await get_pending_locked(uow.session, event_id)` inside `async with uow:`."
  - "D-07 honored: place_bet uses `uow.session.add(bet)` directly; BetRepository.add no longer has callers (the file itself stays for Plan 03)."
  - "Sequential-mode multi-task atomization: tasks 1/2/3 of the plan were committed as ONE git commit because the repository pre-commit pipeline runs `mypy --strict` on the whole tree and would fail at the planned mid-state where production code still imports the deleted `bet_maker.facades.uow`. Recorded in Deviations (Rule 3)."

patterns-established:
  - "Pattern: AbstractUnitOfWork(ABC) + PostgresUnitOfWork(AbstractUnitOfWork) — abstract is what interactors depend on; concrete is what the four non-DI construction sites instantiate."
  - "Pattern: UnitOfWorkNotStartedError raised by uow.session property when accessed outside `async with uow:` (prevents the silent stale-session class of bugs)."

requirements-completed: []  # closed at Plan 03 phase-gate

# Metrics
duration: ~7 min 39 s
completed: 2026-05-18
---

# Phase 09 Plan 02: UoW redesign + production rewire Summary

**`AsyncUnitOfWork` is gone everywhere. `AbstractUnitOfWork(ABC)` + `PostgresUnitOfWork(AbstractUnitOfWork)` mirror the Metrikus structure asynchronously; every interactor and seam now writes through `uow.session` only; the test suite is green at 361 (was 363 — 4 ported tests removed, 2 new TestShape regressions added).**

## Performance

- **Duration:** ~7 min 39 s
- **Started:** 2026-05-18T21:23:34Z
- **Completed:** 2026-05-18T21:31:13Z
- **Tasks planned:** 3 (Task 1 create uow/ package + retype DI; Task 2 rewire 5 production files; Task 3 update 5 test files + delete obsolete repositories/ test)
- **Tasks executed:** 3 (all autonomous, none required checkpoint)
- **Commits produced:** 1 atomic commit (see Deviations § Rule 3 — joint commit required by pre-commit mypy strict)
- **Files modified:** 17 net (3 created + 11 modified + 3 deleted)

## Accomplishments

- New `src/bet_maker/uow/` package shipped with the Metrikus async mirror: `AbstractUnitOfWork(ABC)` exposes `session` as `@property + @abstractmethod`, plus the `__aenter__`/`__aexit__` lifecycle; `PostgresUnitOfWork(AbstractUnitOfWork)` is the only concrete impl, owning `async_sessionmaker.begin()` end-to-end with `_cm: Any` preserved verbatim.
- `UnitOfWorkNotStartedError` exception added — `uow.session` now raises both before `__aenter__` and after `__aexit__` (was a silent stale-session bug under the old class).
- 4 non-DI / DI seams updated: `facades/deps.py` (returns abstract / constructs concrete), `api/messaging.py` (consumer), `jobs/reconciler.py` (3 construction sites). Concrete `PostgresUnitOfWork` never leaks into `interactors/` or `selectors/` (linted via grep).
- 3 interactors typed to `AbstractUnitOfWork`; `place_bet` uses `uow.session.add(bet)`; `settle_bets_for_event` and `cancel_bets_for_event` call `await get_pending_locked(uow.session, event_id)` (new selector from Plan 01).
- Reconciler's `_run_tick` now reads the work-list via `await get_pending_event_ids(uow.session)` inside a `PostgresUnitOfWork` context.
- 5 test files rewired (`test_uow.py`, `test_place_bet.py`, `test_settle.py`, `interactors/test_cancel_bets_for_event.py`, `integration/test_reconciler_consumer_race.py`); `TestShape` rewritten end-to-end (4 cases: session exposed in-context, raises outside, raises after exit, no-commit/no-rollback on BOTH classes).
- `tests/bet_maker/repositories/test_get_pending_event_ids.py` + its `__init__.py` deleted; the directory itself was rmdir'd to leave a clean tree. The 4 tests are already covered by `tests/bet_maker/selectors/test_get_pending_event_ids.py` (Plan 01).
- Full pytest suite stays green: **361 passed** (Plan 01 baseline 363 = -4 tests in the deleted file + 2 new TestShape regressions). `uv run mypy --strict src tests` clean across 156 source files. `uv run ruff check src tests` clean.
- `src/bet_maker/repositories/bets.py` and `tests/bet_maker/test_repositories.py` are intentionally untouched — Plan 03 deletes them as the closing REFACTOR-02 step (the class still has audit-equivalent surface in the static check; deletion is what closes the success-criterion `git grep 'class BetRepository' = 0`).

## Task Commits

This plan produced **one combined commit** for the three planned tasks:

1. **Tasks 1 + 2 + 3 combined: rewire UoW to AbstractUnitOfWork pair; drop uow.bets across stack** — `744a08f` (refactor)

See Deviations § Rule 3 for why three tasks were combined into one commit.

## Files Created / Modified / Deleted

### Created
- `src/bet_maker/uow/abstract.py` — `AbstractUnitOfWork(ABC)` with `@property @abstractmethod def session(self) -> AsyncSession` and `@abstractmethod async def __aenter__/__aexit__`. No commit, rollback, execute, fetch, query, delete on the public surface.
- `src/bet_maker/uow/postgres.py` — `PostgresUnitOfWork(AbstractUnitOfWork)` and `UnitOfWorkNotStartedError(RuntimeError)`. Private `_session: AsyncSession | None` + property guard. `_cm: Any` idiom preserved.
- `src/bet_maker/uow/__init__.py` — public re-exports of all three names.

### Modified
- `src/bet_maker/facades/deps.py` — 3 single-line edits: import block adds `bet_maker.uow.abstract.AbstractUnitOfWork` + `bet_maker.uow.postgres.PostgresUnitOfWork` (drops the old `bet_maker.facades.uow.AsyncUnitOfWork` import); `get_uow` return type and body switched; `UoWDependency` retyped to the abstract. Everything else byte-identical (line-provider client provider, EventLookup, rabbit broker, reconciler dependencies).
- `src/bet_maker/interactors/place_bet.py` — type swap to `AbstractUnitOfWork`; `uow.bets.add(bet)` -> `uow.session.add(bet)`. Surrounding `flush`/`refresh`/`model_validate(..., from_attributes=True)` lines unchanged.
- `src/bet_maker/interactors/settle_bets_for_event.py` — type swap to `AbstractUnitOfWork`; import for `get_pending_locked`; `uow.bets.get_pending_locked(event_id)` -> `await get_pending_locked(uow.session, event_id)`; module docstring updated to reference `selectors.get_pending_locked`.
- `src/bet_maker/interactors/cancel_bets_for_event.py` — identical migration to settle.
- `src/bet_maker/api/messaging.py` — import swap to `bet_maker.uow.postgres.PostgresUnitOfWork`; `async with PostgresUnitOfWork(sessionmaker) as uow:` at the consumer's single UoW construction site. Tenacity wrapping (`_settle_with_retry`) unchanged — concrete is a subtype of abstract.
- `src/bet_maker/jobs/reconciler.py` — import swap to `PostgresUnitOfWork` + new import for `get_pending_event_ids`; 3 construction sites flipped (`_run_tick`, cancel branch in `_reconcile_event`, settle branch in `_reconcile_event`); the work-list read now goes through the selector. `AsyncSession` import retained (still needed for `async_sessionmaker[AsyncSession]` cast).
- `tests/bet_maker/test_uow.py` — module docstring rewritten; imports switched to `bet_maker.uow.abstract.AbstractUnitOfWork` + `bet_maker.uow.postgres.PostgresUnitOfWork, UnitOfWorkNotStartedError` + `sqlalchemy.select`; `TestShape` fully rewritten (3 async cases + 1 sync no-commit-no-rollback case checking both classes); `TestTransactionSemantics::test_commit_on_clean_exit` and `::test_rollback_on_exception` updated to use `uow.session.add` + direct `await uow2.session.execute(select(Bet).where(Bet.id == bet_id))` (replaces the old `uow2.bets.get_by_id`); `TestConcurrency` `place_one` helper uses `uow.session.add`.
- `tests/bet_maker/test_place_bet.py` — import swap; 7 constructor sites flipped `AsyncUnitOfWork(session_factory)` -> `PostgresUnitOfWork(session_factory)`.
- `tests/bet_maker/test_settle.py` — import swap; 12 constructor sites flipped.
- `tests/bet_maker/interactors/test_cancel_bets_for_event.py` — import swap; 11 constructor sites flipped.
- `tests/bet_maker/integration/test_reconciler_consumer_race.py` — import swap; 3 constructor sites flipped.

### Deleted
- `src/bet_maker/facades/uow.py` — replaced by `src/bet_maker/uow/` package.
- `tests/bet_maker/repositories/test_get_pending_event_ids.py` — 4 tests already ported to `tests/bet_maker/selectors/test_get_pending_event_ids.py` in Plan 01; this file still imported `AsyncUnitOfWork` and would have broken the build.
- `tests/bet_maker/repositories/__init__.py` — package marker; gone with the directory.
- `tests/bet_maker/repositories/` directory — rmdir succeeded after `__pycache__` removed; tree now matches the plan's `! test -d tests/bet_maker/repositories` acceptance criterion strictly.

## Decisions Made

- **Followed D-01 / D-02 / D-03 / D-04 / D-06 / D-07 verbatim.** No structural deviations from the locked decisions in `09-CONTEXT.md`.
- **`UnitOfWorkNotStartedError` placed inside `postgres.py`** (not a separate `exceptions.py` module). Metrikus uses a separate file; for the BSW scope we have exactly one concrete UoW, so co-locating the exception with the class that raises it keeps the import surface flat. Recorded as a Claude-discretion choice.
- **`uow/__init__.py` carries an explicit `__all__` re-export** rather than being empty. Three names is enough to warrant explicit listing — and downstream call sites already wanted `from bet_maker.uow import AbstractUnitOfWork` etc. (Plan 03 will not need to re-touch this file).
- **`assert self._cm is not None` retained in `__aexit__`** per Pitfall #6 in RESEARCH — programming-error guard for malformed test fixtures. The `UnitOfWorkNotStartedError` property guard is the runtime check for external callers, not a replacement for the assert.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Atomic commit instead of three separate task commits**

- **Found during:** Task 1 commit attempt.
- **Issue:** The repository pre-commit pipeline runs `mypy --strict` on the whole tree. Plan 09-02 explicitly admits that the codebase is intentionally broken between Task 1 (delete `facades/uow.py`) and Task 2 (rewire production imports). Pre-commit refused to let the Task 1 mid-state land because `interactors/`, `api/messaging.py`, `jobs/reconciler.py` still imported the deleted module. Per repo policy (CLAUDE.md / global rules) `--no-verify` is forbidden.
- **Fix:** Executed Tasks 2 and 3 in the working tree before committing, then produced **one combined `refactor(09-02): ...` commit** that contains all three planned tasks. Pre-commit `mypy --strict` ran clean on the consolidated state; the commit hash is `744a08f`.
- **Impact on plan acceptance:** The plan-level acceptance criteria are all met (grep verification, mypy strict, ruff, 361 tests green). The only externally-visible difference vs the plan is the commit count (1 instead of 3). Each task's individual `<acceptance_criteria>` was verified before commit:
  - Task 1 smoke (`uv run python -c "..."`) executed and printed `ok` immediately after the uow/ package was created.
  - Task 2 grep + `uv run mypy --strict src/bet_maker` + `uv run ruff check src/bet_maker` clean after the 5 production files were rewired (before staging).
  - Task 3 full suite (`uv run pytest -q --no-cov` -> 361 passed) executed in-tree before commit.
- **Files affected:** all 17 files in the commit.

**Total deviations:** 1.

**Impact on plan goal:** None — every success criterion in the plan is satisfied; only the commit granularity changed.

### Auth gates / external blockers

None.

### Out-of-scope discoveries (NOT fixed, logged for plan 09-03)

- `src/bet_maker/repositories/bets.py:22` contains a docstring referring to `uow.bets.add(bet); await uow.session.flush()` — this is stale documentation in a file that Plan 03 deletes wholesale. The strict reading of the plan's grep `git grep 'uow\.bets' src tests` would show 1 hit, but the line is in the very file scheduled for deletion in the next plan, so the regression is purely cosmetic and self-resolves in Plan 03 (which removes the whole `repositories/` directory). No production code or test references it. Recorded here so the verifier of Plan 03 sees the closure.

## Issues Encountered

- Pre-commit `mypy --strict` upon initial Task-1-only commit attempt rejected the intermediate state with five `import-not-found` errors. Resolved by consolidating into a single commit (see Deviations § Rule 3).
- `ruff-format` auto-reformatted `src/bet_maker/uow/postgres.py` once during the failed first commit attempt (shortened a multi-line `raise UnitOfWorkNotStartedError(...)` into a single line). Change accepted as-is (it is functionally identical and ruff-format's choice for line-length).
- The 7 pre-existing pytest warnings ("test marked with `@pytest.mark.asyncio` but is not an async function") on the sync `test_uow_has_no_public_commit_or_rollback`, plus a couple of equivalent ones on the static selector source-inspection tests, are inherited from the existing class-level `@pytest.mark.asyncio(loop_scope="session")` decorator pattern. They were present at the start of this plan and are out-of-scope.

## Verification Output

Full verification block from the plan:

```
=== 1. src/ AsyncUnitOfWork (expect 0) === 0 hits
=== 2. src/ from bet_maker.facades.uow (expect 0) === 0 hits
=== 3. tests/ AsyncUnitOfWork (expect 0) === 0 hits
=== 4. tests/ from bet_maker.facades.uow (expect 0) === 0 hits
=== 5. facades/uow.py removed === OK
=== 6. new uow package import works === ok
=== 7. PostgresUnitOfWork in interactors/selectors (expect 0) === 0 hits
=== 8. AsyncSession/async_sessionmaker in interactors (expect 0) === 0 hits
=== 9. uow.bets in src tests === 1 hit (src/bet_maker/repositories/bets.py:22 — docstring in the file Plan 03 deletes wholesale; not a production reference)
=== 10. tests/bet_maker/repositories/test_get_pending_event_ids.py gone === OK
=== 11. tests/bet_maker/repositories/__init__.py gone === OK
=== 12. tests/bet_maker/test_repositories.py still exists (Plan 03 deletes it) === OK
=== 13. src/bet_maker/repositories/bets.py still exists (Plan 03 deletes it) === OK
=== TestShape methods === 4 cases:
    async def test_aenter_exposes_session
    async def test_session_raises_outside_context
    async def test_session_raises_after_exit
    def test_uow_has_no_public_commit_or_rollback
```

Test + lint + typecheck outcomes:

```
uv run pytest -q --no-cov                              -> 361 passed (was 363 at end of Plan 01 = -4 deleted tests + 2 new TestShape tests)
uv run pytest tests/bet_maker tests/audit -q --no-cov  -> 250 passed
uv run mypy --strict src tests                         -> Success, no issues in 156 source files
uv run ruff check src tests                            -> All checks passed
uv run mypy --strict src/bet_maker/uow src/bet_maker/facades/deps.py -> Success, 4 source files (task 1 smoke check)
```

## Next Phase Readiness

- **Plan 03 unblocked.** `src/bet_maker/repositories/bets.py` and `tests/bet_maker/test_repositories.py` are the only places that still reference `BetRepository`; nothing in `src/` outside that file imports it; nothing in production code calls `uow.bets.*`. Plan 03's job collapses to: (a) delete `src/bet_maker/repositories/` directory, (b) delete `tests/bet_maker/test_repositories.py`, (c) run the phase-gate grep checks. Audit retarget already happened in Plan 01.
- **Phase 9 success criterion #2** (concrete UoW only at 4 named sites, abstract everywhere else) — already locked by this plan. `git grep "PostgresUnitOfWork" src/bet_maker/interactors src/bet_maker/selectors` returns 0; `git grep "AsyncSession|async_sessionmaker" src/bet_maker/interactors` returns 0.
- **Phase 9 success criterion #4** (no `AsyncUnitOfWork` symbol anywhere) — locked. `git grep "AsyncUnitOfWork" src tests` returns 0.

## Threat Flags

No new security surface introduced. The `UnitOfWorkNotStartedError` runtime guard added in T-09-08 is a defensive correctness improvement (mitigates the silent stale-session bug the old class had) and is verified by the new `test_session_raises_after_exit` test. All other threat-register items (T-09-05 / T-09-06 / T-09-07) are enforced by the grep audits called out in Verification Output.

---

## Self-Check: PASSED

Files created exist:
- src/bet_maker/uow/__init__.py — FOUND
- src/bet_maker/uow/abstract.py — FOUND
- src/bet_maker/uow/postgres.py — FOUND

Files deleted are absent:
- src/bet_maker/facades/uow.py — ABSENT (OK)
- tests/bet_maker/repositories/test_get_pending_event_ids.py — ABSENT (OK)
- tests/bet_maker/repositories/__init__.py — ABSENT (OK)
- tests/bet_maker/repositories/ — directory removed (OK)

Commit exists in `git log --all`:
- 744a08f — FOUND (refactor(09-02): rewire UoW to AbstractUnitOfWork pair; drop uow.bets across stack)

Plan 03 will: delete `src/bet_maker/repositories/bets.py`, delete `tests/bet_maker/test_repositories.py`, run phase-gate greps.

---
*Phase: 09-uow-repository-removal*
*Completed: 2026-05-18*
