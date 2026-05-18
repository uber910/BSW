---
phase: 05-rabbitmq-integration
plan: 10
subsystem: documentation
tags: [requirements, rabbitmq, faststream, tenacity, dlq, prefetch]

requires:
  - phase: 05-05-messaging-entrypoint
    provides: "Channel(prefetch_count=10) implementation in messaging.py; tenacity in-handler retry"
  - phase: 05-CONTEXT.md
    provides: "D-08/D-09 tenacity retry spec; D-26 prefetch_count=10 locked decision"
provides:
  - "REQUIREMENTS.md BM-09 synced: prefetch_count=10 via Channel(prefetch_count=10) on RabbitRouter"
  - "REQUIREMENTS.md BM-11 synced: tenacity in-handler retry (3 attempts, exp backoff); DLX name corrected to bsw.events.dlx; poison -> reject(requeue=False) enumerated; R7 noted"
affects: [review, 05-VALIDATION, phase-gate]

tech-stack:
  added: []
  patterns:
    - "REQUIREMENTS.md reflects implementation reality — no reviewer-visible drift between docs and code"

key-files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md

key-decisions:
  - "BM-09 prefetch: locked at prefetch_count=10 per D-26; REQUIREMENTS.md updated from stale 'prefetch=20'"
  - "BM-11 retry mechanism: in-handler tenacity (D-08/D-09), NOT x-death header counting; REQUIREMENTS.md updated accordingly"
  - "DLX name in BM-11 corrected from events.dlx to bsw.events.dlx per D-01 topology"

requirements-completed: [LP-06, BM-09, BM-10, BM-11]

duration: ~5min
completed: 2026-05-18
---

# Phase 5 Plan 10: Requirements Doc Sync Summary

**REQUIREMENTS.md BM-09 and BM-11 synced with Phase 5 implementation: prefetch_count=10 via Channel, tenacity in-handler retry (3 attempts exp backoff), DLX name corrected to bsw.events.dlx.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-18T07:50:00Z
- **Completed:** 2026-05-18T07:59:01Z
- **Tasks:** 3 (2 edits + 1 verification gate)
- **Files modified:** 1

## Accomplishments

- BM-09 wording updated: `prefetch=20` replaced with `prefetch_count=10 (через Channel(prefetch_count=10) на RabbitRouter)` — matches D-26 and `src/bet_maker/entrypoints/messaging.py`
- BM-11 wording replaced: `x-death header` mechanism replaced with tenacity in-handler retry spec (3 attempts, multiplier=0.2 min=0.2 max=2), poison classes enumerated, R7 noted, cross-reference to D-08/D-09 added
- DLX name corrected: `events.dlx` → `bsw.events.dlx` per D-01 topology decision
- Full suite still green: 295 passed, 0 failed; mypy 121 files clean; ruff clean

## Task Commits

1. **Task 1: Update BM-09 prefetch value** — `54f1250` (docs)
2. **Task 2: Update BM-11 retry mechanism** — `20f9f07` (docs)

Task 3 was a verification gate only — no code changes, no commit required.

## REQUIREMENTS.md Before/After Diff

### BM-09

**Before:**
```
- [ ] **BM-09**: FastStream RabbitRouter consumer на очереди `bet_maker.events.finished` с `AckPolicy.MANUAL`, prefetch=20, durable=true
```

**After:**
```
- [ ] **BM-09**: FastStream RabbitRouter consumer на очереди `bet_maker.events.finished` с `AckPolicy.MANUAL`, `prefetch_count=10` (через `Channel(prefetch_count=10)` на `RabbitRouter`), durable=true
```

### BM-11

**Before:**
```
- [ ] **BM-11**: DLX `events.dlx` + DLQ `bet_maker.events.finished.dlq` с bounded retries (max 3) через `x-death` header
```

**After:**
```
- [ ] **BM-11**: DLX `bsw.events.dlx` + DLQ `bet_maker.events.finished.dlq`; bounded in-handler retries для transient ошибок через `tenacity` (3 попытки, exponential backoff `multiplier=0.2, min=0.2, max=2` вокруг `settle_bets_for_event`); poison-сообщения (ValidationError / UnsupportedSchemaVersion / IntegrityError) сразу `reject(requeue=False) → DLQ`; nack(requeue=True) НЕ используется (R7). Per D-08/D-09 (Phase 5 CONTEXT.md).
```

## Grep Verification Outputs

```
prefetch_count=10: FOUND
prefetch=20: GONE
Channel ref: FOUND
tenacity: FOUND
x-death: GONE
bsw.events.dlx: FOUND
DLQ: FOUND
3 попытки: FOUND
reject: FOUND
D-08/D-09 ref: FOUND
BM-11 id: FOUND
```

Full suite: `295 passed, 26 warnings in 20.85s`
mypy: `Success: no issues found in 121 source files`
ruff: `All checks passed!`

## Files Created/Modified

- `.planning/REQUIREMENTS.md` — BM-09 prefetch value corrected; BM-11 retry mechanism, DLX name, and poison classes updated

## Decisions Made

None — followed plan as specified. Edits were line-level wording corrections to match already-implemented behavior.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Documentation-only change.

## Self-Check: PASSED

Files modified:
- `.planning/REQUIREMENTS.md` — FOUND

Commits:
- `54f1250` docs(05-10): sync BM-09 prefetch value — FOUND
- `20f9f07` docs(05-10): sync BM-11 retry mechanism — FOUND

grep checks: all PASSED (see Grep Verification Outputs above)

---
*Phase: 05-rabbitmq-integration*
*Completed: 2026-05-18*
