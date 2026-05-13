# Project State: BSW Betting System

**Last updated:** 2026-05-13 (initial)

## Project Reference

**Core Value:** Ставка никогда не остаётся в статусе PENDING после того, как её событие завершилось.

**Current focus:** Phase 1 — Skeleton + Infrastructure. Establish the foundation (pyproject + uv.lock, Dockerfiles, docker-compose with PG + RabbitMQ healthchecks + volumes, structlog, pydantic-settings, pre-commit, ruff + mypy strict, GitHub Actions CI, README skeleton, empty `/health` endpoints on both services).

## Current Position

- **Milestone:** v1
- **Phase:** 1 (Skeleton + Infrastructure)
- **Plan:** none yet — awaiting `/gsd-plan-phase 1`
- **Status:** Roadmap created; planning not started
- **Progress:** Phase 0 / 7 complete

```
[░░░░░░░] 0/7 phases (0%)
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| Phases planned | 0/7 |
| Phases complete | 0/7 |
| Requirements mapped | 42/42 (100%) |
| Plans complete | 0/0 |

## Accumulated Context

### Decisions

(See PROJECT.md "Key Decisions" — locked at initialization. Phase-level decisions accumulate here at each transition.)

- **2026-05-13**: 7-phase build order adopted from research/ARCHITECTURE.md (validated minimum-dependency DAG); Phase 2 and Phase 3 parallelizable after Phase 1.
- **2026-05-13**: Critical path = 1 → 2 → 5 → 6 → 7 (covers Core Value end-to-end).
- **2026-05-13**: Phase 5 is the risk-heavy phase (~50% of identified pitfalls cluster there) and warrants double code-review attention.

### Open Todos

(None yet — populated by `/gsd-plan-phase` and during phase execution.)

### Blockers

(None.)

### Insights / Learnings

(Populated at phase transitions.)

## Session Continuity

### Last Session

- **Started:** 2026-05-13
- **Ended:** 2026-05-13
- **Activity:** Roadmap synthesis from REQUIREMENTS.md + research/ARCHITECTURE.md.
- **Outcome:** ROADMAP.md (7 phases, 42/42 requirements mapped), STATE.md initialized, REQUIREMENTS.md traceability filled.

### Next Session

- **Recommended command:** `/gsd-plan-phase 1`
- **Goal:** Decompose Phase 1 (Skeleton + Infrastructure) into executable plans satisfying its 6 success criteria.

### Open Questions for Next Phase

(From research/SUMMARY.md "Gaps to Address" — decide during Phase 1 / Phase 5 planning):

- **Classic vs quorum queues** — Phase 5 planning will lock this in. Research recommends classic for the test task (with app-level redelivery tracking); quorum noted as production upgrade.
- **Idempotency variant** — variant (b) at queue consumer is must-have (covered by Phase 5 `FOR UPDATE SKIP LOCKED` + `WHERE status='PENDING'`); variant (a) `Idempotency-Key` header on `POST /bet` deferred to README "what I'd add next".
- **Reconciliation interval** — Phase 6 default 30s via `BET_MAKER_RECONCILIATION_INTERVAL_S`.
- **RabbitMQ Management UI binding** — Phase 1 to bind `127.0.0.1:15672:15672`, never `0.0.0.0`.

---
*State file initialized: 2026-05-13*
