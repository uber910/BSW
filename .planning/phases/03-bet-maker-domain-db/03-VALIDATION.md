---
phase: 3
slug: bet-maker-domain-db
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| 03-XX-XX | XX | N | BM-YY | — / T-03-Z | {expected behavior} | unit/integration | `uv run pytest tests/bet_maker/test_*.py::test_*` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Tests scaffolding that MUST exist before any implementing task can run automated verification:

- [ ] `tests/conftest.py` (root) — `postgres_container` session-scoped fixture using `testcontainers.postgres.PostgresContainer("postgres:16-alpine", driver="asyncpg")` (RESEARCH §3); yields DSN
- [ ] `tests/conftest.py` (root) — `apply_migrations` session-scoped fixture: builds `alembic.config.Config` from `alembic.ini`, calls `set_main_option("sqlalchemy.url", dsn)`, runs `alembic.command.upgrade(cfg, "head")` (RESEARCH §4)
- [ ] `tests/bet_maker/conftest.py` — UPDATED: PG-backed `client` fixture (replaces P1 in-memory build_app); `truncate_bets` autouse function-scoped fixture (`TRUNCATE bets RESTART IDENTITY CASCADE`); `seed_event` helper for `StubEventLookup`
- [ ] `tests/bet_maker/test_models.py` — stubs for BM-01, BM-02 (Bet shape, status default, created_at/updated_at server_default + refresh — RESEARCH §A1)
- [ ] `tests/bet_maker/test_repositories.py` — stub for BM-03 (BetRepository.add/get_by_id, flush-not-commit invariant)
- [ ] `tests/bet_maker/test_uow.py` — stub for D-17 (commit on clean exit, rollback on exception)
- [ ] `tests/bet_maker/test_event_lookup.py` — stub for D-11 (StubEventLookup.seed / get_event / None-on-miss)
- [ ] `tests/bet_maker/test_place_bet.py` — stubs for BM-06 (happy path, 3 EventNotBettable cases, amount quantization)
- [ ] `tests/bet_maker/test_selectors.py` — stubs for BM-02, BM-05 (list ordering DESC, get_by_id, model_validate from_attributes)
- [ ] `tests/bet_maker/test_bet_routes.py` — stubs for BM-05, BM-06, BM-07 + new BM-13 (POST 201 + 422 cases, GET /bets order, GET /bet/{id} 200/404, Decimal round-trip "10.00")
- [ ] `tests/bet_maker/test_health.py` — stub for BM-08 (200 ok, 503 when PG down)
- [ ] `tests/bet_maker/test_lifespan.py` — stub for D-27 (tenacity retry exhaustion → RuntimeError)
- [ ] `tests/bet_maker/test_alembic.py` — stub for success criterion #5 (upgrade head idempotent rerun — guards RESEARCH §10 ENUM idempotency recipe)
- [ ] `pyproject.toml` — adds `sqlalchemy[asyncio]==2.0.49`, `asyncpg==0.31.0`, `alembic==1.18.4`, `tenacity==9.1.4` to prod; `testcontainers>=4.9,<5` to dev (RESEARCH §3 — no `[postgresql]` extra)

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (test files listed above scaffolded with `pytest.skip("Wave 0 stub")` before any implementing task lands)
- [ ] No watch-mode flags (`pytest --watch` / `-f` forbidden — CI must run finite suite)
- [ ] Feedback latency < 60 s
- [ ] All 10 critical risk axes mapped to at least one automated test row
- [ ] `nyquist_compliant: true` set in frontmatter (gsd-planner / gsd-plan-checker flips this after Wave 0 stubs land)

**Approval:** pending
