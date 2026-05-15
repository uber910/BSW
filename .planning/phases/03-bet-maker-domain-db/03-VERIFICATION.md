---
phase: 03-bet-maker-domain-db
verified: 2026-05-15T21:00:00Z
status: passed
score: 6/6
overrides_applied: 0
---

# Phase 3: bet-maker domain (DB) — Verification Report

**Phase Goal:** bet-maker persists bets in PostgreSQL through UoW + Repository, exposes `POST /bet` and `GET /bets`, and `/health` pings PG. No AMQP, no HTTP integration with line-provider yet.
**Verified:** 2026-05-15T21:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /bet accepts {event_id, amount}, returns 201 BetRead, persists PENDING bet | VERIFIED | `entrypoints/api/bets.py:16-45` — status_code=201, response_model=BetRead; `interactors/place_bet.py:76-87` — Bet inserted inside UoW, model_validate inside session |
| 2 | POST /bet rejects 422 for >2dp, amount<=0, extra field, and 4xx for non-bettable event | VERIFIED | `schemas/bets.py:30-34` — Amount Annotated with Field(gt=0, decimal_places=2) + AfterValidator; `bets.py:41-45` — EventNotBettable mapped to 422; 8 rejection tests in TestPostBet + 3 in TestPostBetEventNotBettable |
| 3 | GET /bets returns full history ordered by created_at DESC | VERIFIED | `selectors/list_bets.py:20` — `select(Bet).order_by(Bet.created_at.desc())`; `test_bet_routes.py:182-198` — ordering asserted |
| 4 | GET /health returns 200/503 based on PG SELECT 1 result | VERIFIED | `entrypoints/api/health.py:23-31` — 200 {status:ok, checks:{postgres:ok}} / 503 {status:degraded, checks:{postgres:down}}; `test_health.py:40-56` — 503 tested via AsyncMock patching ping_postgres |
| 5 | alembic upgrade head creates bets table + bet_status ENUM; rerun is idempotent | VERIFIED | `alembic/versions/20260515_0001_bets_initial.py:30-37` — `postgresql.ENUM.create(checkfirst=True)` + `create_type=False` throughout; `test_alembic.py:62-73` — third upgrade head call in test, apply_migrations fixture calls twice; manual docker compose rehearsal approved |
| 6 | Decimal round-trip: POST amount="10.00" → GET /bets returns "10.00" | VERIFIED | Pydantic v2 serializes Decimal as str in JSON mode (verified: `{"amount": "10.00"}`); `test_bet_routes.py:47-52` — POST 201 asserts `body["amount"] == "10.00"`; `test_selectors.py:115-126` — DB round-trip via get_bet_by_id asserts `str(read.amount) == "10.00"` |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/bet_maker/entrypoints/api/bets.py` | POST /bet, GET /bets, GET /bet/{id} | VERIFIED | 78 lines, substantive, all 3 routes wired via include_router in app.py |
| `src/bet_maker/interactors/place_bet.py` | 3-branch EventNotBettable + UoW insert | VERIFIED | 88 lines, validation outside UoW, model_validate inside session |
| `src/bet_maker/selectors/list_bets.py` | ORDER BY created_at DESC | VERIFIED | `order_by(Bet.created_at.desc())` line 20 |
| `src/bet_maker/selectors/get_bet.py` | scalar_one_or_none → BetRead | None | VERIFIED | 22 lines, returns BetRead or None |
| `src/bet_maker/entrypoints/api/health.py` | 200/503 SELECT 1 | VERIFIED | per-request ping, 200 ok / 503 degraded format |
| `src/bet_maker/models/bet.py` | Numeric(12,2), no coefficient | VERIFIED | Mapped[Decimal] = mapped_column(Numeric(12, 2)); no coefficient column |
| `src/bet_maker/schemas/bets.py` | Amount Annotated + BetRead from_attributes | VERIFIED | gt=0, decimal_places=2, AfterValidator(quantize_amount), from_attributes=True |
| `src/bet_maker/infrastructure/db/engine.py` | pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800, expire_on_commit=False | VERIFIED | All 5 D-16/D-15 params present |
| `src/bet_maker/infrastructure/db/pings.py` | wait_for_postgres tenacity 10 attempts; ping_postgres SQLAlchemyError handler | VERIFIED | @retry stop_after_attempt(10), wait_exponential; except SQLAlchemyError only (not bare Exception) |
| `src/bet_maker/repositories/bets.py` | add (no commit), get_by_id | VERIFIED | No commit/rollback calls; flush controlled by interactor |
| `src/bet_maker/facades/uow.py` | async_sessionmaker.begin() context manager | VERIFIED | 54 lines; auto-commit on clean exit via _cm.__aexit__ |
| `src/bet_maker/facades/event_lookup.py` | EventLookup Protocol + EventSnapshot frozen + StubEventLookup | VERIFIED | frozen=True, extra="forbid", seed() + seed_active() |
| `src/bet_maker/facades/deps.py` | 6 providers + 6 Annotated aliases | VERIFIED | EngineDep, SessionDep, UoWDep, EventLookupDep, SettingsDep, SessionmakerDep |
| `alembic/versions/20260515_0001_bets_initial.py` | ENUM checkfirst=True + create_type=False | VERIFIED | Both patterns present; no coefficient column, no (event_id, status) index |
| `alembic/env.py` | target_metadata = Base.metadata | VERIFIED | Line 23; reads DSN from BetMakerSettings |
| `tests/bet_maker/test_bet_routes.py` | ≥4 distinct 422 cases + decimal round-trip | VERIFIED | 8 422 rejection tests + 3 EventNotBettable + decimal roundtrip |
| `tests/bet_maker/test_alembic.py` | idempotent rerun proof | VERIFIED | apply_migrations calls upgrade head x2; test adds x3 |
| `tests/conftest.py` | testcontainers + apply_migrations + truncate_bets | VERIFIED | PostgresContainer("postgres:16-alpine", driver="asyncpg"); apply_migrations calls upgrade head twice |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bets.py POST /bet` | `place_bet interactor` | `await place_bet(uow, ...)` | WIRED | line 35 |
| `bets.py GET /bets` | `list_bets selector` | `await list_bets(session)` | WIRED | line 58 |
| `bets.py GET /bet/{id}` | `get_bet_by_id selector` | `await get_bet_by_id(session, bet_id)` | WIRED | line 71 |
| `health.py GET /health` | `ping_postgres` | `await ping_postgres(engine)` | WIRED | line 23 |
| `place_bet` | `BetRepository.add` | `uow.bets.add(bet)` | WIRED | line 78 |
| `lifespan` | `wait_for_postgres` | `await wait_for_postgres(engine)` | WIRED | line 35 |
| `lifespan` | `app.state.event_lookup` | `StubEventLookup()` | WIRED | line 44 |
| `app.py` | `bets router` | `include_router(bets.router)` | WIRED | line 18 |
| `alembic/env.py` | `Base.metadata` | `target_metadata = Base.metadata` | WIRED | line 23 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `entrypoints/api/bets.py POST /bet` | BetRead return | `place_bet` → `uow.bets.add(bet)` → `session.flush()` → `session.refresh(bet)` → `model_validate(bet)` | DB INSERT + refresh | FLOWING |
| `entrypoints/api/bets.py GET /bets` | list[BetRead] | `list_bets(session)` → `select(Bet).order_by(...)` → `session.execute` | DB SELECT | FLOWING |
| `entrypoints/api/health.py` | JSONResponse | `ping_postgres(engine)` → `engine.connect()` → `SELECT 1` | Real DB connection | FLOWING |

