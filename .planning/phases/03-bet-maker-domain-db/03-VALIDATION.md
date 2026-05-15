---
phase: 3
slug: bet-maker-domain-db
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-15
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.1.0 + pytest-cov 7.1.0 |
| **Config file** | `pyproject.toml` ([tool.pytest.ini_options]) — extends P1/P2 config; adds `asyncio_default_fixture_loop_scope = "session"` if needed for session-scoped async fixtures (RESEARCH Assumption A3) |
| **Quick run command** | `uv run pytest tests/bet_maker -x -q --no-cov` |
| **Full suite command** | `uv run pytest --cov=src/bet_maker --cov-report=term-missing` |
| **Estimated runtime** | ~25–40 s (testcontainers PG cold-start ~6–10 s session-once; per-test TRUNCATE ~50–100 ms × ~30 tests ≈ ~3 s) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/bet_maker -x -q --no-cov`
- **After every plan wave:** Run `uv run pytest --cov=src/bet_maker --cov-report=term-missing`
- **Before `/gsd-verify-work`:** Full suite must be green; coverage ≥80% on `src/bet_maker/`
- **Max feedback latency:** 60 s (target — testcontainers cold-start dominates)

---

## Per-Task Verification Map

> Filled by `gsd-planner` during Step 8. Each task in PLAN.md MUST emit a row here (or list Wave 0 dependency). Format:

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 0 | BM-01, BM-05 | T-03-1-DOC | TZ drift verified — POST /bet body без coefficient | doc | `grep -q "ТЗ стр. 3" .planning/REQUIREMENTS.md` | OK | pending |
| 03-01-02 | 01 | 0 | BM-01 | T-03-1-DOC | BM-01 переписан per D-01 (без coefficient) | doc | `bash -c "! grep -q 'BM-01.*coefficient Decimal 6.2' .planning/REQUIREMENTS.md"` | OK | pending |
| 03-01-03 | 01 | 0 | BM-05 | T-03-1-DOC | BM-05 переписан per D-01; BM-13 добавлен per D-02 | doc | `grep -q "BM-13" .planning/REQUIREMENTS.md` | OK | pending |
| 03-01-04 | 01 | 0 | BM-01, BM-05 | T-03-2-DOC | Traceability table расширена BM-13 → Phase 3 | doc | `grep -q "BM-13 \| Phase 3 \| Pending" .planning/REQUIREMENTS.md` | OK | pending |
| 03-02-01 | 02 | 0 | QA-07 | — | testcontainers в dev-deps + coverage расширен на src/bet_maker + asyncio_default_fixture_loop_scope | shell | `uv run python -c "from testcontainers.postgres import PostgresContainer"` | W0 | pending |
| 03-02-02 | 02 | 0 | QA-07 | — | tests/conftest.py 6 PG fixtures (postgres_container + pg_dsn + apply_migrations + async_engine + session_factory + truncate_bets) | unit | `grep -c "PostgresContainer(\"postgres:16-alpine\"" tests/conftest.py` | W0 | pending |
| 03-02-03 | 02 | 0 | QA-07 | — | tests/bet_maker/conftest.py app + client + seed_event с LifespanManager | unit | `uv run pytest tests/bet_maker/test_health.py -q` | W0 | pending |
| 03-02-04 | 02 | 0 | QA-07 | — | 11 Wave 0 stub файлов созданы с pytest.mark.skip (test_schemas + test_models + test_db_engine + test_repositories + test_uow + test_event_lookup + test_place_bet + test_selectors + test_bet_routes + test_lifespan + test_alembic) | unit | `uv run pytest tests/bet_maker --collect-only -q` | W0 | pending |
| 03-02-05 | 02 | 0 | QA-07 | — | 03-VALIDATION.md frontmatter wave_0_complete=true | doc | `grep -q "wave_0_complete: true" .planning/phases/03-bet-maker-domain-db/03-VALIDATION.md` | OK | pending |
| 03-03-01 | 03 | 1 | BM-05, BM-06 | T-03-3 | EventState (str, Enum) duplicated; BetStatus (str, Enum); helpers/money.quantize_amount | unit | `uv run pytest tests/bet_maker/test_schemas.py -q` | W0 | pending |
| 03-03-02 | 03 | 1 | BM-05 | T-03-3 | BetCreate (Annotated Decimal max_digits=12, decimal_places=2, AfterValidator) + BetRead (extra='forbid', from_attributes=True) | unit | same | W0 | pending |
| 03-03-03 | 03 | 1 | BM-03 | — | helpers/status.py stub (event_state_to_bet_status — NotImplementedError для P5) | unit | `grep -q "raise NotImplementedError" src/bet_maker/helpers/status.py` | W0 | pending |
| 03-04-01 | 04 | 1 | BM-01 | T-03-3 | Bet model: Mapped[Decimal] = mapped_column(Numeric(12, 2)) + PG-ENUM bet_status | unit | `uv run pytest tests/bet_maker/test_models.py -q` | W0 | pending |
| 03-04-02 | 04 | 1 | BM-01 | — | alembic/env.py target_metadata = Base.metadata (PATTERNS.md Key Invariant 2) | unit | `grep -q "target_metadata = Base.metadata" alembic/env.py` | W0 | pending |
| 03-04-03 | 04 | 1 | BM-01 | T-03-6 | alembic/versions/0001_bets_initial.py with ENUM.create checkfirst=True | unit | `uv run pytest tests/bet_maker/test_alembic.py -q` | W0 | pending |
| 03-05-01 | 05 | 3 | BM-02 | T-03-1-pool | infrastructure/db/engine.py: create_async_engine с D-16 params + async_sessionmaker expire_on_commit=False | unit | `grep -q "pool_pre_ping=True" src/bet_maker/infrastructure/db/engine.py` | W0 | pending |
| 03-05-02 | 05 | 3 | BM-08 | T-03-2-DoS, T-03-5 | infrastructure/db/pings.py wait_for_postgres tenacity-decorated (stop_after_attempt=10, wait_exponential) + ping_postgres bool (SQLAlchemyError handler, no bare Exception) | unit | `grep -q "@retry" src/bet_maker/infrastructure/db/pings.py` | W0 | pending |
| 03-05-03 | 05 | 3 | BM-02, BM-08 | — | tests/bet_maker/test_db_engine.py replaces Wave 0 stub — 4+ tests covering engine params + ping_postgres True/False contract | unit | `uv run pytest tests/bet_maker/test_db_engine.py -q` | W0 | pending |
| 03-06-01 | 06 | 3 | BM-02 | T-03-3-Anti1 | facades/uow.py AsyncUnitOfWork + repositories/bets.py BetRepository (add + get_by_id, NO commit/rollback — grep-verified) | unit | `uv run pytest tests/bet_maker/test_uow.py tests/bet_maker/test_repositories.py -q` | W0 | pending |
| 03-06-02 | 06 | 3 | BM-06 | T-03-3-extra, T-03-3-frozen | facades/event_lookup.py: EventLookup Protocol + StubEventLookup (dict-backed seed/seed_active) + EventSnapshot frozen + extra='forbid' | unit | `uv run pytest tests/bet_maker/test_event_lookup.py -q` | W0 | pending |
| 03-06-03 | 06 | 3 | BM-03 | — | facades/deps.py: 6 providers (get_settings/get_engine/get_sessionmaker/get_session/get_uow/get_event_lookup) + 6 Annotated aliases | unit | `grep -c "Annotated\[" src/bet_maker/facades/deps.py` | W0 | pending |
| 03-07-01 | 07 | 4 | BM-05, BM-06 | T-03-3, T-03-3-rejection | interactors/place_bet.py: 3-branch validation (None / deadline / state) → EventNotBettable; happy path → BetRead inside session | unit | `uv run pytest tests/bet_maker/test_place_bet.py -q` | W0 | pending |
| 03-07-02 | 07 | 4 | BM-07 | — | selectors/list_bets.py: order_by(created_at DESC) + model_validate from_attributes | unit | `uv run pytest tests/bet_maker/test_selectors.py -q` | W0 | pending |
| 03-07-03 | 07 | 4 | BM-13 | — | selectors/get_bet.py: scalar_one_or_none → BetRead \| None | unit | same | W0 | pending |
| 03-08-01 | 08 | 5 | BM-08 | T-03-3, T-03-5 | health.py REPLACE: SELECT 1 via engine.connect → 200/503 JSON + structlog.warning health.check.failed | integration | `uv run pytest tests/bet_maker/test_health.py -q` | OK | pending |
| 03-08-02 | 08 | 5 | BM-08 | T-03-3 | lifespan.py EXTEND: create_async_engine + await wait_for_postgres (tenacity) + app.state.engine/sessionmaker/event_lookup | integration | `uv run pytest tests/bet_maker/test_lifespan.py -q` | W0 | pending |
| 03-08-03 | 08 | 5 | BM-05, BM-06, BM-07, BM-13 | T-03-3 | bets.py: POST /bet 201/422 + GET /bets 200 ordered + GET /bet/{id} 200/404; Decimal round-trip "10.00" | integration | `uv run pytest tests/bet_maker/test_bet_routes.py -q` | W0 | pending |
| 03-08-04 | 08 | 5 | BM-05 | — | app.py: include_router(bets.router) + P1 health test assertion update | integration | `uv run pytest tests/bet_maker -q` | OK | pending |
| 03-09-01 | 09 | 6 | QA-07 | — | Full bet_maker suite зелёный + coverage ≥80% src/bet_maker | shell | `uv run pytest --cov=src/bet_maker --cov-fail-under=80 tests/bet_maker -q` | OK | pending |
| 03-09-02 | 09 | 6 | BM-08 | T-03-6 | Manual alembic idempotency rehearsal через docker compose (см. Manual-Only Verifications) | manual | manual; documented in 03-09-SUMMARY | OK | pending |
| 03-09-03 | 09 | 6 | BM-01..03, BM-05..08, BM-13, QA-07 | — | REQUIREMENTS.md status flip + ROADMAP P3 checkbox + STATE.md advance | doc | `grep -q "Phase 3 complete" .planning/STATE.md` | OK | pending |

> All 10 risk axes mapped to at least one Per-Task Verification Map row (verified by gsd-plan-checker).

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

Tests scaffolding that MUST exist before any implementing task can run automated verification:

- [x] `tests/conftest.py` (root) — `postgres_container` session-scoped fixture using `testcontainers.postgres.PostgresContainer("postgres:16-alpine", driver="asyncpg")` (RESEARCH §3); yields DSN
- [x] `tests/conftest.py` (root) — `apply_migrations` session-scoped fixture: builds `alembic.config.Config` from `alembic.ini`, calls `set_main_option("sqlalchemy.url", dsn)`, runs `alembic.command.upgrade(cfg, "head")` (RESEARCH §4)
- [x] `tests/bet_maker/conftest.py` — UPDATED: PG-backed `client` fixture (replaces P1 in-memory build_app); `truncate_bets` autouse function-scoped fixture (`TRUNCATE bets RESTART IDENTITY CASCADE`); `seed_event` helper for `StubEventLookup`
- [x] `tests/bet_maker/test_schemas.py` — stubs for BM-05/BM-06 (BetCreate/BetRead/BetStatus/EventState/quantize_amount)
- [x] `tests/bet_maker/test_models.py` — stubs for BM-01, BM-02 (Bet shape, status default, created_at/updated_at server_default + refresh — RESEARCH §A1)
- [x] `tests/bet_maker/test_db_engine.py` — stub for BM-02/BM-08 (create_engine_and_sessionmaker + ping_postgres)
- [x] `tests/bet_maker/test_repositories.py` — stub for BM-03 (BetRepository.add/get_by_id, flush-not-commit invariant)
- [x] `tests/bet_maker/test_uow.py` — stub for D-17 (commit on clean exit, rollback on exception)
- [x] `tests/bet_maker/test_event_lookup.py` — stub for D-11 (StubEventLookup.seed / get_event / None-on-miss)
- [x] `tests/bet_maker/test_place_bet.py` — stubs for BM-06 (happy path, 3 EventNotBettable cases, amount quantization)
- [x] `tests/bet_maker/test_selectors.py` — stubs for BM-02, BM-05 (list ordering DESC, get_by_id, model_validate from_attributes)
- [x] `tests/bet_maker/test_bet_routes.py` — stubs for BM-05, BM-06, BM-07 + new BM-13 (POST 201 + 422 cases, GET /bets order, GET /bet/{id} 200/404, Decimal round-trip "10.00")
- [x] `tests/bet_maker/test_health.py` — stub for BM-08 (200 ok, 503 when PG down); P1 file already exists — expanded in Plan 03-08 Task 4 atomically with health.py replace
- [x] `tests/bet_maker/test_lifespan.py` — stub for D-27 (tenacity retry exhaustion → RuntimeError)
- [x] `tests/bet_maker/test_alembic.py` — stub for success criterion #5 (upgrade head idempotent rerun — guards RESEARCH §10 ENUM idempotency recipe)
- [x] `pyproject.toml` — adds `sqlalchemy[asyncio]==2.0.49`, `asyncpg==0.31.0`, `alembic==1.18.4`, `tenacity==9.1.4` to prod; `testcontainers>=4.9,<5` to dev (RESEARCH §3 — no `[postgresql]` extra)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `/health` returns 503 when `docker compose stop postgres` from outside test runner | BM-08 / Success #4 | Requires real `docker compose` state mutation; testcontainers PG-stop is awkward and not representative of compose lifecycle | `docker compose up -d bet-maker postgres && curl -s -w "%{http_code}" localhost:8001/health` then `docker compose stop postgres && sleep 2 && curl -s -w "%{http_code}" localhost:8001/health` — expect 200 → 503 |
| `alembic upgrade head` from a fresh `docker compose up` against an empty PG | Success #5 | End-to-end production rehearsal that the compose-driven startup applies migrations before bet-maker accepts traffic (depends on entrypoint script / one-shot job — to be planned) | `docker compose down -v && docker compose up -d postgres && docker compose run --rm bet-maker uv run alembic upgrade head && docker compose run --rm bet-maker uv run alembic upgrade head` — second run must be no-op |

---

## Critical Risk Axes (from RESEARCH §Validation Architecture)

Cross-reference for plan-checker — each axis must have at least one automated test row above:

1. **Decimal precision drift** → `test_bet_routes::test_amount_roundtrip_10_00`, `test_models::test_amount_numeric_12_2`
2. **ENUM type idempotency** → `test_alembic::test_upgrade_head_idempotent`
3. **Per-request UoW isolation under concurrency** → `test_uow::test_concurrent_uows_isolated` (asyncio.gather over 5 UoWs)
4. **testcontainers Docker availability in CI** → CI must run on a runner with Docker; document in README. Skip-marker `@pytest.mark.skipif(not docker_available)` is anti-pattern (silently passing test).
5. **Tenacity retry exhaustion** → `test_lifespan::test_postgres_unreachable_raises_after_retries` (override settings to `attempts=2` for speed)
6. **Health liveness during PG outage** → `test_health::test_health_503_when_pg_down` (force-close engine pool, do not stop testcontainer)
7. **Pydantic 422 message specificity** → `test_bet_routes::test_amount_more_than_2dp_returns_422`, `test_bet_routes::test_amount_zero_or_negative_422`, `test_bet_routes::test_extra_field_422`
8. **EventLookup stub seeding per test** → `test_event_lookup::*`, integration tests use `seed_event` helper
9. **GET /bets ordering under server_default created_at** → `test_selectors::test_list_bets_orders_by_created_at_desc` + `test_bet_routes::test_get_bets_ordering`
10. **Alembic rerun idempotency** → `test_alembic::test_upgrade_head_idempotent` (RESEARCH §2/§10 `ENUM.create(checkfirst=True)` + `create_type=False`)

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test files listed above scaffolded with `pytest.skip("Wave 0 stub")` before any implementing task lands)
- [x] No watch-mode flags (`pytest --watch` / `-f` forbidden — CI must run finite suite)
- [x] Feedback latency < 60 s
- [x] All 10 critical risk axes mapped to at least one automated test row
- [x] `nyquist_compliant: true` set in frontmatter (gsd-planner / gsd-plan-checker flips this after Wave 0 stubs land)

**Approval:** approved 2026-05-15 by gsd-planner Phase 3 (Plan 03-02)
