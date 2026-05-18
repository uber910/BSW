---
phase: 06-reconciliation-job
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - .planning/REQUIREMENTS.md
  - .planning/ROADMAP.md
autonomous: true
requirements: [BM-12]
tags: [docs, sync, cancelled-status, reconciliation]

must_haves:
  truths:
    - "REQUIREMENTS.md BM-05 lists status set as PENDING | WON | LOST | CANCELLED"
    - "REQUIREMENTS.md BM-12 describes the CANCELLED branch (404 from line-provider)"
    - "ROADMAP.md Phase 6 Goal mentions CANCELLED-on-404 branch"
    - "ROADMAP.md Phase 6 Success Criteria #1 mentions WON/LOST/CANCELLED reconciler outcomes"
    - "ROADMAP.md Phase 6 Success Criteria #5 mentions CANCELLED scenario (delete-event)"
    - "ROADMAP.md Phase 6 Plans block lists eleven 06-NN-*-PLAN.md entries with checkboxes"
  artifacts:
    - path: ".planning/REQUIREMENTS.md"
      provides: "BM-05 status set + BM-12 CANCELLED branch description"
      contains: "CANCELLED"
    - path: ".planning/ROADMAP.md"
      provides: "Phase 6 Goal/SC#1/SC#5 mentions CANCELLED; Plans list updated"
      contains: "CANCELLED"
  key_links:
    - from: ".planning/REQUIREMENTS.md BM-05"
      to: "src/bet_maker/schemas/bets.py BetStatus enum (extended in Plan 03)"
      via: "say-do parity — text spec mirrors the eventual code"
      pattern: "PENDING \\| WON \\| LOST \\| CANCELLED"
    - from: ".planning/ROADMAP.md Phase 6 Plans"
      to: ".planning/phases/06-reconciliation-job/*.md filenames"
      via: "checkbox list of plan files used by orchestrator/checker"
      pattern: "06-\\d{2}-.*-PLAN\\.md"
---

<objective>
Sync the project documentation with the locked CONTEXT.md decisions D-03 / D-25 BEFORE any code is written:
- REQUIREMENTS.md BM-05: extend the documented bet-status set from `PENDING | WON | LOST` to `PENDING | WON | LOST | CANCELLED` and explain that `CANCELLED` is a recovery-status assigned by the reconciler when line-provider returns 404 for the event_id.
- REQUIREMENTS.md BM-12: expand the description so it lists all three terminal branches (WON / LOST via terminal-state poll, CANCELLED via 404).
- ROADMAP.md Phase 6: Goal sentence + Success Criteria #1 and #5 mention the CANCELLED branch; the `Plans:` block is filled with the eleven 06-NN file names and unchecked boxes.

Purpose: This is the standard "doc-sync first plan" pattern (P2 02-01 / P3 03-01 / P4 04-01 / P5 05-10). It is a Wave 0 task so the rest of the phase plans (which depend on the new docs being authoritative) can quote from them safely. The CANCELLED extension is documented as an engineering interpretation of the TZ — surfaced explicitly per memory rule `feedback_verify_against_tz` so the divergence is auditable.