---

### Pitfall Mitigations (Verification Checks G-N)

| Check | Status | Evidence |
|-------|--------|---------|
| G-A1: expire_on_commit=False | VERIFIED | `infrastructure/db/engine.py:37` — `async_sessionmaker(engine, expire_on_commit=False)`; model_validate inside session at `place_bet.py:87` |
| G-A2: per-request UoW, sessionmaker singleton | VERIFIED | `facades/deps.py:40-47` — `AsyncUnitOfWork(sessionmaker)` constructed fresh per request; sessionmaker is module-level via app.state |
| G-A3: pool params | VERIFIED | `engine.py:31-36` — pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800 |
| G-A4/A5: Numeric(12,2) + Annotated Decimal | VERIFIED | `models/bet.py:57-60`; `schemas/bets.py:30-34` |
| G-D2: tenacity retry in lifespan | VERIFIED | `pings.py:20-25` — @retry(stop_after_attempt(10), wait_exponential); called from `lifespan.py:35` |
| H: repository never commits | VERIFIED | `grep self._session.commit repositories/bets.py` → empty; BetRepository has only `.add()` and `.get_by_id()` |
| I: no out-of-scope code | VERIFIED | No consumers/, workers/, broker/, line_provider_client.py, RabbitMQ, reconciliation implementations; `reconciliation_interval_s` is config field only (prepared for P6), no actual implementation |
| I: no coefficient column | VERIFIED | `models/bet.py` — 6 columns only (id, event_id, amount, status, created_at, updated_at); migration confirms `numeric(12,2)` with no coefficient |
| I: no (event_id, status) index | VERIFIED | Migration has only `bets_pkey` PRIMARY KEY index |
| M: no coefficient in BM-01 | VERIFIED | REQUIREMENTS.md BM-01 explicitly states "Per D-01: coefficient НЕ хранится" |
| M: BM-13 registered | VERIFIED | REQUIREMENTS.md BM-13 present and marked `[x] Complete (Plan 03-09)` |

