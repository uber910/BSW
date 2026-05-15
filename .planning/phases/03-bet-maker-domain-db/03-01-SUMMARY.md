---
phase: 03-bet-maker-domain-db
plan: "01"
subsystem: planning
tags: [requirements-sync, doc-only, tz-compliance, bet-maker]
dependency_graph:
  requires: []
  provides: [REQUIREMENTS.md-BM-01-synced, REQUIREMENTS.md-BM-05-synced, REQUIREMENTS.md-BM-13-added]
  affects: [03-02-PLAN.md, 03-03-PLAN.md, 03-04-PLAN.md, 03-05-PLAN.md]
tech_stack:
  added: []
  patterns: [tz-first-source-verification, requirements-sync-per-phase]
key_files:
  created: []
  modified:
    - .planning/REQUIREMENTS.md
decisions:
  - "D-01 (Phase 3 CONTEXT.md): coefficient НЕ хранится в Bet — ТЗ стр. 3 POST /bet body = {идентификатор события, сумма ставки}"
  - "D-02 (Phase 3 CONTEXT.md): GET /bet/{bet_id} реализуется как BM-13 — присутствует на диаграмме ТЗ стр. 3"
metrics:
  duration: "~2 min (136s)"
  completed_date: "2026-05-15"
  tasks_completed: 4
  files_modified: 1
---

# Phase 3 Plan 1: REQUIREMENTS.md sync against TZ (BM-01/BM-05/BM-13) Summary

**One-liner:** REQUIREMENTS.md синхронизирован с ТЗ стр. 3: coefficient удалён из Bet payload (D-01), добавлен BM-13 GET /bet/{bet_id} (D-02), Traceability расширена до 43 требований.

## What Was Built

Sync-only plan (doc-only, zero code). Устраняет drift между REQUIREMENTS.md и первоисточником ТЗ до того, как Wave 1 начнёт писать модели.

### Task 1: Verify drift against TZ first source
**Status:** Complete

Прочитан PDF ТЗ (страницы 1-4). Три факта подтверждены:

1. **POST /bet body (ТЗ стр. 3, stream 4):** «идентификатор события — строка или число, сумму ставки — строго положительное число с двумя знаками после запятой». Coefficient НЕ упомянут. Подтверждает D-01.

2. **GET /bets (ТЗ стр. 3, stream 4):** «массив JSON-объектов, содержащих информацию о ставках: их идентификаторы и текущие статусы». Coefficient НЕ упомянут. Подтверждает D-01.

3. **GET /bet/{bet_id}:** Отсутствует в текстовом описании ТЗ (стр. 3, stream 3-4). По CONTEXT.md D-02 — присутствует на диаграмме ТЗ стр. 3. Реализуется в P3 как BM-13. Подтверждает D-02.

Все три факта совпадают с D-01 и D-02.

### Task 2: Rewrite BM-01 (remove coefficient) per D-01
**Status:** Complete

BM-01 обновлён: убрано `coefficient Decimal 6.2`, добавлена явная цитата ТЗ стр. 3, добавлена ссылка `Per D-01 (Phase 3 CONTEXT.md)`.

### Task 3: Rewrite BM-05 + add BM-13 per D-01/D-02
**Status:** Complete

BM-05 обновлён: убран «снимок coefficient на момент создания», уточнён ответ до `201 с BetRead`, добавлена ссылка `Per D-01`.

BM-13 добавлен после BM-12 и до `### Quality (QA)`:
`GET /bet/{bet_id}` — 200 + BetRead или 404 `{"detail":"bet {id} not found"}`. Per D-02.

### Task 4: Update Traceability table + Coverage counters
**Status:** Complete

- BM-13 вставлена в Traceability table между BM-12 и QA-01 (Phase 3, Pending).
- Coverage: 42 → **43 total** (100% mapped).
- Phase 3 distribution: 8 → **9 requirements** (BM-01..03, BM-05..08, BM-13, QA-07).

## Decisions Made

- `Per D-01 (Phase 3 CONTEXT.md)`: coefficient НЕ хранится в Bet-записи. ТЗ (стр. 3) определяет POST /bet body строго как `{идентификатор события, сумма ставки}`. Первоисточник подтверждён чтением PDF.
- `Per D-02 (Phase 3 CONTEXT.md)`: GET /bet/{bet_id} регистрируется как новый BM-13 и реализуется в P3. Эндпоинт присутствует на диаграмме ТЗ стр. 3, отсутствует в текстовом описании.

## TZ Citations (page references)

| Цитата из ТЗ | Страница | Вывод |
|---|---|---|
| «идентификатор события — строка или число, сумму ставки — строго положительное число» | стр. 3 (POST /bet) | coefficient НЕ является частью Bet payload |
| «массив JSON-объектов, содержащих информацию о ставках: их идентификаторы и текущие статусы» | стр. 3 (GET /bets) | coefficient НЕ фигурирует в ответе GET /bets |
| диаграмма с GET /bet/{bet_id} | стр. 3 (диаграмма) | эндпоинт присутствует на диаграмме → BM-13 |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — doc-only plan, no code introduced.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced (doc-only).

## Self-Check: PASSED

- `.planning/REQUIREMENTS.md` modified and verified with grep acceptance criteria.
- `grep -c "BM-01.*Per D-01"` = 1
- `grep -c "coefficient Decimal 6.2|снимок coefficient"` = 0
- `grep -c "BM-13"` = 2 (requirements section + traceability table)
- `grep -c "v1 requirements: 43 total"` = 1
- `grep -c "Phase 3 (bet-maker DB): 9 requirements"` = 1
- `uv run pytest -q` = 97 passed (baseline unchanged)
