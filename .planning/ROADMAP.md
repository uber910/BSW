# Roadmap: BSW Betting System

**Created:** 2026-05-13
**Granularity:** standard (7 phases — derived from research, validated against minimum-dependency DAG in ARCHITECTURE.md)
**Mode:** standard (Horizontal Layers)
**Core Value:** Ставка никогда не остаётся в статусе PENDING после того, как её событие завершилось.

## Phases

- [x] **Phase 1: Skeleton + Infrastructure** — Both services boot via `docker compose up` with green CI and healthy deps
- [x] **Phase 2: line-provider domain** — In-memory event store with full HTTP API (no AMQP yet)
- [x] **Phase 3: bet-maker domain (DB)** — PostgreSQL persistence, UoW, place/list bets via HTTP
- [x] **Phase 4: bet-maker HTTP integration with line-provider** — `GET /events` proxy with retry and TTL cache
- [x] **Phase 5: RabbitMQ integration** — Publisher in line-provider, durable consumer + DLQ in bet-maker, atomic settle
- [x] **Phase 6: Reconciliation job** — Background worker recovers stuck PENDING bets via HTTP poll (defence-in-depth)
- [x] **Phase 7: Polish + Documentation** — README, OpenAPI/AsyncAPI quality, e2e/coverage gate, "Looks Done But Isn't" audit

**v1.1 — Architecture cleanup** (post-v1 refactor, no functional change)