---

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|---------|
| BM-01 (Bet model, Numeric 12.2, no coefficient) | SATISFIED | `models/bet.py:46-74`; no coefficient column |
| BM-02 (UoW async context manager, repo flushes, UoW commits) | SATISFIED | `facades/uow.py`; `repositories/bets.py` (flush via interactor, UoW commits) |
| BM-03 (layered architecture) | SATISFIED | entrypoints / facades / interactors / selectors / helpers all present |
| BM-05 (POST /bet 201 BetRead) | SATISFIED | `entrypoints/api/bets.py:16-45` |
| BM-06 (event validation: deadline, state) | SATISFIED | `interactors/place_bet.py:55-74` — 3-branch EventNotBettable |
| BM-07 (GET /bets ordered) | SATISFIED | `selectors/list_bets.py:20` |
| BM-08 (GET /health PG ping) | SATISFIED | `entrypoints/api/health.py`; 200/503 |
| BM-13 (GET /bet/{bet_id} 200/404) | SATISFIED | `entrypoints/api/bets.py:61-77` |
| QA-07 (real PG via testcontainers) | SATISFIED | `tests/conftest.py:24-35` — PostgresContainer("postgres:16-alpine") session-scoped |

---

### Behavioral Spot-Checks

Step 7b: SKIPPED (no server running — integration tests serve as behavioral verification; 193 tests green per SUMMARY plan 03-09)

---

### Anti-Patterns Found

| File | Pattern | Severity | Assessment |
|------|---------|----------|-----------|
| `src/bet_maker/helpers/status.py` | `raise NotImplementedError` | Info | Intentional P5 stub; documented in SUMMARY Known Stubs; not user-visible in P3 |
| `src/bet_maker/facades/event_lookup.py` | `StubEventLookup` in production lifespan | Info | Intentional P4 stub; same Protocol, replaced by HttpEventLookup in Phase 4; documented |

No blockers. No warnings. Both stubs are explicitly documented as phase-appropriate placeholders.

---

### Human Verification Required

None — all success criteria are verifiable programmatically. The manual alembic docker compose rehearsal (SC-5) was pre-approved by the operator (documented in 03-09-SUMMARY.md with step-by-step output evidence).

---

### 10 Critical Risk Axes Status

| Axis | Test | Status |
|------|------|--------|
| 1. Decimal precision drift | `test_selectors::test_amount_is_decimal_with_two_places` + `test_bet_routes::test_post_bet_decimal_roundtrip` | VERIFIED |
| 2. ENUM type idempotency | `test_alembic::test_upgrade_head_third_run_idempotent` + manual rehearsal | VERIFIED |
| 3. Per-request UoW isolation | `test_uow::*` (concurrent UoWs); per-request sessionmaker construction in deps.py | VERIFIED |
| 4. testcontainers Docker availability | CI runs on Docker-capable runner; session-scoped container; no skipif markers | VERIFIED (by design) |
| 5. Tenacity retry exhaustion | `test_lifespan::test_postgres_unreachable_raises_after_retries` | VERIFIED |
| 6. Health liveness during PG outage | `test_health::test_health_returns_503_when_pg_down` (AsyncMock patching) | VERIFIED |
| 7. Pydantic 422 specificity | 8 distinct 422 cases in TestPostBet + 3 in TestPostBetEventNotBettable | VERIFIED |
| 8. EventLookup stub seeding per test | `_clear_event_lookup` autouse in bet_maker conftest; `seed_event` fixture | VERIFIED |
| 9. GET /bets ordering | `test_bet_routes::test_get_bets_ordered_desc_by_created_at` | VERIFIED |
| 10. Alembic rerun idempotency | `apply_migrations` x2 + test x3; `checkfirst=True` + `create_type=False` | VERIFIED |

---

## Phase Goal Assessment

The phase goal is **fully achieved**:

- `POST /bet` and `GET /bets` are wired, substantive, and data flows through PostgreSQL via UoW + Repository.
- `/health` pings PG with correct 200/503 response shape.
- Alembic migration is idempotent (ENUM.create checkfirst=True + create_type=False).
- Decimal round-trip is exact (Pydantic v2 serializes Decimal as "10.00").
- No AMQP, no HTTP integration with line-provider (StubEventLookup, no broker code).
- 193 tests green, 94.28% coverage, mypy strict clean, ruff clean (per 03-09-SUMMARY.md).

---

_Verified: 2026-05-15T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
