---
phase: 07-polish-documentation
plan: 09
type: execute
wave: 3
depends_on: [02, 03, 04, 05, 06, 07, 08]
files_modified:
  - .planning/phases/07-polish-documentation/07-AUDIT.md
autonomous: true
requirements: [DOC-04]
must_haves:
  truths:
    - "07-AUDIT.md exists in phase directory"
    - "Audit table has 19 rows: 18 \"Looks Done But Isn't\" items + 1 schema-parity reference"
    - "Each row has all 4 columns filled: Item | Evidence | Status | Notes"
    - "Status is one of: verified | fix-applied | waived"
    - "Zero rows have Status=waived without written justification in Notes"
    - "Evidence column references concrete file:line, pytest node-id, or shell command + expected output"
    - "Manual-only rows record exact shell command + expected output (docker compose down exit 0, docker volume ls, Decimal roundtrip, Decimal 422)"
  artifacts:
    - path: ".planning/phases/07-polish-documentation/07-AUDIT.md"
      provides: "Codified 18-item audit table mapping each PITFALLS.md «Looks Done But Isn't» bullet to Evidence + Status"
      min_lines: 50
      contains: "verified"
  key_links:
    - from: ".planning/phases/07-polish-documentation/07-AUDIT.md"
      to: ".planning/research/PITFALLS.md §«Looks Done But Isn't»"
      via: "Each row mirrors one bullet from the source checklist"
      pattern: "\\| (Manual ack|Idempotency|Reconciler|FOR UPDATE)"
    - from: ".planning/phases/07-polish-documentation/07-AUDIT.md"
      to: "tests/audit/test_static.py / tests/bet_maker/test_e2e_rabbitmq.py / tests/bet_maker/jobs/test_reconciler_tick.py / tests/bet_maker/test_bet_routes.py"
      via: "Evidence column cites pytest node IDs and file:line references"
      pattern: "tests/audit/test_static\\.py::test_"
---

<objective>
Create `07-AUDIT.md` codifying the 19-row audit table per CONTEXT.md D-18 + RESEARCH.md 18-item evidence map. Each row maps one «Looks Done But Isn't» item to:
1. Item — concise human-readable description
2. Evidence — concrete `file:line`, pytest node-id, or shell command + expected output
3. Status — `verified` (no edit), `fix-applied` (corrected in P7), or `waived` (with written justification — should be zero or near-zero rows)
4. Notes — context, especially for manual-only items

All 19 rows must resolve to `verified` per the evidence map (every item is already in place from P1-P6). Zero `waived` without justification.

Output: 1 markdown file. No code changes. AUDIT.md is the documented reference for plan 07-12 phase-gate to verify completeness.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/research/PITFALLS.md
@.planning/phases/07-polish-documentation/07-CONTEXT.md
@.planning/phases/07-polish-documentation/07-RESEARCH.md
@.planning/phases/07-polish-documentation/07-PATTERNS.md
@.planning/phases/07-polish-documentation/07-07-SUMMARY.md
@.planning/phases/07-polish-documentation/07-08-SUMMARY.md
</context>

<threat_model>
N/A — documentation artefact. AUDIT.md records existing evidence; introduces no code or attack surface.
</threat_model>

<tasks>

