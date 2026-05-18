---
phase: 7
slug: polish-documentation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-18
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.1.0 + pytest-cov 7.1.0 |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.coverage.*]`) |
| **Quick run command** | `uv run pytest -q tests/audit/test_static.py` |
| **Full suite command** | `uv run pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85` |
| **Estimated runtime** | ~60s full suite (existing ~295 tests + 7 new static tests); ~2s audit-only |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q tests/audit/ -x` (audit static tests only — < 5s)
- **After every plan wave:** Run `uv run pytest -q --cov --cov-fail-under=85` (full suite + coverage)
- **Before `/gsd-verify-work`:** Full suite must be green; `uv run mypy src` strict zero errors; AUDIT.md all rows `verified` or `fix-applied`
- **Max feedback latency:** 60s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 0 | DOC-01..04, QA-01, QA-09 | — | sync-task verification only (REQUIREMENTS/ROADMAP/README vs ТЗ PDF) — no runtime impact | manual | `diff` against ТЗ PDF (memory `feedback_verify_against_tz`) | ❌ W0 (manual) | ⬜ pending |
| 07-02-01 | 02 | 1 | DOC-01..04 (visibility) | — | error responses use static `ErrorDetail` schema (no f-string interpolation) | unit | `uv run pytest -q tests/audit/test_static.py::test_error_detail_schema_exists` | ❌ W0 (new) | ⬜ pending |
| 07-02-02 | 02 | 1 | DOC-01 (OpenAPI) | — | OpenAPI route metadata present (summary + responses + examples) | manual + grep | grep `summary=` in `src/{line_provider,bet_maker}/entrypoints/api/*.py` ≥ 1 per route | ✅ existing | ⬜ pending |
| 07-03-01 | 03 | 1 | QA-09 | — | CI pytest step extended with `--cov --cov-fail-under=85` | CI gate | `.github/workflows/ci.yml` contains `--cov-fail-under=85` | ✅ existing | ⬜ pending |
| 07-04-01 | 04 | 1 | ROADMAP P7 SC#6 (audit items 1, 4, 6, 8, 11, 13-15, 17) | various | static-audit invariants (manual ack, FOR UPDATE SKIP LOCKED, expire_on_commit, durable queue, Dockerfile exec-form + bookworm + PYTHONUNBUFFERED) | unit | `uv run pytest -q tests/audit/test_static.py` (7 tests) | ❌ W0 (new) | ⬜ pending |
| 07-05-01 | 05 | 2 | ROADMAP P7 SC#6 (all 19 items) | various | `07-AUDIT.md` table maps each item to evidence | manual review | grep `07-AUDIT.md` for 19 rows, zero unjustified `waived` | ❌ W0 (new) | ⬜ pending |
| 07-06-01 | 06 | 3 | DOC-01..04 | — | README final pass (ASCII diagram + curl walkthrough + Architecture + Reliability + Development + badges + Project status 7/7) | manual review | grep README for `## Quick start`, `## Architecture`, `## Reliability`, `## Development`, `coverage-85`, all curl steps, ASCII art | ✅ existing | ⬜ pending |
| 07-07-01 | 07 | 3 | QA-01 | — | mypy strict pass + AsyncAPI endpoint 200 smoke (`/asyncapi`) | CI gate + smoke | `uv run mypy src` zero errors; `curl :8001/asyncapi -o /dev/null -w %{http_code}` returns 200 in e2e test | ✅ existing (mypy) + ❌ W0 (asyncapi smoke) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/audit/__init__.py` — package marker (empty file)
- [ ] `tests/audit/test_static.py` — 7 regex/string-match tests (subscribers manual-ack, repositories FOR UPDATE SKIP LOCKED, sessionmaker expire_on_commit=False, Dockerfile exec-form CMD, `python:3.10-slim-bookworm` pin, `PYTHONUNBUFFERED=1`, RabbitQueue/Exchange `durable=True`)
- [ ] `.github/workflows/ci.yml` — Pytest step extension `--cov --cov-report=term-missing --cov-report=xml --cov-fail-under=85`
- [ ] `.planning/phases/07-polish-documentation/07-AUDIT.md` — 19-row table (18 items + 1 schema-parity reference)
- [ ] `src/line_provider/schemas/errors.py` — `ErrorDetail` Pydantic model
- [ ] `src/bet_maker/schemas/errors.py` — `ErrorDetail` Pydantic model (duplicated per cross-service no-import policy, P5 D-28)
- [ ] `tests/bet_maker/test_asyncapi_smoke.py` — smoke test that `/asyncapi` returns 200 on both services
- [ ] `tests/line_provider/test_asyncapi_smoke.py` — smoke test on line-provider side

*(No framework install needed — pytest-cov + pytest-asyncio already in dev-deps.)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose down` exit code 0 in < 5s | ROADMAP P7 SC#6 item «SIGTERM handled» / R11 | Requires real Docker daemon; CI sandbox does not run docker-in-docker for this stack | `docker compose up -d && sleep 10 && time docker compose down` — expect exit code 0 and < 5s wall time |
| `docker volume ls` shows `bsw_postgres_data` + `bsw_rabbitmq_data` | ROADMAP P7 SC#6 item «Volumes» / R10 | Docker daemon required | `docker compose up -d && docker volume ls \| grep bsw_` — expect 2 rows |
| Healthcheck wired (compose ps shows `(healthy)`) | ROADMAP P7 SC#6 item «Healthcheck wired» / D1/D2 | Docker daemon required | `docker compose up -d && watch -n 1 docker compose ps` — expect `(healthy)` on `postgres` and `rabbitmq` before app services come up |
| RabbitMQ Management UI accessible at 127.0.0.1:15672 | DOC-01 README claim | UI inspection; no programmatic gate | Open `http://127.0.0.1:15672`, login `guest/guest`, verify `bsw.events` exchange + `bet_maker.events.finished` queue + DLX `bsw.events.dlx` visible |
| Decimal exact roundtrip `POST /bet amount="10.00"` → `GET /bets` returns `"10.00"` | ROADMAP P7 SC#6 item «Decimal storage exact» | Already covered by P3 `test_bet_routes.py::TestPostBet201` — but manual end-to-end after `docker compose up` is the reviewer-checklist evidence | `curl -X POST :8001/bet ...` then `curl :8001/bets \| jq` — expect `"amount":"10.00"` |
| Decimal validation 422 on `amount="10.123"` | ROADMAP P7 SC#6 item «Decimal validation» | Already covered by P3 integration test — manual check after `up` is reviewer evidence | `curl -X POST :8001/bet -d '{"event_id":"...","amount":"10.123"}'` — expect 422 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify (07-04-01 and 07-05-01 lean manual but flanked by automated 07-03-01 and 07-07-01)
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
