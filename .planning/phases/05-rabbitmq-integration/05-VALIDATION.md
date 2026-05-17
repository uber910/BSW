---
phase: 05
slug: rabbitmq-integration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-18
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.1.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"`) |
| **Quick run command** | `uv run pytest tests/bet_maker/test_messaging.py -x -q` |
| **Full suite command** | `uv run pytest -q --cov=src --cov-report=term-missing` |
| **Estimated runtime** | ~60–90 seconds (e2e testcontainers dominates) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/bet_maker/test_messaging.py -x -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green (`uv run pytest -q --cov=src --cov-report=term-missing`)
- **Max feedback latency:** ~5 seconds for the quick command; full suite ≤ 120 seconds.

---

## Per-Task Verification Map

> Planner MUST fill this table during plan generation. Each task row binds a plan task to a requirement, threat reference (if any), expected behaviour, and the automated command that proves it. The planner is allowed to add or refine rows as it splits the plan; this list is initial scaffolding only.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 0 | QA-06 | — | `pika` dev-dep installed and `from testcontainers.rabbitmq import RabbitMqContainer` succeeds | unit (import) | `uv run python -c "from testcontainers.rabbitmq import RabbitMqContainer"` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 0 | QA-06 | — | Session-scoped RabbitMQ + PG testcontainer fixtures available | fixture | `uv run pytest tests/conftest.py --collect-only -q` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | BM-09 | — | `EventFinishedMessage` schema duplicated byte-for-byte in `bet_maker/schemas/messages.py` with `extra="forbid"` | unit | `uv run pytest tests/contract/test_event_finished_message_schema.py -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 1 | BM-10 | — | `BetRepository.get_pending_locked(event_id)` uses `with_for_update(skip_locked=True)` + `status=PENDING` filter | unit + integration | `uv run pytest tests/bet_maker/test_repositories.py -x` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 1 | BM-10 | — | Alembic migration adds `settled_at` + `settled_via` columns, reversible | integration | `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 1 | BM-10 | — | `settle_bets_for_event(event_id, terminal_state, settled_via)` idempotent: second call on same event is no-op | integration (real PG) | `uv run pytest tests/bet_maker/test_settle.py::test_idempotent -x` | ❌ W0 | ⬜ pending |
| 05-04-02 | 04 | 1 | BM-10 | — | Concurrent settle (consumer + reconciler) produces exactly one update | integration (real PG) | `uv run pytest tests/bet_maker/test_settle.py::test_concurrent_no_double_update -x` | ❌ W0 | ⬜ pending |
| 05-05-01 | 05 | 2 | BM-09 | — | Consumer registered with `ack_policy=AckPolicy.MANUAL`, `prefetch_count=10` via `Channel`, topic exchange `bsw.events`, wildcard `event.finished.*` | unit (TestRabbitBroker) | `uv run pytest tests/bet_maker/test_messaging.py::test_subscriber_config -x` | ❌ W0 | ⬜ pending |
| 05-05-02 | 05 | 2 | BM-09 | — | Happy path: `await msg.ack()` only AFTER UoW commit | unit (TestRabbitBroker) | `uv run pytest tests/bet_maker/test_messaging.py::test_happy_path -x` | ❌ W0 | ⬜ pending |
| 05-05-03 | 05 | 2 | BM-11 | — | Poison (ValidationError / DecodeError / schema_version!=1 / IntegrityError) → `reject(requeue=False)` → DLQ | unit (TestRabbitBroker) | `uv run pytest tests/bet_maker/test_messaging.py::TestPoison -x` | ❌ W0 | ⬜ pending |
| 05-05-04 | 05 | 2 | BM-09 | — | Transient (OperationalError / DBAPIError invalidated / TimeoutError) → tenacity retries 3× → ack on recovery | unit (TestRabbitBroker) | `uv run pytest tests/bet_maker/test_messaging.py::TestTransient -x` | ❌ W0 | ⬜ pending |
| 05-05-05 | 05 | 2 | BM-11 | — | Transient retry exhausted → `reject(requeue=False)` → DLQ | unit (TestRabbitBroker) | `uv run pytest tests/bet_maker/test_messaging.py::TestTransient::test_exhausted -x` | ❌ W0 | ⬜ pending |
| 05-06-01 | 06 | 2 | LP-06 | — | `RabbitEventBus.publish(message)` called after store mutation in `set_event_state` interactor | unit | `uv run pytest tests/line_provider/test_interactors.py::test_publishes_on_terminal -x` | ❌ W0 | ⬜ pending |
| 05-06-02 | 06 | 2 | LP-06 | — | `correlation_id` propagated from request → message → broker.publish kwarg | unit | `uv run pytest tests/line_provider/test_event_bus.py -x` | ❌ W0 | ⬜ pending |
| 05-07-01 | 07 | 2 | LP-06, BM-09 | — | Both lifespans: PG ready → httpx singleton → broker.connect → declare topology → yield; reverse-order shutdown | integration (real RMQ+PG via testcontainers) | `uv run pytest tests/bet_maker/test_lifespan.py tests/line_provider/test_lifespan.py -x` | ❌ W0 | ⬜ pending |
| 05-08-01 | 08 | 2 | BM-09 | — | `/health` returns 503 when broker.ping fails OR subscribers==0 OR PG ping fails | integration | `uv run pytest tests/bet_maker/test_health.py -x` | ❌ W0 | ⬜ pending |
| 05-09-01 | 09 | 3 | QA-06 | — | E2E: publish via real RMQ → bet flips WON/LOST in real PG within 1s | e2e (testcontainers) | `uv run pytest tests/bet_maker/test_e2e_rabbitmq.py -x` | ❌ W0 | ⬜ pending |
| 05-10-01 | 10 | 3 | LP-06, BM-09, BM-10, BM-11 | — | REQUIREMENTS.md BM-09 (prefetch 20→10) and BM-11 (x-death header → tenacity in-handler) synced with implementation | docs | `git diff --exit-code .planning/REQUIREMENTS.md` (after planned edit) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — add `pika>=1.3,<2` to `[dependency-groups.dev]` (required by `testcontainers.rabbitmq.RabbitMqContainer.readiness_probe()`)
- [ ] `tests/conftest.py` — add session-scoped `rabbitmq_container` + `amqp_url` fixtures (mirror existing PG testcontainer style from Phase 3)
- [ ] `tests/contract/__init__.py` — new package
- [ ] `tests/contract/test_event_finished_message_schema.py` — stub asserting `EventFinishedMessage.model_json_schema()` byte-identity across services
- [ ] `tests/bet_maker/test_messaging.py` — stubs for all 5 D-30 branches
- [ ] `tests/bet_maker/test_settle.py` — stubs for idempotency + concurrent-settle race
- [ ] `tests/bet_maker/test_e2e_rabbitmq.py` — e2e stub with `RabbitMqContainer("rabbitmq:4.2-management-alpine")`
- [ ] `tests/bet_maker/test_lifespan.py` + `tests/line_provider/test_lifespan.py` — startup ordering smoke tests
- [ ] `tests/bet_maker/test_health.py` — `/health` 503-path stubs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| DLQ population visible in RabbitMQ Management UI | BM-11 | Acceptance per ROADMAP SC#3 is "visible in Management UI"; automated assertion of the AMQP Management HTTP API adds scope without raising confidence beyond the e2e DLQ test | After running `docker compose up` and triggering a poison message (e.g., POST a bet then publish a malformed message), open `http://localhost:15672` (guest/guest), confirm `bet_maker.events.finished.dlq` shows ≥1 ready message |
| Consumer survives forced kill mid-handler (redelivery, no loss) | ROADMAP SC#2 | Requires `docker kill` of the running container, not reproducible inside pytest event loop | Manually start the stack, POST a bet, publish a terminal event, `docker kill bet-maker` during processing, restart, observe in `rabbitmqctl list_queues messages_unacknowledged` that the message is redelivered and settled |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s for full suite
- [ ] `nyquist_compliant: true` set in frontmatter (after planner expands the task map and plan-checker confirms coverage)

**Approval:** pending