<task type="auto">
  <name>Task 1: Author 07-AUDIT.md with 19-row evidence table</name>
  <files>.planning/phases/07-polish-documentation/07-AUDIT.md</files>
  <read_first>
    - .planning/research/PITFALLS.md (§«Looks Done But Isn't» — source list of 18 bullets)
    - .planning/phases/07-polish-documentation/07-RESEARCH.md (lines 661-688 — 18-Item Evidence Map; this is the literal source-of-truth row content)
    - .planning/phases/07-polish-documentation/07-CONTEXT.md (D-18..D-22 — audit policy + manual-only items)
    - tests/audit/test_static.py (must exist from plan 07-07 — confirms 7 audit-static test node IDs)
    - tests/bet_maker/test_asyncapi_smoke.py + tests/line_provider/test_asyncapi_smoke.py (must exist from plan 07-08)
    - tests/bet_maker/test_e2e_rabbitmq.py (P5 e2e — covers idempotency + DLQ items)
    - tests/bet_maker/jobs/test_reconciler_tick.py (P6 — covers reconciler exception-isolation item)
    - tests/bet_maker/test_bet_routes.py (P3 — covers Decimal 422 + Decimal exact roundtrip items)
    - src/bet_maker/entrypoints/messaging.py (consumer file; reference for `file:line` evidence)
    - src/bet_maker/repositories/bets.py (FOR UPDATE SKIP LOCKED `file:line`)
    - src/bet_maker/infrastructure/db/engine.py (expire_on_commit=False `file:line`)
    - Dockerfile (exec-form CMD + bookworm pin + PYTHONUNBUFFERED `file:line`)
    - docker-compose.yml (named volumes + healthcheck wiring `file:line`)
  </read_first>
  <action>
    Create `.planning/phases/07-polish-documentation/07-AUDIT.md` with the following structure verbatim. Resolve all `file:line` placeholders to actual line numbers in the current code-base by reading the source files. Use the RESEARCH.md 18-Item Evidence Map (lines 661-688) as the literal source.

    File content:

    ```markdown
    # 07-AUDIT.md — «Looks Done But Isn't» 19-item Audit

    **Phase:** 07-polish-documentation
    **Created:** 2026-05-18
    **Source:** ROADMAP.md Phase 7 SC#6 + `.planning/research/PITFALLS.md` §«Looks Done But Isn't»
    **Policy (D-18):** every row resolves to `verified`, `fix-applied`, or `waived`. Zero `waived` without written justification in Notes column.

    ## Audit Table

    | # | Item | Evidence | Status | Notes |
    |---|------|----------|--------|-------|
    | 1 | Manual ack on every `@router.subscriber(...)` | `src/bet_maker/entrypoints/messaging.py:<LINE-of-ack_policy>` (`ack_policy=AckPolicy.MANUAL`); `await msg.ack()` after `async with uow:`. Automated: `tests/audit/test_static.py::test_subscribers_have_manual_ack` | verified | R1/F1. Static-audit test enforces invariant against accidental decorator-kwarg drop. |
    | 2 | Idempotency on consumer redelivery (concurrent settle no-op) | `tests/bet_maker/test_e2e_rabbitmq.py` (P5 e2e — concurrent settle / redelivery scenarios via real-RMQ container) | verified | R3 / D-12. Existing P5 e2e covers redelivery idempotency end-to-end; no new test needed (D-21). |
    | 3 | Reconciler loop body wrapped `try/except Exception:` | `src/bet_maker/jobs/reconciler.py` (P6 D-13 — wrapped); `tests/bet_maker/jobs/test_reconciler_tick.py::test_tick_exception_isolation` | verified | R8. P6 D-22 — existing test asserts a single failed tick logs and continues; `/health` 503 on `task.done()` covers the dead-task case. |
    | 4 | `FOR UPDATE SKIP LOCKED` on `get_pending_locked` | `src/bet_maker/repositories/bets.py:<LINE-of-with_for_update>` (`.with_for_update(skip_locked=True)`); Automated: `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` | verified | R3. Static-audit test enforces invariant against accidental removal during a refactor. |
    | 5 | Durable queue + persistent messages | `src/bet_maker/entrypoints/messaging.py:<LINE-of-RabbitQueue>` (`durable=True`); Automated: `tests/audit/test_static.py::test_durable_queue_and_exchange`. Manual: `docker compose up -d && docker exec bsw-rabbitmq-1 rabbitmqctl list_queues name durable` — expect `bet_maker.events.finished true` | verified | R4 / R10. Static test covers code-side; manual rabbitmqctl verifies broker-side. |
    | 6 | Named volumes preserve state across restart | `docker-compose.yml:<LINE-of-volumes-block>` (`postgres_data`, `rabbitmq_data`). Manual: `docker compose up -d && docker volume ls \| grep -E "^.*bsw_(postgres\|rabbitmq)_data"` — expect 2 rows | verified | R10. Manual-only (D-20 — requires Docker daemon). |
    | 7 | Healthcheck dependency wiring | `docker-compose.yml:<LINE-of-depends_on-block>` (`depends_on: condition: service_healthy` on postgres and rabbitmq). Manual: `docker compose up -d && docker compose ps` — expect `(healthy)` on postgres and rabbitmq before app services come up | verified | D1 / D2. Manual-only — Docker daemon required. |
    | 8 | `/health` checks deps (not just `{"ok": true}`) | `src/bet_maker/entrypoints/api/health.py:<LINE-of-pg_ok>` (returns `{"checks": {"postgres", "rabbitmq", "rabbitmq_consumer", "reconciler"}}`); covered by existing `tests/bet_maker/test_health.py` (200 / 503 degraded scenarios across P3 / P5 / P6) | verified | D2 / D-13. Tests cover all four 503 branches. |
    | 9 | DLQ wired (poison → DLQ) | `src/bet_maker/entrypoints/messaging.py:<LINE-of-x-dead-letter-exchange>` (RabbitQueue.arguments x-dead-letter-exchange); `tests/bet_maker/test_e2e_rabbitmq.py` (poison-to-DLQ e2e scenario from P5) | verified | R7. Existing P5 e2e covers (D-21). |
    | 10 | Schema version validation rejects unsupported versions | `src/bet_maker/entrypoints/messaging.py:<LINE-of-_SCHEMA_VERSION_SUPPORTED-check>` (raises `UnsupportedSchemaVersion` for schema_version != 1); covered by P5 unit + e2e tests | verified | F7. POISON branch routes to DLQ via reject(requeue=False). |
    | 11 | `expire_on_commit=False` on async_sessionmaker | `src/bet_maker/infrastructure/db/engine.py:<LINE-of-async_sessionmaker>` (`async_sessionmaker(engine, expire_on_commit=False)`); Automated: `tests/audit/test_static.py::test_async_sessionmaker_expire_on_commit_false` | verified | A1. Without this, post-commit ORM attribute access raises MissingGreenlet. |
    | 12 | SIGTERM handled (`docker compose down` exits 0 in <5s) | `Dockerfile:<LINE-of-CMD>` (exec-form `CMD [...]`); `docker-compose.yml:<LINE-of-stop_grace_period>` (`stop_grace_period: 30s`); Automated: `tests/audit/test_static.py::test_dockerfile_exec_form_cmd`. Manual: `docker compose up -d && sleep 10 && time docker compose down` — expect exit code 0 and < 5s wall time | verified | R11 / D-04. Static test covers code form; manual run verifies signal handling end-to-end. |
    | 13 | `python:3.10-slim-bookworm` pinned (no rolling tag) | `Dockerfile:<LINE-of-PYTHON_VERSION-ARG>` (`ARG PYTHON_VERSION=3.10-slim-bookworm`); Automated: `tests/audit/test_static.py::test_dockerfile_pinned_python_bookworm` | verified | D-20 from CLAUDE.md Stack Patterns. |
    | 14 | `PYTHONUNBUFFERED=1` set (both builder + runtime stages) | `Dockerfile:<LINE-of-PYTHONUNBUFFERED>` (both stages); Automated: `tests/audit/test_static.py::test_pythonunbuffered_set` | verified | D-04. structlog requires unbuffered stdout for real-time visibility. |
    | 15 | CMD in exec form (`CMD ["python", ...]`) | `Dockerfile:<LINE-of-CMD>` (exec-form `CMD [...]`); `docker-compose.yml:<LINE-of-command-line-provider>` and `:<LINE-of-command-bet-maker>` (compose `command:` also JSON-array, exec-form); Automated: `tests/audit/test_static.py::test_dockerfile_exec_form_cmd` | verified | D-04 / R11. |
    | 16 | structlog `clear_contextvars` in middleware + handler `try/finally` | `src/bet_maker/entrypoints/middleware.py` (RequestContextMiddleware — bind/clear via try/finally); `src/bet_maker/entrypoints/messaging.py:<LINE-of-clear_contextvars>` (consumer handler — clear at top + in finally) | verified | A7. Covered indirectly by existing health-route X-Request-ID echo test in `tests/bet_maker/test_health.py` and `tests/line_provider/test_health.py::test_health_echoes_request_id_header`. |
    | 17 | `mypy --strict` zero errors, no `# type: ignore` on critical paths | `.github/workflows/ci.yml:<LINE-of-mypy-step>` (`Mypy strict`); Manual: `grep -rn "# type: ignore" src/` — expect zero results | verified | D-12 / Pitfall 7. CI step enforces; grep covers any drift. Phase 7 plan 07-11 re-verifies. |
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

    - All 19 rows resolve to `verified`. Zero `fix-applied`, zero `waived`.
    - Phase 7 introduces no new runtime code on the audited paths — only static-audit tests (plan 07-07) and OpenAPI metadata polish (plans 07-04 / 07-05).
    - `file:line` references resolved against the post-P6 code-base; static-audit tests (plan 07-07) catch future regressions.
    ```

    **Critical:** Before writing the file, read each referenced source file (`src/bet_maker/entrypoints/messaging.py`, `src/bet_maker/repositories/bets.py`, `src/bet_maker/infrastructure/db/engine.py`, `Dockerfile`, `docker-compose.yml`, `src/bet_maker/entrypoints/api/health.py`) and resolve every `<LINE-of-...>` placeholder to the actual line number where the pattern appears. Replace placeholders verbatim — no `TBD` or `<>` in the committed file.

    For example, if `src/bet_maker/repositories/bets.py` has `.with_for_update(skip_locked=True)` on line 62, the row reads:
    ```
    | 4 | `FOR UPDATE SKIP LOCKED` on `get_pending_locked` | `src/bet_maker/repositories/bets.py:62` (`.with_for_update(skip_locked=True)`); Automated: `tests/audit/test_static.py::test_repositories_use_for_update_skip_locked` | verified | R3. Static-audit test enforces invariant against accidental removal during a refactor. |
    ```

    After writing, run a self-verification:
    - `grep -c "^| [0-9]* |" .planning/phases/07-polish-documentation/07-AUDIT.md` returns ≥ 19 (19 audit rows + manual-only sub-table — accept any count ≥ 19; sub-table rows also start with `| <digit> |`).
    - `grep -c "verified" .planning/phases/07-polish-documentation/07-AUDIT.md` returns ≥ 20 (every row's Status + sign-off).
    - `grep -c "waived" .planning/phases/07-polish-documentation/07-AUDIT.md` returns 0 (no `waived` rows beyond policy declaration mentioning "Zero `waived`...").
    - Adjusted policy-line search: `grep -F "Zero \`waived\`" .planning/phases/07-polish-documentation/07-AUDIT.md` may return 1 (policy line itself).

    No emojis (CLAUDE.md). No `TBD`, no `<...>`, no unresolved placeholders.
  </action>
  <verify>
    <automated>grep -cE "^\| [0-9]+ \| " .planning/phases/07-polish-documentation/07-AUDIT.md</automated>
  </verify>
  <acceptance_criteria>
    - File `.planning/phases/07-polish-documentation/07-AUDIT.md` exists, line count ≥ 50
    - `grep -cE "^\| [0-9]+ \| " .planning/phases/07-polish-documentation/07-AUDIT.md` returns ≥ 19 (19 audit rows + extra schema-parity row 20; manual sub-table adds more — accept ≥ 19, ideally ≥ 23)
    - `grep -c "| verified |" .planning/phases/07-polish-documentation/07-AUDIT.md` returns ≥ 19 (every main row marked verified)
    - `grep -cE "\| (fix-applied|waived) \|" .planning/phases/07-polish-documentation/07-AUDIT.md` returns 0 (no fix-applied or waived rows expected — all items pass without P7 edits)
    - `grep -F "TBD" .planning/phases/07-polish-documentation/07-AUDIT.md` returns 0 (no TBDs)
    - `grep -F "<LINE-of-" .planning/phases/07-polish-documentation/07-AUDIT.md` returns 0 (all placeholders resolved)
    - `grep -c "tests/audit/test_static.py::" .planning/phases/07-polish-documentation/07-AUDIT.md` ≥ 5 (multiple rows reference static-audit tests from plan 07-07)
    - `grep -c "tests/bet_maker/" .planning/phases/07-polish-documentation/07-AUDIT.md` ≥ 3 (references to P3/P5/P6 existing tests)
    - No emojis (visual inspection during write)
  </acceptance_criteria>
  <done>07-AUDIT.md committed with 19+1 rows, all `verified`, every Evidence resolved to concrete file:line / pytest node ID / shell command; phase-gate plan 07-12 can reference this for sign-off.</done>
</task>

</tasks>

<verification>
- `wc -l .planning/phases/07-polish-documentation/07-AUDIT.md` ≥ 50
- `grep -c "verified" 07-AUDIT.md` ≥ 19
- `grep -c "waived" 07-AUDIT.md` reflects only the policy line (0 row-level waivers)
- No `TBD`, no placeholders, no emojis
- Audit table cross-references plan 07-07 static tests, P5 e2e, P6 reconciler tests, P3 integration tests
</verification>

<success_criteria>
- 07-AUDIT.md is a single self-contained artefact mapping 18 «Looks Done But Isn't» items + 1 schema-parity item to concrete evidence
- All 19 rows resolve to `verified` (zero fix-applied, zero waived)
- Manual-only commands are recorded verbatim with expected output
- File is referenced by plan 07-10 README §Reliability (link from `.planning/phases/07-polish-documentation/07-AUDIT.md` if desired) and plan 07-12 phase-gate
</success_criteria>

<output>
After completion, create `.planning/phases/07-polish-documentation/07-09-SUMMARY.md` recording:
- 07-AUDIT.md line count
- Status histogram (verified count, fix-applied count, waived count)
- Resolved file:line references (a few samples to confirm placeholders were filled)
- Sign-off statement that all 19 rows are evidenced
</output>