- [x] **Phase 8: Flatten entrypoints/ → api/** — Move HTTP routes + FastStream consumer under `src/<svc>/api/`; delete `entrypoints/`
- [ ] **Phase 9: UoW redesign + Repository removal** — Metrikus-style abstract+postgres UoW; selectors absorb reads; interactors use UoW directly; `BetRepository` deleted
- [ ] **Phase 10: Shared-code consolidation** — Lift duplicated cross-service code (structlog wiring, request-id middleware, lifespan helpers, app-factory, engine factory) into a shared package

### Parallelization

Phase 2 and Phase 3 can be developed in parallel after Phase 1 completes (no shared code; both unblocked by skeleton). Critical path is 1 → 2 → 5 → 6 → 7 (covers the Core Value). Phase 3 and Phase 4 are on the critical path of the read side (`GET /bets`, `GET /events`).

## Phase Details

### Phase 1: Skeleton + Infrastructure
**Goal**: Every later phase can assume `docker compose up` produces two healthy services with CI green.
**Depends on**: Nothing (foundation)
**Requirements**: INFR-01, INFR-02, INFR-03, INFR-04, INFR-05, INFR-06, INFR-07, INFR-08, QA-02, QA-03, QA-10
**Success Criteria** (what must be TRUE):
  1. `docker compose up` brings up postgres, rabbitmq, line-provider, bet-maker; `docker compose ps` shows all four containers `(healthy)` within 30s of start
  2. `curl :8000/health` and `curl :8001/health` both return 200 with `{"status":"ok"}` — endpoints exist (deep dep-pings come in P3/P5)
  3. `docker compose down` exits cleanly with code 0 (no SIGKILL/137); logs show graceful shutdown — verifies exec-form CMD + stop_grace_period
  4. `docker compose down && docker compose up` preserves named volumes (`postgres_data`, `rabbitmq_data`); `docker volume ls` shows both
  5. GitHub Actions CI runs ruff (lint + format) + mypy strict + pytest on every push; CI badge in README skeleton turns green
  6. structlog emits JSON logs to stdout (no buffering); `PYTHONUNBUFFERED=1` set; `bind_contextvars` ready for request-id propagation
**Pitfalls this phase prevents**:
  - **R4 / R10**: queue+message durability + named volumes for `/var/lib/rabbitmq` and `/var/lib/postgresql/data`; `hostname: rabbitmq` pinned
  - **R11 / D4**: Dockerfile exec-form CMD (`CMD ["python", "-m", "uvicorn", ...]`), `stop_grace_period: 30s`, `PYTHONUNBUFFERED=1`
  - **D1**: `depends_on: condition: service_healthy` with `start_period` on PG/RMQ healthchecks (avoid initdb race)
  - **D6**: pin `python:3.10-slim-bookworm` (not rolling `-slim` tag)
  - **D8**: services bind `0.0.0.0`, use compose service names (not `localhost`); RabbitMQ management UI bound to `127.0.0.1:15672`
  - **A7**: structlog `contextvars` configured via middleware with `clear_contextvars` in `try/finally`
**Plans:** 7/7 plans executed (Phase 1 complete 2026-05-14)

Plans:
- [x] 01-01-PLAN.md — pyproject.toml + uv.lock + .python-version + .gitignore foundation (Wave 1)
- [x] 01-02-PLAN.md — src/config/ shared internal package (logging, settings_base, time) (Wave 2)
- [x] 01-03-PLAN.md — src/line_provider/ FastAPI skeleton (factory, lifespan, middleware, /health) (Wave 3)
- [x] 01-04-PLAN.md — src/bet_maker/ skeleton + async Alembic env (Wave 3)
- [x] 01-05-PLAN.md — Dockerfile (multi-stage) + docker-compose.yml + .env.example + checkpoint (Wave 4)
- [x] 01-06-PLAN.md — GitHub Actions CI workflow + pre-commit hooks (Wave 4)
- [x] 01-07-PLAN.md — tests/ smoke scaffold + README stub (Wave 4)

### Phase 2: line-provider domain
**Goal**: line-provider exposes a complete HTTP CRUD surface over an in-memory event store, ready to be wired to RabbitMQ in P5.
**Depends on**: Phase 1
**Parallelizable with**: Phase 3 (no shared code)
**Requirements**: LP-01, LP-02, LP-03, LP-04, LP-05, LP-07, LP-08, QA-04, QA-05
**Success Criteria** (what must be TRUE):
  1. `POST/PUT /event` creates or updates an event with valid `coefficient` (Decimal, 2dp, > 0), `deadline` (future), `state` (NEW)
  2. `GET /event/{event_id}` returns 200 with the event or 404 if not found
  3. `GET /events` returns only active events (`deadline > now` AND `state == NEW`)
  4. State machine rejects reverse transitions (FINISHED_WIN → NEW returns 422); only `NEW → FINISHED_WIN | FINISHED_LOSE` is allowed
  5. `GET /health` returns 200 (RabbitMQ ping deferred — line-provider has no AMQP yet; full health upgraded in P5)
  6. Unit tests cover interactors/selectors/helpers; API integration tests via `httpx.AsyncClient(transport=ASGITransport)` cover all four routes
**Pitfalls this phase prevents**:
  - **R9 / R12**: interactor mutates the in-memory store **before** any side-effect; publish ordering enforced in P5 but discipline established here
  - **Anti-Pattern 6** (concurrent dict access): all state mutations guarded by `asyncio.Lock`; pure reads can skip the lock
  - **A7**: line-provider's `/health` and request-id middleware reuse the same `clear_contextvars` pattern as bet-maker
**Plans:** 7/7 plans executed (Phase 2 complete 2026-05-15)

Plans:
- [x] 02-01-PLAN.md — Foundations: asgi-lifespan dev-dep + REQUIREMENTS.md LP-02 sync (UUID4) + conftest LifespanManager + coverage config (Wave 0)
- [x] 02-02-PLAN.md — Schemas: EventState, EventCreate/Update/Read, Event (frozen), EventFinishedMessage, helpers/money.quantize_coefficient (Wave 1)
- [x] 02-03-PLAN.md — Pure state-machine helper (is_transition_allowed, TransitionForbiddenError, ALLOWED_TRANSITIONS) (Wave 2)
- [x] 02-04-PLAN.md — InMemoryEventStore with asyncio.Lock + (new, previous_state) update tuple + concurrent gather tests (Wave 1)
- [x] 02-05-PLAN.md — Facades (EventBus Protocol + NoopEventBus + DI providers) + Interactors (create_event + set_event_state with commit→publish ordering) + FakeEventBus shared fake (Wave 2)
- [x] 02-06-PLAN.md — Selectors (get_event_by_id + list_active_events with monkey-patched utc_now) (Wave 2)
- [x] 02-07-PLAN.md — HTTP routes (4 endpoints) + lifespan wiring + integration tests + phase-gate coverage ≥85% (Wave 3)

### Phase 3: bet-maker domain (DB)
**Goal**: bet-maker persists bets in PostgreSQL through UoW + Repository, exposes `POST /bet` and `GET /bets`, and `/health` pings PG. No AMQP, no HTTP integration with line-provider yet.
**Depends on**: Phase 1
**Parallelizable with**: Phase 2
**Requirements**: BM-01, BM-02, BM-03, BM-05, BM-06, BM-07, BM-08, QA-07
**Success Criteria** (what must be TRUE):
  1. `POST /bet` accepts `{event_id, amount}` with Pydantic validation (`amount > 0`, exactly 2 decimal places) and returns 201 with a fresh bet id; bet is persisted in PG with `status=PENDING`
  2. `POST /bet` rejects with 422 when `amount` has more than 2 dp; rejects with 4xx when the referenced event does not exist, is finished, or `deadline <= now` (validation may stub the event lookup until P4 wires the real client)
  3. `GET /bets` returns the full history with `id, event_id, amount, status, created_at`, ordered by `created_at desc`
  4. `GET /health` returns 200 when PG accepts `SELECT 1`; returns 503 when `docker compose stop postgres`
  5. `alembic upgrade head` (async template) applies the initial migration and creates the `bets` table with `Numeric(12,2)` columns; rerun is idempotent
  6. Decimal round-trip is exact: `POST /bet` with `amount="10.00"` then `GET /bets` returns `"10.00"` (string form, two decimals preserved)
**Pitfalls this phase prevents**:
  - **A1**: `async_sessionmaker(engine, expire_on_commit=False)`; selectors return Pydantic DTOs via `model_validate(from_attributes=True)`, never raw ORM
  - **A2**: one `AsyncSession` per UoW per business operation; sessions never shared across tasks; sessionmaker is the only module-level singleton
  - **A3**: explicit `pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800`
  - **A4 / A5**: `Mapped[Decimal] = mapped_column(Numeric(12, 2))`; Pydantic `condecimal(gt=0, decimal_places=2)`; `helpers/money.py` quantizes to `Decimal("0.01")`
  - **A6**: `alembic init -t async`; `env.py` reads DSN from `BetMakerSettings`, no hardcoded `sqlalchemy.url`
  - **Anti-Pattern 1**: repositories `flush()`, only UoW commits
  - **D2**: `/health` lifespan pings PG with `tenacity` retry — must surface bad DSN at startup, not at first request
**Plans:** 9/9 plans executed (Phase 3 complete 2026-05-15)

Plans:
- [x] 03-01-PLAN.md — REQUIREMENTS.md sync (BM-01/BM-05 remove coefficient, BM-13 added) per D-01/D-02 (Wave 0)
- [x] 03-02-PLAN.md — Test scaffolding (testcontainers PG fixtures + 10 stubs + pyproject coverage) (Wave 0)
- [x] 03-03-PLAN.md — Schemas + helpers (BetCreate, BetRead, BetStatus, EventState duplicate, quantize_amount, status stub) (Wave 1)
- [x] 03-04-PLAN.md — Bet ORM + alembic env.py target_metadata + 0001_bets_initial migration (idempotent ENUM) (Wave 1)
- [x] 03-05-PLAN.md — DB Infrastructure (engine + pings tenacity wait_for_postgres + ping_postgres) (Wave 3)
- [x] 03-06-PLAN.md — Facades & Repositories (UoW + BetRepository + EventLookup Protocol + Stub + deps Annotated aliases) (Wave 3)
- [x] 03-07-PLAN.md — Interactor place_bet (3-branch EventNotBettable) + selectors list_bets/get_bet (Wave 4)
- [x] 03-08-PLAN.md — HTTP routes (POST /bet 201/422, GET /bets, GET /bet/{id}) + lifespan extension + /health PG ping + 14+ integration tests (Wave 5)
- [x] 03-09-PLAN.md — Phase-gate (coverage ≥80%, manual alembic rehearsal, docs sync) (Wave 6)

### Phase 4: bet-maker HTTP integration with line-provider
**Goal**: bet-maker exposes `GET /events` by proxying line-provider via `httpx.AsyncClient` with retry (tenacity), and establishes the HTTP client that reconciliation will reuse in P6. Per D-01 (Phase 4 CONTEXT.md): TTL cache не реализуется — ТЗ кэш не требует.
**Depends on**: Phase 2 (needs line-provider `GET /events/{id}` + `GET /events`), Phase 3 (uses same lifespan + Depends graph)
**Requirements**: BM-04
**Success Criteria** (what must be TRUE):
  1. bet-maker's `GET /events` returns the same active-events payload that `line-provider` exposes, with acceptable lag (свежий результат каждого запроса; отставание = длительность одного HTTP-вызова к LP плюс retry-backoff). Per D-01 (Phase 4 CONTEXT.md): TTL cache не реализуется в P4.
  2. `tenacity` retries transient httpx failures (timeout, 5xx) with exponential backoff; permanent failures (404, 422) propagate
  3. The httpx client is a singleton constructed in lifespan and closed on shutdown — no per-request client construction
  4. Integration test drives both apps via `httpx.AsyncClient(transport=ASGITransport)` without docker, asserting end-to-end proxy behaviour
  5. `POST /bet` validation (BM-06) now uses the real `line_provider_client` to resolve and validate the event (deadline + state)
**Pitfalls this phase prevents**:
  - Stale `httpx.AsyncClient` connections / event-loop sharing in tests (fixture scope must match)
  - **Integration Gotcha**: `httpx.AsyncClient(base_url=str(settings.line_provider_base_url), timeout=httpx.Timeout(5.0))` — never default infinite timeout
**Plans:** 9 plans across 6 waves

Plans:
- [x] 04-01-PLAN.md — Doc-sync (REQUIREMENTS BM-04 + ROADMAP Phase 4 Goal/SC#1) + respx dev-dep (Wave 1)
- [x] 04-02-PLAN.md — EventRead schema in bet_maker/schemas/events.py + TestEventRead (Wave 2)
- [x] 04-03-PLAN.md — BetMakerSettings two new fields (line_provider_http_attempts, line_provider_http_backoff_max_s) + test_settings.py (Wave 2)
- [x] 04-04-PLAN.md — facades/line_provider_client.py (LineProviderUnavailable + make_retry_decorator factory) + tests (Wave 3)
- [x] 04-05-PLAN.md — facades/http_event_lookup.py (HttpEventLookup implements EventLookup Protocol) + respx unit tests (Wave 4)
- [x] 04-06-PLAN.md — selectors/list_active_events.py + respx unit tests (Wave 4)
- [x] 04-07-PLAN.md — Lifecycle wiring: deps.py provider + lifespan.py singleton AsyncClient + conftest _clear_event_lookup rework + test_lifespan (Wave 5)
- [x] 04-08-PLAN.md — GET /events route + app.py wiring + integration test (two FastAPI apps via ASGITransport) (Wave 6)
- [x] 04-09-PLAN.md — POST /bet 503 path (LineProviderUnavailable → 503) + TestPostBet503 (Wave 6)

### Phase 5: RabbitMQ integration
**Goal**: line-provider publishes `EventFinishedMessage` to RabbitMQ on state change; bet-maker consumes durably with manual ack, settles atomically via `FOR UPDATE SKIP LOCKED`, and routes poison messages to DLQ. Highest-risk phase (~half of all pitfalls).
**Depends on**: Phase 2 (publisher lives inside `interactors/set_event_state.py`), Phase 3 (consumer reuses UoW + `BetRepository.get_pending_locked`)
**Requirements**: LP-06, BM-09, BM-10, BM-11, QA-06
**Success Criteria** (what must be TRUE):
  1. PATCH on line-provider that transitions an event to FINISHED_WIN/FINISHED_LOSE causes all PENDING bets on that event to become WON/LOST within 1s, observable via `GET /bets`
  2. Consumer survives a forced crash mid-handler — the message is **redelivered** (not lost): `rabbitmqctl list_queues messages_unacknowledged` ≥ 1 during processing; re-processing is idempotent (no duplicate settle)
  3. A poison message (`schema_version=99` or malformed body) is rejected with `requeue=false` and lands in `bet_maker.events.finished.dlq` (visible in Management UI); the queue does not enter a redelivery loop
  4. Concurrent consumer + reconciler against the same `event_id` results in exactly one settle pass; no double-update, no deadlock — verified by a test that runs both against a real PG
  5. `/health` upgraded: returns 503 if PG ping fails OR RabbitMQ ping fails OR subscriber count == 0
  6. `EventFinishedMessage` (`schema_version, event_id, new_state, coefficient, occurred_at, correlation_id`) is identical byte-for-byte in `line_provider/schemas/messages.py` and `bet_maker/schemas/messages.py`, both with `extra="forbid"`
  7. One real-RabbitMQ e2e test (testcontainers) publishes a message and asserts the consumer settled the bet; complements the `TestRabbitBroker` unit tests
**Pitfalls this phase prevents**:
  - **R1 / F1**: explicit `ack_policy=AckPolicy.MANUAL` on every `@router.subscriber(...)`; never the default `REJECT_ON_ERROR`
  - **R2 / F4**: `await msg.ack()` **after** `async with uow:` exits successfully; `nack(requeue=True)` on transient errors; `reject(requeue=False)` after bounded retries
  - **R3**: `BetRepository.get_pending_locked()` uses `with_for_update(skip_locked=True)` + `WHERE status='PENDING'` filter → consumer/reconciler race is provably no-op on second pass
  - **R5**: exchange/queue arguments dict is pinned in one module and treated as immutable — rename, never edit
  - **R7**: distinguish poison (`ValidationError` → `reject(requeue=False)`) from transient (`OperationalError` → `nack(requeue=True)`); never unbounded requeue
  - **R9 / R12 / Anti-Pattern 2**: line-provider's `interactors/set_event_state.py` mutates the in-memory store **before** publishing; never publish from inside a lock or DB transaction
  - **F2**: `prefetch_count=10` on the broker — never default unlimited
  - **F3**: custom lifespan controls startup order (DB ready → httpx ready → broker starts subscribing → worker starts)
  - **F5 / Anti-Pattern 5**: one `RabbitBroker` per service; publishers reuse `router.broker.publish()` through an `EventBus` facade
  - **F6**: at least one e2e test against a real RabbitMQ container (testcontainers) — `TestRabbitBroker` alone misses topology bugs
  - **F7**: `schema_version` field + `ConfigDict(extra="forbid")`; consumer rejects unsupported versions to DLQ
  - **F8**: routing key constants single-sourced; mandatory binding asserted in integration test
  - **A7**: consumer handler `clear_contextvars()` at top, binds `event_id/correlation_id/message_id`, clears in `finally`
**Plans:** 10 plans across 4 waves

Plans:
- [x] 05-01-wave0-test-scaffolding-PLAN.md — pyproject pika dev-dep + conftest RMQ fixtures + 7 stub test files (Wave 0)
- [x] 05-02-schema-duplication-routing-PLAN.md — EventFinishedMessage duplicate + SettleResult DTO + messaging/routing.py constants + contract test (Wave 1)
- [x] 05-03-repository-orm-migration-PLAN.md — Bet ORM settled_at/settled_via + Alembic 0002 + BetRepository.get_pending_locked (Wave 1)
- [x] 05-04-settle-interactor-PLAN.md — settle_bets_for_event idempotent interactor + idempotency/concurrent settle tests (Wave 1)
- [x] 05-05-messaging-entrypoint-PLAN.md — RabbitRouter + on_event_finished handler + RabbitBrokerDep + 7-branch TestRabbitBroker (Wave 2)
- [x] 05-06-rabbit-event-bus-PLAN.md — RabbitEventBus + line-provider messaging.py + set_event_state rewire (Wave 2)
- [x] 05-07-lifespan-composition-PLAN.md — bet-maker + line-provider lifespan broker layer + topology declare + app.include_router (Wave 2)
- [x] 05-08-health-upgrade-PLAN.md — /health 503 on PG/RMQ/subscribers (Wave 2)
- [x] 05-09-e2e-rabbitmq-PLAN.md — real-RMQ + real-PG e2e (consumer settle + poison-to-DLQ) (Wave 3)
- [x] 05-10-requirements-doc-sync-PLAN.md — REQUIREMENTS.md BM-09/BM-11 sync with implementation (Wave 3)

### Phase 6: Reconciliation job
**Goal**: A bet **never** stays PENDING after its event has finished, even if the AMQP message was lost. An asyncio background task polls line-provider for terminal-state events and settles via the same `settle_bets_for_event` interactor as the consumer, or marks the bets `CANCELLED` via a new `cancel_bets_for_event` interactor when line-provider returns 404 (event deleted / LP recreated).
**Depends on**: Phase 4 (httpx client to line-provider), Phase 5 (settle interactor + UoW)
**Requirements**: BM-12, QA-08
**Success Criteria** (what must be TRUE):
  1. If a state-change message is dropped between line-provider and bet-maker (verified by skipping the publish in a test), the reconciliation worker settles affected PENDING bets within `RECONCILIATION_INTERVAL_S` (default 30s, configurable via pydantic-settings) to `WON` / `LOST` when LP reports `FINISHED_WIN` / `FINISHED_LOSE`, or to `CANCELLED` when LP returns 404 for the event_id
  2. The worker survives transient errors: a single failed tick (httpx timeout, PG blip) logs an exception and continues; the loop never exits silently
  3. `/health` returns 503 if the reconciliation task is `done()` or has an exception — observable failure, not invisible
  4. Reconciler + consumer running concurrently against the same `event_id` produce exactly one settled status per affected bet (verified by integration test with `FOR UPDATE SKIP LOCKED`)
  5. End-to-end test scenarios: (a) create event → place bet → finish event → assert bet is WON via consumer; (b) create event → place bet → drop publish → finish event → assert bet is WON via reconciler within one interval; (c) create event → place bet → delete event from line-provider → assert bet becomes CANCELLED via reconciler within one interval
**Pitfalls this phase prevents**:
  - **R8**: loop body wrapped in `try/except Exception:` (not `BaseException`); task named `"reconciliation"`; `/health` asserts `task.done() is False`
  - **R3 (re-verified end-to-end)**: integration test runs consumer + reconciler concurrently and asserts no double-update
  - **R9**: reconciler trusts monotonic terminal state from line-provider — no "wait N seconds" debounce; immediate settle on observed FINISHED state
  - **Integration Gotcha (reconciler vs HTTP order)**: reconciler queries `GET /events/{id}` only AFTER line-provider's in-memory commit (ordering enforced in P2/P5)
**Plans:** 11/11 plans complete

Plans:
- [x] 06-01-doc-sync-PLAN.md — REQUIREMENTS BM-05/BM-12 + ROADMAP Phase 6 Goal/SC sync (CANCELLED branch) (Wave 0)
- [x] 06-02-test-scaffolding-PLAN.md — 11 stub test files + conftest extensions (reconciler fixtures) (Wave 0)
- [x] 06-03-cancelled-status-migration-PLAN.md — BetStatus.CANCELLED enum + Alembic 0003 autocommit_block ALTER TYPE (Wave 1)
- [x] 06-04-reconciler-settings-PLAN.md — BetMakerSettings.line_provider_reconciler_attempts + _backoff_max_s (Wave 1)
- [x] 06-05-get-pending-event-ids-PLAN.md — BetRepository.get_pending_event_ids() DISTINCT PENDING query (Wave 1)
- [x] 06-06-cancel-interactor-PLAN.md — cancel_bets_for_event interactor + CancelResult DTO + unit tests (Wave 2)
- [x] 06-07-reconciler-job-PLAN.md — jobs/reconciler.py loop + _run_tick + unit tests (Wave 2)
- [x] 06-08-lifespan-health-wiring-PLAN.md — lifespan reconciler_event_lookup + create_task + /health 4th check (Wave 3)
- [x] 06-09-integration-tests-PLAN.md — respx drop-publish + reconciler/consumer concurrent race tests (Wave 4)
- [x] 06-10-e2e-drop-publish-PLAN.md — real-RMQ + real-PG e2e drop-publish (SC#5 / QA-08) (Wave 5)
- [x] 06-11-phase-gate-PLAN.md — coverage ≥80%, REQUIREMENTS/ROADMAP sync verify, plan checkboxes (Wave 6)

### Phase 7: Polish + Documentation
**Goal**: A reviewer can clone the repo, run `docker compose up`, hit the documented curl commands, and pass the "Looks Done But Isn't" 18-item checklist from PITFALLS.md.
**Depends on**: Phases 1–6
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04, QA-01, QA-09
**Success Criteria** (what must be TRUE):
  1. README explains what the system does, includes an ASCII architecture diagram, and gives a copy-pasteable `docker compose up` + curl sequence (create event → place bet → finish event → list bets) that a reviewer can execute in under 5 minutes
  2. README has dedicated sections: **Architecture** (layers, UoW, RabbitMQ topology, link to ARCHITECTURE.md), **Development** (uv install, migrations, tests, linters), **Reliability** (durable queue + manual ack + DLQ + reconciler + FOR UPDATE SKIP LOCKED + Core Value)
  3. `mypy --strict` passes with zero errors across both packages (`src/line_provider/` and `src/bet_maker/`), enforced in CI; no `# type: ignore` on UoW, repositories, or consumer handler signatures
  4. `pytest-cov` shows ≥80% line coverage across both packages, enforced as a CI threshold; coverage badge in README
  5. OpenAPI tags/summaries/`response_model`/examples are filled in for both services' routes; FastStream AsyncAPI docs at `/asyncapi` describe the AMQP contract
  6. Every item in the PITFALLS.md "Looks Done But Isn't" 18-item checklist is verified (manual ack, idempotency, reconciler exception guard, FOR UPDATE SKIP LOCKED, durable queue + volumes, healthcheck depths, DLQ wired, schema version checked, expire_on_commit=False, SIGTERM clean exit, bookworm pin, PYTHONUNBUFFERED, exec-form CMD, structlog clear_contextvars, mypy strict, Decimal 422 on bad input, Decimal exact roundtrip)
**Pitfalls this phase prevents**:
  - **Visibility gap**: every fix from P1–P6 only counts if a 15-minute reviewer can see it; README + curl examples + AsyncAPI + CI badge close this gap
  - **R6 (final)**: subscriber-count check in `/health` documented and re-verified
  - **R11 (final)**: capture `docker compose down` logs in README/CI to prove SIGTERM cleanly drains the consumer
**Plans:** 12/12 plans complete

Plans:
**Wave 1**
- [x] 07-01-sync-task-PLAN.md — REQUIREMENTS/ROADMAP/README vs ТЗ PDF drift verification (Wave 0)
- [x] 07-02-error-detail-schemas-PLAN.md — ErrorDetail Pydantic schemas + parity tests on both services (Wave 1)
- [x] 07-03-openapi-app-metadata-PLAN.md — FastAPI description= on both app factories (Wave 1)
- [x] 07-06-ci-coverage-gate-PLAN.md — CI Pytest step --cov --cov-fail-under=85 (Wave 1)
- [x] 07-07-audit-static-tests-PLAN.md — tests/audit/test_static.py with 7 regex audit tests (Wave 1)
- [x] 07-08-asyncapi-smoke-tests-PLAN.md — /asyncapi smoke tests on both services (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 07-04-openapi-route-polish-line-provider-PLAN.md — line-provider routes summary/responses/Body(openapi_examples) (Wave 2)
- [x] 07-05-openapi-route-polish-bet-maker-PLAN.md — bet-maker routes summary/responses/Body(openapi_examples) (Wave 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 07-09-audit-md-PLAN.md — 07-AUDIT.md 19-row evidence table (Wave 3)
- [x] 07-11-mypy-strict-verification-PLAN.md — mypy strict + # type: ignore audit (Wave 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 07-10-readme-final-PLAN.md — README final pass (Architecture + Reliability + Reviewer walkthrough + 7/7 status) (Wave 4)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 07-12-phase-gate-PLAN.md — full quality gate + planning ledger update (Wave 5)

### Phase 8: Flatten entrypoints/ → api/
**Goal**: HTTP routers and the FastStream RabbitMQ router live in `src/<svc>/api/` for both services; the `entrypoints/` package is gone. Treat Rabbit as just another transport-layer API.
**Depends on**: Phase 7 (closes v1.0 baseline)
**Milestone**: v1.1
**Requirements**: REFACTOR-01, REFACTOR-05
**Success Criteria** (what must be TRUE):
  1. `src/bet_maker/entrypoints/` and `src/line_provider/entrypoints/` do not exist (the directories are deleted, not just emptied); `find src -type d -name entrypoints` returns nothing.
  2. `src/bet_maker/api/` and `src/line_provider/api/` contain all HTTP route modules (`bets.py`, `events.py`, `health.py`) AND the FastStream `messaging.py` consumer (bet_maker only) plus their `__init__.py` exporting routers; route imports across the codebase (`from <svc>.api.X import router`) resolve without legacy `entrypoints` references.
  3. `lifespan.py` and `middleware.py` are relocated to a stable location agreed during discuss-phase (likely `src/<svc>/app/` or kept at `src/<svc>/` root next to `app.py`) and `app.py` wires them from the new location without dead imports.
  4. v1.0 test suite stays green (355+ tests, no skips/xfails added); `mypy --strict src` reports zero errors; `ruff check src tests` clean; coverage gate ≥85% still holds (REFACTOR-05).
  5. `tests/audit/test_static.py` and any other static audit referencing `entrypoints/` paths are updated in lockstep so the audit fails on regressions, not on the new layout.
**Pitfalls this phase prevents**:
  - **Stale import paths**: `git grep -E 'from (bet_maker|line_provider)\.entrypoints'` must return 0 hits after the move.
  - **Hidden Alembic / Dockerfile / docker-compose path leaks**: `command: ["python","-m","<svc>"]` already abstracts the entry; verify Dockerfile + alembic env.py + CI workflow do not hardcode `entrypoints/`.
  - **RabbitRouter wiring drift**: `app.include_router(messaging_router)` lives in `app.py` exactly as before — only the import path changes; AsyncAPI docs at `/asyncapi` still resolve.
**Plans:** 3/3 plans executed (Phase 8 complete 2026-05-18)

Plans:
- [x] 08-01-PLAN.md — bet_maker entrypoints/ → api/ + lifespan + middleware relocate + tests/audit sync + tests/bet_maker/test_e2e_rabbitmq.py line 131 (Wave 1)
- [x] 08-02-PLAN.md — line_provider entrypoints/ → api/ + lifespan + middleware relocate + cross-service test sync + test_e2e_rabbitmq.py line 113 + audit test expansion (Wave 2)
- [x] 08-03-PLAN.md — full quality gate + ROADMAP + REQUIREMENTS.md BM-03 closeout (Wave 3)

### Phase 9: UoW redesign + Repository removal
**Goal**: `AsyncUnitOfWork` becomes an abstract contract + concrete Postgres implementation modeled on `~/Interexy/Metrikus/metrikus-app/api_common/unit_of_work/`; interactors take `uow: AsyncUnitOfWork` as a DI parameter and access the session only through `uow.session`. The `repositories/` layer is removed entirely — reads move into `selectors/` (thin SQL/in-memory wrappers, no commit/flush) and writes move into `interactors/` directly.
**Depends on**: Phase 8 (cleaner layout makes the move-targets stable)
**Milestone**: v1.1
**Requirements**: REFACTOR-02, REFACTOR-03, REFACTOR-05
**Success Criteria** (what must be TRUE):
  1. `src/bet_maker/facades/uow.py` (or `src/bet_maker/uow/`) exports `AbstractUnitOfWork` (ABC or Protocol — locked in discuss-phase) AND a concrete `PostgresUnitOfWork`; the abstract type is what interactors and tests depend on (`uow: AbstractUnitOfWork`), the concrete is what the FastAPI `Depends` provider returns.
  2. `async with uow:` manages a single transaction; `uow.session` is the only session handle interactors touch; no interactor opens an `AsyncSession` directly and no module-level sessionmaker leaks into interactor signatures. `git grep -E 'async_sessionmaker|AsyncSession' src/bet_maker/interactors src/bet_maker/selectors` returns zero hits.
  3. `src/bet_maker/repositories/` does not exist; `git grep 'class BetRepository'` returns zero hits across `src/` and `tests/`. `BetRepository.add` is absorbed by the relevant write interactors (`place_bet`, `settle_bets_for_event`, `cancel_bets_for_event`); `BetRepository.get_*` methods migrate to `selectors/` (e.g. `selectors/get_pending_locked.py`, `selectors/get_pending_event_ids.py`).
  4. `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` is either deleted or replaced by an equivalent interactor-level audit (e.g. asserting `with_for_update(skip_locked=True)` lives in `selectors/get_pending_locked.py`); the static audit remains a regression net, just at the new seam.
  5. v1.0 behavioural surface unchanged: 355+ tests stay green, mypy strict clean, ruff clean, coverage ≥85% (REFACTOR-05); `POST /bet` / `GET /bets` / consumer / reconciler all produce byte-identical responses on the e2e fixture.
**Pitfalls this phase prevents**:
  - **Intermediate half-broken state**: doing UoW redesign and Repository removal in one phase avoids the otherwise-mandatory "old UoW + new selectors" hybrid that breaks on every test run.
  - **Hidden session leaks**: `AbstractUnitOfWork.session` is the only public knob; tests cannot accidentally bypass it because `BetRepository` no longer exists.
  - **FOR UPDATE SKIP LOCKED regression**: must explicitly carry the `with_for_update(skip_locked=True)` invariant from `BetRepository.get_pending_locked` into its new home in `selectors/` and keep the static-audit hook (or the equivalent integration test) pointing at the new file.
  - **DI contract drift**: every interactor signature changes from positional `repo`/`session` arg to `uow: AbstractUnitOfWork`; route layer's `Annotated[AbstractUnitOfWork, Depends(get_uow)]` is the single seam to update.
**Plans:** 3 plans across 3 waves

Plans:
- [x] 09-01-PLAN.md — Create selectors/get_pending_locked + get_pending_event_ids + retarget audit (Wave 1)
- [ ] 09-02-PLAN.md — Introduce uow/ package (Abstract+Postgres), rewire interactors/messaging/reconciler + all consumer tests, delete facades/uow.py (Wave 2)
- [ ] 09-03-PLAN.md — Delete src/bet_maker/repositories/ + tests/bet_maker/test_repositories.py + phase gate (Wave 3)

### Phase 10: Shared-code consolidation
**Goal**: Cross-service near-duplicates (structlog wiring, request-id middleware with the A7 double-clear pattern, FastAPI app-factory boilerplate, lifespan helpers, SQLAlchemy async engine/sessionmaker factory, AMQP message schemas) live in a single shared package that both `bet_maker` and `line_provider` import; no copy-paste twin files remain. Exact list of consolidation targets is locked in discuss-phase.
**Depends on**: Phase 9 (interactor/selector/UoW shape settled — shared boundaries don't keep moving)
**Milestone**: v1.1
**Requirements**: REFACTOR-04, REFACTOR-05
**Success Criteria** (what must be TRUE):
  1. A shared package (likely `src/shared/` or an extension of the existing `src/config/`; final name fixed in discuss-phase) exposes: `configure_structlog`, `RequestContextMiddleware`, app-factory helper, lifespan helpers (e.g. `make_postgres_lifespan_layer`), `create_engine_and_sessionmaker`, and the cross-service AMQP schema (`EventFinishedMessage`) as a single source of truth — no longer duplicated under `bet_maker/schemas/messages.py` and `line_provider/schemas/messages.py`.
  2. `diff src/bet_maker/<file> src/line_provider/<file>` for any candidate file identified in discuss-phase either returns empty (both import from shared) or returns only intentional service-specific lines (documented in discuss CONTEXT.md).
  3. Both services boot identically via `docker compose up`; `/health` on both still returns 200; `GET /events` proxy through bet-maker → line-provider still works; reconciler + consumer still settle bets — all v1.0 e2e tests stay green (REFACTOR-05).
  4. `mypy --strict` continues to pass with the new package included (`packages = ["src/bet_maker", "src/line_provider", "src/shared"]` in pyproject `[tool.hatch.build.targets.wheel]`); no new `# type: ignore` or `# noqa` over the v1.0 baseline (REFACTOR-05).
  5. Coverage gate ≥85% holds across all three packages combined; new shared modules either inherit coverage from existing tests or get dedicated thin unit tests (no shared module ships uncovered).
**Pitfalls this phase prevents**:
  - **Service-coupling regression**: shared package must not import from `bet_maker` or `line_provider` (one-way dep); enforce via a static audit test in `tests/audit/test_static.py` (`from bet_maker` / `from line_provider` inside `src/shared/` returns 0 hits).
  - **AMQP schema drift**: a single `EventFinishedMessage` class is the single source of truth; v1.0 contract test that compared the two duplicate schemas byte-for-byte is replaced by a simpler assertion that both services import the same class object.
  - **Hatch / pyproject packaging miss**: `pyproject.toml` `[tool.hatch.build.targets.wheel] packages` list must include the new shared dir, otherwise editable install fails silently for the shared package.
  - **Late discovery of incompatible duplication**: discuss-phase locks the list of consolidation candidates BEFORE coding, so the phase doesn't snowball into a service-rewrite.
**Plans:** TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Skeleton + Infrastructure | 7/7 | Complete | 2026-05-14 |
| 2. line-provider domain | 7/7 | Complete | 2026-05-15 |
| 3. bet-maker domain (DB) | 9/9 | Complete | 2026-05-15 |
| 4. bet-maker HTTP integration with line-provider | 9/9 | Complete | 2026-05-17 |
| 5. RabbitMQ integration | 10/10 | Complete | 2026-05-18 |
| 6. Reconciliation job | 11/11 | Complete   | 2026-05-18 |
| 7. Polish + Documentation | 12/12 | Complete   | 2026-05-18 |
| 8. Flatten entrypoints/ → api/ | 3/3 | Complete | 2026-05-18 |
| 9. UoW redesign + Repository removal | 0/3 | Planning complete | - |
| 10. Shared-code consolidation | 0/? | Not started | - |

---
*Roadmap created: 2026-05-13 from REQUIREMENTS.md + ARCHITECTURE.md*
*Coverage: 42/42 v1 requirements mapped (no orphans); v1.1 +5/+5 (REFACTOR-01..05) → 10 phases total*
*Milestone v1.1 phases appended: 2026-05-18 (Phases 8-10, architecture cleanup, no functional change; behavioural invariants enforced via REFACTOR-05 in every phase)*
*Phase 1 plans created: 2026-05-13 (7 plans across 4 waves)*
*Phase 3 plans created: 2026-05-15 (9 plans across 6 waves)*
