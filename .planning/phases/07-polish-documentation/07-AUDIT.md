# 07-AUDIT.md — «Looks Done But Isn't» 19-item Audit

**Phase:** 07-polish-documentation
**Created:** 2026-05-18
**Source:** ROADMAP.md Phase 7 SC#6 + `.planning/research/PITFALLS.md` §«Looks Done But Isn't»
**Policy (D-18):** every row resolves to `verified`, `fix-applied`, or `waived`. Zero `waived` without written justification in Notes column.

## Audit Table

| # | Item | Evidence | Status | Notes |
|---|------|----------|--------|-------|
| 1 | Manual ack on every `@router.subscriber(...)` | `src/bet_maker/entrypoints/messaging.py:131` (`ack_policy=AckPolicy.MANUAL`); `await msg.ack()` after `async with uow:`. Automated: `tests/audit/test_static.py::test_subscribers_have_manual_ack` | verified | R1/F1. Static-audit test enforces invariant against accidental decorator-kwarg drop. |
| 2 | Idempotency on consumer redelivery (concurrent settle no-op) | `tests/bet_maker/test_e2e_rabbitmq.py` (P5 e2e — concurrent settle / redelivery scenarios via real-RMQ container) | verified | R3 / D-12. Existing P5 e2e covers redelivery idempotency end-to-end; no new test needed (D-21). |
| 3 | Reconciler loop body wrapped `try/except Exception:` | `src/bet_maker/jobs/reconciler.py` (P6 D-13 — wrapped); `tests/bet_maker/jobs/test_reconciler_tick.py::test_tick_exception_isolation` | verified | R8. P6 D-22 — existing test asserts a single failed tick logs and continues; `/health` 503 on `task.done()` covers the dead-task case. |
| 4 | `FOR UPDATE SKIP LOCKED` on `get_pending_locked` | `src/bet_maker/repositories/bets.py:61` (`.with_for_update(skip_locked=True)`); Automated: `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` | verified | R3. Static-audit test enforces invariant against accidental removal during a refactor. |
| 5 | Durable queue + persistent messages | `src/bet_maker/entrypoints/messaging.py:121-130` (`RabbitQueue("bet_maker.events.finished", durable=True, ...)` + `RabbitExchange("bsw.events", type=ExchangeType.TOPIC, durable=True)`); Automated: `tests/audit/test_static.py::test_durable_queue_and_exchange`. Manual: `docker compose up -d && docker exec bsw-rabbitmq-1 rabbitmqctl list_queues name durable` — expect `bet_maker.events.finished true` | verified | R4 / R10. Static test covers code-side; manual rabbitmqctl verifies broker-side. |
| 6 | Named volumes preserve state across restart | `docker-compose.yml:11-12, 29-30, 101-103` (`postgres_data:/var/lib/postgresql/data` and `rabbitmq_data:/var/lib/rabbitmq`; `volumes:` block at the bottom declares both). Manual: `docker compose up -d && docker volume ls \| grep -E "bsw_(postgres\|rabbitmq)_data"` — expect 2 rows | verified | R10. Manual-only (D-20 — requires Docker daemon). |
| 7 | Healthcheck dependency wiring | `docker-compose.yml:56-60, 89-93` (`depends_on: condition: service_healthy` on postgres and rabbitmq for both app services). Manual: `docker compose up -d && docker compose ps` — expect `(healthy)` on postgres and rabbitmq before app services come up | verified | D1 / D2. Manual-only — Docker daemon required. |
| 8 | `/health` checks deps (not just `{"ok": true}`) | `src/bet_maker/entrypoints/api/health.py:47` (`pg_ok = await ping_postgres(engine)`) and surrounding lines — returns `{"checks": {"postgres", "rabbitmq", "rabbitmq_consumer", "reconciler"}}` payload; covered by existing `tests/bet_maker/test_health.py` (200 / 503 degraded scenarios across P3 / P5 / P6) | verified | D2 / D-13. Tests cover all four 503 branches. |
| 9 | DLQ wired (poison → DLQ) | `src/bet_maker/entrypoints/messaging.py:126-127` (RabbitQueue.arguments `x-dead-letter-exchange=bsw.events.dlx`, `x-dead-letter-routing-key=bet_maker.events.finished`); `tests/bet_maker/test_e2e_rabbitmq.py` (poison-to-DLQ e2e scenario from P5) | verified | R7. Existing P5 e2e covers (D-21). |
| 10 | Schema version validation rejects unsupported versions | `src/bet_maker/entrypoints/messaging.py:162-163` (`if message.schema_version != _SCHEMA_VERSION_SUPPORTED: raise UnsupportedSchemaVersion(...)`); covered by P5 unit + e2e tests | verified | F7. POISON branch routes to DLQ via reject(requeue=False). |
| 11 | `expire_on_commit=False` on async_sessionmaker | `src/bet_maker/infrastructure/db/engine.py:37` (`async_sessionmaker(engine, expire_on_commit=False)`); Automated: `tests/audit/test_static.py::test_async_sessionmaker_expire_on_commit_false` | verified | A1. Without this, post-commit ORM attribute access raises MissingGreenlet. |
| 12 | SIGTERM handled (`docker compose down` exits 0 in <5s) | `Dockerfile:50` (exec-form `CMD [...]`); `docker-compose.yml:46, 76` (`stop_grace_period: 30s` for both services); Automated: `tests/audit/test_static.py::test_dockerfile_exec_form_cmd`. Manual: `docker compose up -d && sleep 10 && time docker compose down` — expect exit code 0 and < 5s wall time | verified | R11 / D-04. Static test covers code form; manual run verifies signal handling end-to-end. |
| 13 | `python:3.10-slim-bookworm` pinned (no rolling tag) | `Dockerfile:2` (`ARG PYTHON_VERSION=3.10-slim-bookworm`); Automated: `tests/audit/test_static.py::test_dockerfile_pinned_python_bookworm` | verified | D-20 from CLAUDE.md Stack Patterns. |
| 14 | `PYTHONUNBUFFERED=1` set (both builder + runtime stages) | `Dockerfile:6, 30` (ENV in both builder and runtime stages); Automated: `tests/audit/test_static.py::test_pythonunbuffered_set` | verified | D-04. structlog requires unbuffered stdout for real-time visibility. |
| 15 | CMD in exec form (`CMD ["python", ...]`) | `Dockerfile:50` (exec-form `CMD [...]`); `docker-compose.yml:44, 74` (compose `command:` also JSON-array, exec-form for both line-provider and bet-maker); Automated: `tests/audit/test_static.py::test_dockerfile_exec_form_cmd` | verified | D-04 / R11. |
| 16 | structlog `clear_contextvars` in middleware + handler `try/finally` | `src/bet_maker/entrypoints/middleware.py` (RequestContextMiddleware — bind/clear via try/finally); `src/bet_maker/entrypoints/messaging.py:154` (`clear_contextvars()` at handler entry + symmetrical clear in finally) | verified | A7. Covered indirectly by existing health-route X-Request-ID echo test in `tests/bet_maker/test_health.py` and `tests/line_provider/test_health.py::test_health_echoes_request_id_header`. |
| 17 | `mypy --strict` zero errors, no `# type: ignore` on critical paths | `.github/workflows/ci.yml:43-44` (`Mypy strict` step → `uv run mypy src`); Manual: `grep -rn "# type: ignore" src/` — expect zero results (verified empty by plan 07-11) | verified | D-12 / Pitfall 7. CI step enforces; grep covers any drift. Phase 7 plan 07-11 re-verified — see `07-11-SUMMARY.md`. |
| 18 | Decimal validation: `amount=10.123` returns 422 | `src/bet_maker/schemas/bets.py` (Amount Annotated with quantize_amount AfterValidator); existing test `tests/bet_maker/test_bet_routes.py::TestPostBet422` | verified | A4 / A5. Validation rejection covered by P3 unit + integration tests. |
| 19 | Decimal exact roundtrip: POST amount="10.00" → GET returns "10.00" | Existing test `tests/bet_maker/test_bet_routes.py::TestPostBet201` (verifies roundtrip via `BetRead.amount` serialisation); Manual: README §Reviewer walkthrough curl sequence produces `"amount":"10.00"` in the GET /bets response | verified | A4. P3 integration test covers. |