Output: Two edited markdown files committed to git with a doc-sync commit message. No code touched.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/ROADMAP.md
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update REQUIREMENTS.md BM-05 and BM-12 to include CANCELLED</name>
  <files>.planning/REQUIREMENTS.md</files>
  <read_first>
    - .planning/REQUIREMENTS.md (lines 32-44 — BM-01 through BM-13, especially the BM-05 line and the BM-12 line)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-25 (sync-task spec)
  </read_first>
  <action>
    Edit `.planning/REQUIREMENTS.md` (use Edit tool, two targeted replacements; do NOT touch anything else):

    1. Locate the BM-05 line:
       ```
       - [x] **BM-05**: `POST /bet` — приём ставки; в теле `{event_id, amount}` (amount > 0, ровно 2 знака после запятой); ответ — 201 с BetRead `{id, event_id, amount, status, created_at}`; status=PENDING при создании. Per D-01 (Phase 3 CONTEXT.md): coefficient snapshot НЕ хранится — coefficient остаётся в line-provider; ТЗ стр. 3 не требует coefficient в Bet payload.
       ```
       Append (do NOT rewrite the existing text) a new sentence at the end of the same bullet:
       ```
        Статусы ставки: `PENDING | WON | LOST | CANCELLED` (Phase 6 / D-03). `CANCELLED` — recovery-статус: ставка помечается reconciler'ом при 404 от line-provider (событие удалено или LP пересоздан) — инженерная трактовка ТЗ (memory `feedback_verify_against_tz`), отдельно отмечена в README §Reliability (DOC-04).
       ```

    2. Locate the BM-12 line:
       ```
       - [ ] **BM-12**: Reconciliation job — asyncio background task в lifespan, период через pydantic-settings (default 30s); выбирает PENDING-ставки, тянет статус события из line-provider, доводит до WON/LOST
       ```
       Replace ONLY this line (keep the `- [ ] **BM-12**:` prefix and trailing-newline) with:
       ```
       - [ ] **BM-12**: Reconciliation job — asyncio background task в lifespan, период через pydantic-settings (default 30s); выбирает PENDING-ставки через `BetRepository.get_pending_event_ids()`, тянет статус каждого события из line-provider через отдельный `HttpEventLookup` (reconciler-params, 5 attempts / max_backoff 10s — P4 D-04), доводит до `WON` / `LOST` (terminal_state) или `CANCELLED` (404 от LP — событие удалено). Per D-02/D-03/D-04 (Phase 6 CONTEXT.md).
       ```

    Do NOT change anything else in the file (no traceability table edits — BM-12 is already mapped to Phase 6 there; we are not renaming).
  </action>
  <verify>
    <automated>grep -E 'BM-05.*CANCELLED|PENDING \| WON \| LOST \| CANCELLED' .planning/REQUIREMENTS.md && grep -E 'BM-12.*get_pending_event_ids|BM-12.*CANCELLED.*404' .planning/REQUIREMENTS.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "PENDING | WON | LOST | CANCELLED" .planning/REQUIREMENTS.md` returns 1 (one match in the BM-05 bullet)
    - `grep -c "BM-12.*get_pending_event_ids" .planning/REQUIREMENTS.md` returns 1
    - `grep -c "CANCELLED.*404\|404.*CANCELLED" .planning/REQUIREMENTS.md` is at least 1 (BM-12 mentions the 404→CANCELLED mapping)
    - `grep -c "feedback_verify_against_tz" .planning/REQUIREMENTS.md` returns 1 (the BM-05 reference to the memory rule)
    - Section count and headings unchanged: `grep -cE "^### (Infrastructure|line-provider|bet-maker|Quality|Documentation)" .planning/REQUIREMENTS.md` returns 5
    - Total BM-NN bullets unchanged at 13: `grep -cE "^- \[[ x]\] \*\*BM-[0-9]+\*\*" .planning/REQUIREMENTS.md` returns 13
  </acceptance_criteria>
  <done>BM-05 line gained the CANCELLED sentence; BM-12 line rewritten to include get_pending_event_ids + 404→CANCELLED; no other bullets changed.</done>
</task>

<task type="auto">
  <name>Task 2: Update ROADMAP.md Phase 6 Goal/SC#1/SC#5 and finalise the Plans list</name>
  <files>.planning/ROADMAP.md</files>
  <read_first>
    - .planning/ROADMAP.md (lines 179-211 — the entire `### Phase 6: Reconciliation job` section, current Goal/SC/Plans)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-25 (which SC lines mention CANCELLED)
    - .planning/phases/06-reconciliation-job/06-VALIDATION.md §Per-Task Verification Map (eleven 06-NN plan rows — source-of-truth for plan list and slugs)
  </read_first>
  <action>
    Edit `.planning/ROADMAP.md` using Edit tool — keep all phases other than Phase 6 unchanged. Inside `### Phase 6: Reconciliation job`:

    1. Replace the **Goal** line:
       FROM: `**Goal**: A bet **never** stays PENDING after its event has finished, even if the AMQP message was lost. An asyncio background task polls line-provider for terminal-state events and settles via the same `settle_bets_for_event` interactor as the consumer.`
       TO:   `**Goal**: A bet **never** stays PENDING after its event has finished, even if the AMQP message was lost. An asyncio background task polls line-provider for terminal-state events and settles via the same `settle_bets_for_event` interactor as the consumer, or marks the bets `CANCELLED` via a new `cancel_bets_for_event` interactor when line-provider returns 404 (event deleted / LP recreated).`

    2. Replace **Success Criteria #1** (currently `1. If a state-change message is dropped ...`):
       TO: `1. If a state-change message is dropped between line-provider and bet-maker (verified by skipping the publish in a test), the reconciliation worker settles affected PENDING bets within `RECONCILIATION_INTERVAL_S` (default 30s, configurable via pydantic-settings) to `WON` / `LOST` when LP reports `FINISHED_WIN` / `FINISHED_LOSE`, or to `CANCELLED` when LP returns 404 for the event_id`

    3. Replace **Success Criteria #5**:
       TO: `5. End-to-end test scenarios: (a) create event → place bet → finish event → assert bet is WON via consumer; (b) create event → place bet → drop publish → finish event → assert bet is WON via reconciler within one interval; (c) create event → place bet → delete event from line-provider → assert bet becomes CANCELLED via reconciler within one interval`

    4. Replace the `**Plans**: TBD` line with `**Plans:** 11 plans across 7 waves (0..6)`.

    5. Immediately AFTER the `**Plans:** 11 plans across 7 waves (0..6)` line, add a blank line and then a `Plans:` block (same shape as the Phase 4/Phase 5 blocks):
       ```
       Plans:
       - [ ] 06-01-doc-sync-PLAN.md — REQUIREMENTS BM-05/BM-12 + ROADMAP Phase 6 Goal/SC sync (CANCELLED branch) (Wave 0)
       - [ ] 06-02-test-scaffolding-PLAN.md — 11 stub test files + conftest extensions (reconciler fixtures) (Wave 0)
       - [ ] 06-03-cancelled-status-migration-PLAN.md — BetStatus.CANCELLED enum + Alembic 0003 autocommit_block ALTER TYPE (Wave 1)
       - [ ] 06-04-reconciler-settings-PLAN.md — BetMakerSettings.line_provider_reconciler_attempts + _backoff_max_s (Wave 1)
       - [ ] 06-05-get-pending-event-ids-PLAN.md — BetRepository.get_pending_event_ids() DISTINCT PENDING query (Wave 1)
       - [ ] 06-06-cancel-interactor-PLAN.md — cancel_bets_for_event interactor + CancelResult DTO + unit tests (Wave 2)
       - [ ] 06-07-reconciler-job-PLAN.md — jobs/reconciler.py loop + _run_tick + unit tests (Wave 2)
       - [ ] 06-08-lifespan-health-wiring-PLAN.md — lifespan reconciler_event_lookup + create_task + /health 4th check (Wave 3)
       - [ ] 06-09-integration-tests-PLAN.md — respx drop-publish + reconciler/consumer concurrent race tests (Wave 4)
       - [ ] 06-10-e2e-drop-publish-PLAN.md — real-RMQ + real-PG e2e drop-publish (SC#5 / QA-08) (Wave 5)
       - [ ] 06-11-phase-gate-PLAN.md — coverage ≥80%, REQUIREMENTS/ROADMAP sync verify, plan checkboxes (Wave 6)
       ```

    6. In the Progress table at the bottom of ROADMAP.md, leave the Phase 6 row as `0/?` — it will be updated at phase completion by Plan 06-11.

    Do NOT touch Phases 1-5 or Phase 7.
  </action>
  <verify>
    <automated>grep -c "06-01-doc-sync-PLAN.md" .planning/ROADMAP.md && grep -c "11 plans across 7 waves" .planning/ROADMAP.md && grep -c "CANCELLED" .planning/ROADMAP.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "06-01-doc-sync-PLAN.md" .planning/ROADMAP.md` returns 1
    - `grep -c "06-11-phase-gate-PLAN.md" .planning/ROADMAP.md` returns 1
    - `grep -cE "^- \[ \] 06-\d{2}-" .planning/ROADMAP.md` returns 11 (eleven Phase 6 plan checkboxes — none ticked yet)
    - `grep -c "11 plans across 7 waves" .planning/ROADMAP.md` returns 1
    - `grep -c "CANCELLED" .planning/ROADMAP.md` returns at least 3 (Goal + SC#1 + SC#5 scenario c)
    - `grep -c "delete event from line-provider" .planning/ROADMAP.md` returns 1 (SC#5c)
    - Other phase sections untouched: `grep -cE "^### Phase " .planning/ROADMAP.md` returns 7
  </acceptance_criteria>
  <done>Phase 6 Goal + SC#1 + SC#5 mention CANCELLED; eleven plan files listed with unchecked boxes; Phases 1-5 and 7 untouched.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| n/a | Documentation-only change — no input traversal, no runtime code touched |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-01-01 | Tampering (spec drift) | REQUIREMENTS.md / ROADMAP.md | mitigate | This plan IS the mitigation — the say-do parity sync runs in Wave 0 so downstream plans cannot quote stale text |
| T-06-01-02 | Information Disclosure | n/a | accept | No secrets, no PII; docs are public to the reviewer |
</threat_model>

<verification>
- `grep -E 'BM-05.*CANCELLED' .planning/REQUIREMENTS.md` returns at least one hit.
- `grep -E '06-\d{2}-.*-PLAN.md' .planning/ROADMAP.md | wc -l` >= 11.
- `git diff --stat .planning/REQUIREMENTS.md .planning/ROADMAP.md` shows only those two files changed.
</verification>

<success_criteria>
- BM-05 documents the four-status set with the recovery-rationale sentence.
- BM-12 documents the CANCELLED-on-404 branch and references CONTEXT.md decisions.
- ROADMAP.md Phase 6 Goal/SC#1/SC#5 mention CANCELLED.
- ROADMAP.md Phase 6 has a fully populated `Plans:` block with 11 unchecked entries that match the planner-assigned filenames.
- No code or test files are touched in this plan.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-01-SUMMARY.md` describing exactly which lines were edited (file:line refs) and confirming the verification greps returned the expected counts.
</output>

## Decision Coverage

- D-01: Polling strategy — `get_pending_event_ids` exposed via REQUIREMENTS/ROADMAP sync (this plan locks BM-12 wording).
- D-25: First plan of Phase 6 is a sync-task (P2 02-01 / P3 03-01 / P4 04-01 / P5 05-10 pattern) — covered by this plan's two tasks.
