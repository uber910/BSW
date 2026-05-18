---
phase: 05-rabbitmq-integration
verified: 2026-05-18T08:30:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
---

# Phase 5: RabbitMQ Integration Verification Report

**Phase Goal:** line-provider publishes EventFinishedMessage to RabbitMQ on state change; bet-maker consumes durably with manual ack, settles atomically via FOR UPDATE SKIP LOCKED, and routes poison messages to DLQ. Highest-risk phase (~half of all pitfalls).
**Verified:** 2026-05-18T08:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | PATCH on line-provider transitions event to FINISHED_WIN/FINISHED_LOSE causes all PENDING bets to become WON/LOST within 1s (SC#1) | VERIFIED | `test_consumer_settles_bet_after_lp_transitions_to_finished_win` passes (2 e2e tests green, real RMQ + real PG, 7.37s run) |
| 2 | Consumer survives forced crash mid-handler; redelivery is idempotent (SC#2) | VERIFIED | `AckPolicy.MANUAL` confirmed in `messaging.py:130`; `msg.ack()` only after `async with uow:` exits (`messaging.py:163`); `settle_bets_for_event` idempotent by FOR UPDATE SKIP LOCKED (17 settle tests pass) |
| 3 | Poison message (schema_version=99) rejected with requeue=false lands in DLQ; no redelivery loop (SC#3) | VERIFIED | `test_poison_message_lands_in_dlq` passes against real RMQ; DLX wired in lifespan (`lifespan.py:63-71`); `reject(requeue=False)` in POISON branch (`messaging.py:175`); `nack` absent from handler code (2 grep matches are comments only) |
| 4 | Concurrent consumer + reconciler against same event_id settles exactly once; no double-update, no deadlock (SC#4) | VERIFIED | `TestSettleConcurrent.test_concurrent_settled_via_attribution_is_single_pass` asserts `counts == [0, 3]` against real PG; FOR UPDATE SKIP LOCKED in `repositories/bets.py:44,61` |
| 5 | /health returns 503 if PG ping fails OR RabbitMQ ping fails OR subscriber count == 0 (SC#5) | VERIFIED | `health.py` AND-gates `pg_ok and rmq_ok and subs_ok`; 6 health tests pass (3 503-branch + 3 existing) |
| 6 | EventFinishedMessage schema byte-for-byte identical in both services; both with extra="forbid" (SC#6) | VERIFIED | Contract test `test_schemas_are_identical` passes; `model_json_schema()` equality assertion; `grep -q 'from line_provider' src/bet_maker` returns empty (no cross-service imports) |
| 7 | One real-RabbitMQ e2e test (testcontainers) publishes a message and asserts consumer settled the bet (SC#7) | VERIFIED | `TestE2ERabbitMQ` uses `rabbitmq_container` session fixture (`rabbitmq:4.2-management-alpine`); 2 e2e tests pass with real broker |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/bet_maker/entrypoints/messaging.py` | RabbitRouter + on_event_finished + UnsupportedSchemaVersion | VERIFIED | `router = RabbitRouter(..., default_channel=Channel(prefetch_count=10))`, `ack_policy=AckPolicy.MANUAL`, DLX args, tenacity 3-retry, structlog A7 pattern |
| `src/bet_maker/schemas/messages.py` | EventFinishedMessage byte-for-byte duplicate | VERIFIED | Copied from line_provider; `ConfigDict(frozen=True, extra="forbid")`; no cross-service imports |
| `src/bet_maker/schemas/settle.py` | SettleResult frozen DTO | VERIFIED | `ConfigDict(frozen=True, extra="forbid")`; `settled_via: Literal["consumer", "reconciler"]` |
| `src/bet_maker/messaging/routing.py` | EVENT_FINISHED_WIN/LOSE/WILDCARD Final[str] | VERIFIED | All 3 constants present as `Final[str]` |
| `src/line_provider/messaging/routing.py` | EVENT_FINISHED_WIN/LOSE/WILDCARD Final[str] | VERIFIED | Symmetric with bet_maker; all 3 constants present |
| `src/bet_maker/interactors/settle_bets_for_event.py` | Idempotent settle interactor | VERIFIED | `async with uow:`, `get_pending_locked(event_id)`, `func.now()` for `settled_at`, no broker calls |
| `src/line_provider/facades/event_bus.py` | RabbitEventBus with persist=True + correlation_id propagation | VERIFIED | `persist=True` at line 71; `correlation_id=message.correlation_id` at lines 72, 80; NoopEventBus preserved |
| `src/line_provider/entrypoints/messaging.py` | RabbitRouter singleton (publisher-only) | VERIFIED | `router = RabbitRouter(str(_settings.rabbitmq_url))`; 0 subscribers; no Channel(prefetch) |
| `src/bet_maker/entrypoints/lifespan.py` | Startup order D-21; reverse shutdown | VERIFIED | PG → httpx → `broker.connect()` → declare DLX → declare DLQ → `dlq.bind()` → `set_sessionmaker()` → yield; nested try/finally shutdown |
| `src/line_provider/entrypoints/lifespan.py` | broker.connect → declare bsw.events → RabbitEventBus | VERIFIED | `await rabbit_router.broker.connect()`, `declare_exchange("bsw.events", TOPIC, durable=True)`, `app.state.event_bus = RabbitEventBus(rabbit_router.broker)` |
| `src/bet_maker/app.py` | app.include_router(rabbit_router) | VERIFIED | Line 21: `app.include_router(rabbit_router)` |
| `src/line_provider/app.py` | app.include_router(rabbit_router) | VERIFIED | Line 20: `app.include_router(rabbit_router)` |
| `src/bet_maker/entrypoints/api/health.py` | 3-check AND-gate health | VERIFIED | `broker.ping(timeout=1.0)`, `len(broker.subscribers) > 0`, 503 on any failure |
| `src/bet_maker/facades/deps.py` | RabbitBrokerDep alias | VERIFIED | `get_rabbit_broker` function + `RabbitBrokerDep = Annotated[RabbitBroker, Depends(...)]` |
| `src/bet_maker/repositories/bets.py` | get_pending_locked with FOR UPDATE SKIP LOCKED | VERIFIED | `with_for_update(skip_locked=True)` at line 61; raw SQL fallback at line 44 |
| `src/line_provider/interactors/set_event_state.py` | Uses routing constants (no inline strings) | VERIFIED | `from line_provider.messaging.routing import EVENT_FINISHED_LOSE, EVENT_FINISHED_WIN`; no `"event.finished.win"` literal |
| `tests/contract/test_event_finished_message_schema.py` | model_json_schema equality contract test | VERIFIED | 3 tests pass: `test_schemas_are_identical`, `test_schema_version_field_is_present_with_default_one`, `test_extra_forbid_is_set_on_both` |
| `tests/bet_maker/test_messaging.py` | 7-branch TestRabbitBroker coverage | VERIFIED | 6 test classes (TestSubscriberConfig, TestHappyPath, TestPoison, TestTransient, TestNoop, TestInvariants); all pass |
| `tests/bet_maker/test_settle.py` | Idempotency + concurrent settle tests | VERIFIED | 4 classes (TestSettleHappyPath, TestSettleNoop, TestSettleConcurrent, TestSettleResultShape); 9 tests pass against real PG |
| `tests/bet_maker/test_e2e_rabbitmq.py` | Real RMQ e2e + poison DLQ test | VERIFIED | `TestE2ERabbitMQ` with 2 tests; uses `rabbitmq_container` session fixture (not TestRabbitBroker) |
| `tests/conftest.py` | rabbitmq_container + amqp_url session fixtures | VERIFIED | `RabbitMqContainer("rabbitmq:4.2-management-alpine")` at line 113 |
| `pyproject.toml` | pika>=1.3,<2 dev dep | VERIFIED | Line 33: `"pika>=1.3,<2"` in dependency-groups |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `messaging.py` handler | `settle_bets_for_event` interactor | `_settle_with_retry(uow, ...)` | VERIFIED | `settle_bets_for_event` imported and wrapped by tenacity at module level |
| `messaging.py` router | `messaging/routing.py` | `routing_key=EVENT_FINISHED_WILDCARD` | VERIFIED | Constant imported and used on `RabbitQueue` (not on decorator) |
| `messaging.py` handler | DLQ via x-dead-letter-exchange | `RabbitQueue.arguments` dict | VERIFIED | `"x-dead-letter-exchange": "bsw.events.dlx"` + `"x-dead-letter-routing-key": "bet_maker.events.finished"` |
| `lifespan.py` (bet-maker) | DLX topology | `broker.declare_exchange + broker.declare_queue + dlq.bind` | VERIFIED | All three calls present; `dlq.bind(exchange="bsw.events.dlx", routing_key="bet_maker.events.finished")` |
| `event_bus.py` | `bsw.events` exchange | `broker.publish(..., exchange=RabbitExchange("bsw.events", TOPIC, durable=True), persist=True, correlation_id=...)` | VERIFIED | `persist=True` and `correlation_id=message.correlation_id` at lines 71-72 |
| `set_event_state.py` | `messaging/routing.py` constants | dict `{EventState: EVENT_FINISHED_*}` | VERIFIED | Import at line 16; no inline string literals |
| `lifespan.py` (line-provider) | `RabbitEventBus` via `app.state.event_bus` | `RabbitEventBus(rabbit_router.broker)` | VERIFIED | Line 46: `app.state.event_bus = RabbitEventBus(rabbit_router.broker)` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `on_event_finished` handler | `payload: EventFinishedMessage` | RabbitMQ via FastStream subscriber | Real AMQP messages from line-provider | FLOWING |
| `settle_bets_for_event` | `bets` list | `uow.bets.get_pending_locked(event_id)` → PG FOR UPDATE SKIP LOCKED | Real PG rows | FLOWING |
| `/health` endpoint | `pg_ok, rmq_ok, subs_ok` | `ping_postgres`, `broker.ping`, `broker.subscribers` | Real live checks | FLOWING |
| e2e test | bet status | `GET /bets` poll loop | Real PG row update from consumer | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| nack never appears in handler code | `grep "nack" messaging.py \| grep -v "^.*#\|NEVER\|never\|R7"` | Empty (0 matches outside comments) | PASS |
| prefetch_count=10 set | `grep "prefetch_count=10" messaging.py` | Found at line 115 | PASS |
| AckPolicy.MANUAL set | `grep "ack_policy=AckPolicy.MANUAL" messaging.py` | Found at line 130 | PASS |
| persist=True on publish | `grep "persist=True" event_bus.py` | Found at line 71 | PASS |
| FOR UPDATE SKIP LOCKED in repository | `grep "with_for_update(skip_locked=True)" repositories/bets.py` | Found at line 61 | PASS |
| No cross-service imports | `grep -r "from line_provider" src/bet_maker/` | No production imports (only docstring comments) | PASS |
| Full test suite green | `uv run pytest -q` | **295 passed, 26 warnings in 21.14s** | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| LP-06 | 05-06 | line-provider publishes EventFinishedMessage to RabbitMQ on state change | SATISFIED | `RabbitEventBus` in `event_bus.py`; `persist=True`; `correlation_id` propagated; routing constants from `messaging/routing.py` |
| BM-09 | 05-05, 05-08 | FastStream RabbitRouter consumer; AckPolicy.MANUAL; prefetch_count=10; durable; /health AND-gate | SATISFIED | `Channel(prefetch_count=10)` at `messaging.py:115`; `AckPolicy.MANUAL` at line 130; health 503 on any failure |
| BM-10 | 05-04 | settle_bets_for_event idempotent; FOR UPDATE SKIP LOCKED | SATISFIED | `get_pending_locked` with `with_for_update(skip_locked=True)`; concurrent test proves single-pass attribution |
| BM-11 | 05-05, 05-07 | DLX bsw.events.dlx + DLQ; tenacity 3 retries; poison → reject(requeue=False); nack never used | SATISFIED | DLX/DLQ declared in lifespan; tenacity `stop_after_attempt(3), wait_exponential(multiplier=0.2, min=0.2, max=2)`; all poison paths reject; nack absent from handler |
| QA-06 | 05-05, 05-09 | Consumer tests via TestRabbitBroker + e2e via testcontainers | SATISFIED | `test_messaging.py` (6 classes, TestRabbitBroker); `test_e2e_rabbitmq.py` (2 tests, real RMQ container) |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/bet_maker/entrypoints/lifespan.py` | 90 | `broker.close()` deprecated since FastStream 0.5.44; `stop()` is preferred | Warning | Functional in 0.6.7; will be removed in 0.7.0. No behavioral impact in current version. |
| `src/line_provider/entrypoints/lifespan.py` | 49 | Same `broker.close()` deprecation | Warning | Same as above |

No blockers found. The `broker.close()` API is deprecated but works correctly in FastStream 0.6.7. Migration to `broker.stop()` should be done before upgrading to 0.7.0.

### Human Verification Required

None required — all must-haves were verifiable programmatically. The test suite covers all branches including e2e against real infrastructure.

### Gaps Summary

No gaps. All 7 roadmap success criteria are met, all 5 requirement IDs (LP-06, BM-09, BM-10, BM-11, QA-06) are satisfied, and the full test suite passes (295 tests, 0 failures). The only notable finding is the use of the deprecated `broker.close()` API (deprecated in FastStream 0.5.44, removed in 0.7.0), which functions correctly in the pinned 0.6.7 version.

---

_Verified: 2026-05-18T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
