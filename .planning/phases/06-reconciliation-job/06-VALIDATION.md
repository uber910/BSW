---
phase: 6
slug: reconciliation-job
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-18
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.x (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` (existing) |
| **Quick run command** | `uv run pytest -x -q tests/bet_maker/` |
| **Full suite command** | `uv run pytest --cov=src --cov-report=term-missing` |
| **Estimated runtime** | ~30–60 seconds (unit + integration); ~3–5 min with e2e RMQ container |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -x -q tests/bet_maker/`
- **After every plan wave:** Run `uv run pytest --cov=src --cov-report=term-missing`
- **Before `/gsd-verify-work`:** Full suite must be green + coverage ≥ 80% phase floor
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 0 | BM-05 (CANCELLED) | — | REQUIREMENTS + ROADMAP say-do parity | manual | `grep CANCELLED .planning/REQUIREMENTS.md` | ✅ | ⬜ pending |
| 06-02-01 | 02 | 0 | BM-12 | — | Wave-0 stub files for all new modules | unit | `uv run pytest --collect-only tests/bet_maker/jobs/` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 1 | BM-05 | — | BetStatus.CANCELLED added + idempotent Alembic ALTER TYPE in autocommit_block | unit | `uv run pytest tests/bet_maker/migrations/test_0003_cancelled.py` | ❌ W0 | ⬜ pending |
| 06-04-01 | 04 | 1 | BM-12 | — | BetMakerSettings new fields (reconciler_attempts, reconciler_backoff_max_s) | unit | `uv run pytest tests/bet_maker/config/test_settings_reconciler.py` | ❌ W0 | ⬜ pending |
| 06-05-01 | 05 | 1 | BM-12 | — | get_pending_event_ids returns DISTINCT PENDING event_ids | unit | `uv run pytest tests/bet_maker/repositories/test_get_pending_event_ids.py` | ❌ W0 | ⬜ pending |
| 06-06-01 | 06 | 2 | BM-05 (CANCELLED) | — | cancel_bets_for_event interactor (404 → CANCELLED) idempotent | unit | `uv run pytest tests/bet_maker/interactors/test_cancel_bets_for_event.py` | ❌ W0 | ⬜ pending |
| 06-07-01 | 07 | 2 | BM-12 | — | jobs/reconciler.py: tick body + asyncio task survives transient errors | unit | `uv run pytest tests/bet_maker/jobs/test_reconciler_tick.py` | ❌ W0 | ⬜ pending |
| 06-07-02 | 07 | 2 | BM-12 / SC#2 | — | `_run_tick` catches Exception (not BaseException); CancelledError re-raises | unit | `uv run pytest tests/bet_maker/jobs/test_reconciler_cancellation.py` | ❌ W0 | ⬜ pending |
| 06-08-01 | 08 | 3 | BM-12 / SC#3 | — | Lifespan: start reconciler AFTER broker.start(), cancel FIRST in finally | integration | `uv run pytest tests/bet_maker/test_lifespan_reconciler.py` | ❌ W0 | ⬜ pending |
| 06-08-02 | 08 | 3 | BM-12 / SC#3 | — | /health returns 503 when reconciler task.done() is True | integration | `uv run pytest tests/bet_maker/test_health_reconciler.py` | ❌ W0 | ⬜ pending |
| 06-09-01 | 09 | 4 | BM-12 / SC#4 | — | Reconciler + consumer concurrent settle: exactly one settle (FOR UPDATE SKIP LOCKED) | integration | `uv run pytest tests/bet_maker/integration/test_reconciler_consumer_race.py` | ❌ W0 | ⬜ pending |
| 06-09-02 | 09 | 4 | BM-12 / SC#1 | — | respx-mocked LP + real-PG: drop publish → reconciler settles within interval | integration | `uv run pytest tests/bet_maker/integration/test_reconciler_drop_publish.py` | ❌ W0 | ⬜ pending |
| 06-10-01 | 10 | 5 | BM-12 / SC#5, QA-08 | — | E2E real-RMQ + real-PG + drop publish → bet WON via reconciler | e2e | `uv run pytest tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` | ❌ W0 | ⬜ pending |
| 06-11-01 | 11 | 6 | BM-12, QA-08 | — | Phase gate: coverage ≥ 80% + REQUIREMENTS sync + ROADMAP plan checkboxes | manual | `uv run pytest --cov=src --cov-fail-under=80` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/bet_maker/jobs/test_reconciler_tick.py` — stub for BM-12 (reconciler tick body)
- [ ] `tests/bet_maker/jobs/test_reconciler_cancellation.py` — stub for BM-12 (CancelledError propagates)
- [ ] `tests/bet_maker/repositories/test_get_pending_event_ids.py` — stub for BM-12 (DISTINCT query)
- [ ] `tests/bet_maker/interactors/test_cancel_bets_for_event.py` — stub for BM-05/BM-12 (404 → CANCELLED)
- [ ] `tests/bet_maker/migrations/test_0003_cancelled.py` — stub for BM-05 (Alembic ALTER TYPE)
- [ ] `tests/bet_maker/config/test_settings_reconciler.py` — stub for BM-12 (new settings fields)
- [ ] `tests/bet_maker/test_lifespan_reconciler.py` — stub for SC#3 (lifespan ordering)
- [ ] `tests/bet_maker/test_health_reconciler.py` — stub for SC#3 (/health task.done() → 503)
- [ ] `tests/bet_maker/integration/test_reconciler_consumer_race.py` — stub for SC#4 (concurrent settle)
- [ ] `tests/bet_maker/integration/test_reconciler_drop_publish.py` — stub for SC#1 (respx drop publish)
- [ ] `tests/bet_maker/e2e/test_reconciler_drop_publish_e2e.py` — stub for SC#5 (real-RMQ e2e)
- [ ] Reuse existing fixtures: `pg_engine` / `pg_session` / `pg_uow` / `rabbitmq_container` from P3/P5 conftest

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| RECONCILIATION_INTERVAL_S env var honored in docker compose | BM-12 | Compose lifecycle not in pytest scope | 1) `docker compose down -v && docker compose up -d`, 2) set `RECONCILIATION_INTERVAL_S=5` in `.env`, 3) tail bet-maker logs for `reconciler.tick.start` at 5s cadence |
| Alembic 0003 idempotency on rerun | BM-05 | Migration rerun requires manual orchestration | 1) `alembic upgrade head`, 2) `alembic downgrade -1`, 3) `alembic upgrade head` again — must succeed without error |
| ROADMAP.md Phase 6 Plans checkboxes synced | gates | Plan-checker reads file state; final tick is manual after each plan executes | Verify `[x]` for each plan in `.planning/ROADMAP.md` "### Phase 6" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