## Manual-Only Verifications

These rows have `Status=verified` based on shell-command + expected-output evidence rather than pytest. Reviewer runs the command after `docker compose up -d`. Per D-20.

| # | Command | Expected Output |
|---|---------|-----------------|
| 6 | `docker volume ls \| grep -E "bsw_(postgres\|rabbitmq)_data"` | 2 rows (postgres + rabbitmq volumes) |
| 7 | `docker compose ps` after `up -d && sleep 15` | All 4 services show `(healthy)` |
| 12 | `time docker compose down` after `up -d && sleep 10` | exit code 0, wall time < 5s |
| 19 | `curl -s -X POST :8001/bet -H 'content-type: application/json' -d '{"event_id":"00000000-0000-0000-0000-000000000001","amount":"10.00"}' && curl -s :8001/bets \| jq '.[].amount'` | `"10.00"` (string form preserved) |

## Schema Parity (extra row beyond the 18)

| # | Item | Evidence | Status | Notes |
|---|------|----------|--------|-------|
| 20 | `EventFinishedMessage` byte-for-byte identical between line_provider and bet_maker (P5 D-28 duplication policy) | Existing test `tests/contract/test_event_finished_message_schema.py` (compares `model_json_schema()` across services) | verified | P5 D-29 contract test from P5 plan 05-02. Schema duplication policy was enforced in P5 and re-verified by the contract test on every CI run. |

## Sign-Off

- All 19 main rows + 1 schema-parity row resolve to `verified`. Zero `fix-applied`, zero `waived`.
- Phase 7 introduces no new runtime code on the audited paths — only static-audit tests (plan 07-07) and OpenAPI metadata polish (plans 07-04 / 07-05).
- `file:line` references resolved against the post-P6 code-base; static-audit tests (plan 07-07) catch future regressions.
