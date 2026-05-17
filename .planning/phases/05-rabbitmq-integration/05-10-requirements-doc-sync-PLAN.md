---
phase: 05
plan: 10
type: execute
wave: 3
depends_on: [05, 07]
files_modified:
  - .planning/REQUIREMENTS.md
autonomous: true
requirements: [LP-06, BM-09, BM-10, BM-11]
must_haves:
  truths:
    - "REQUIREMENTS.md BM-09 says 'prefetch_count=10' (was 'prefetch=20') — matches D-26 + Plan 05 messaging.py implementation"
    - "REQUIREMENTS.md BM-11 describes tenacity in-handler retries (was 'x-death header bounded retries') — matches D-08 / D-09 implementation"
    - "REQUIREMENTS.md row for LP-06 / BM-09 / BM-10 / BM-11 reflects Plan 05 reality"
  artifacts:
    - path: ".planning/REQUIREMENTS.md"
      provides: "synced BM-09 and BM-11 wording"
      contains: "prefetch_count=10"
  key_links:
    - from: ".planning/REQUIREMENTS.md::BM-09"
      to: "src/bet_maker/entrypoints/messaging.py"
      via: "Channel(prefetch_count=10)"
      pattern: "prefetch_count=10"
---

<objective>
Resolve two pieces of TZ drift identified in RESEARCH.md §TZ Drift Check. Both items are documentation-only — implementation already follows D-26 / D-08 / D-09. This plan exists to close the loop so REQUIREMENTS.md and the codebase tell the same story.

Drift items:
1. **BM-09 prefetch:** REQUIREMENTS.md says `prefetch=20`; D-26 locks `prefetch_count=10`; Plan 05 ships `Channel(prefetch_count=10)`. Update REQUIREMENTS.md.
2. **BM-11 retry mechanism:** REQUIREMENTS.md says "bounded retries via `x-death` header"; D-08 + D-09 lock in-handler tenacity (3 attempts, exp backoff). Plan 05 ships tenacity wrapper on `settle_bets_for_event`. Update REQUIREMENTS.md.

Pitfalls guarded:
- **MEMORY: feedback_verify_against_tz**: drift between REQUIREMENTS.md and the codebase is exactly the kind of post-hoc inconsistency the rule asks us to keep in sync.
- **Reviewer experience**: a reviewer reading REQUIREMENTS.md and then the code should not find contradictions.

Output: 2 line-level edits to REQUIREMENTS.md.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/REQUIREMENTS.md
@.planning/phases/05-rabbitmq-integration/05-RESEARCH.md
@.planning/phases/05-rabbitmq-integration/05-CONTEXT.md
@src/bet_maker/entrypoints/messaging.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update REQUIREMENTS.md BM-09 prefetch value (20 -> 10)</name>
  <read_first>
    - .planning/REQUIREMENTS.md (line 40 — BM-09)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-26
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §TZ Drift Check (BM-09 entry)
    - src/bet_maker/entrypoints/messaging.py (Plan 05 — confirms Channel(prefetch_count=10))
  </read_first>
  <action>
    Edit `.planning/REQUIREMENTS.md`. Locate the BM-09 bullet (currently around line 40):

    Current text:
    ```
    - [ ] **BM-09**: FastStream RabbitRouter consumer на очереди `bet_maker.events.finished` с `AckPolicy.MANUAL`, prefetch=20, durable=true
    ```

    Replace with:
    ```
    - [ ] **BM-09**: FastStream RabbitRouter consumer на очереди `bet_maker.events.finished` с `AckPolicy.MANUAL`, `prefetch_count=10` (через `Channel(prefetch_count=10)` на `RabbitRouter`), durable=true
    ```

    Single line edit; no other change to this bullet or to surrounding text.
  </action>
  <verify>
    <automated>grep -q 'prefetch_count=10' .planning/REQUIREMENTS.md &amp;&amp; ! grep -q 'prefetch=20' .planning/REQUIREMENTS.md &amp;&amp; echo ok</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'prefetch=20' .planning/REQUIREMENTS.md | grep -v '^#'` returns 0 (old value gone)
    - `grep -q 'prefetch_count=10' .planning/REQUIREMENTS.md`
    - `grep -q 'Channel(prefetch_count=10)' .planning/REQUIREMENTS.md` (cross-reference to implementation form)
    - The line still starts with `- [ ] **BM-09**:` (checkbox + ID preserved)
    - No other BM-09 metadata changed (this is a wording fix, not a status change)
  </acceptance_criteria>
  <done>REQUIREMENTS.md BM-09 matches D-26 and Plan 05 messaging.py.</done>
</task>

<task type="auto">
  <name>Task 2: Update REQUIREMENTS.md BM-11 retry mechanism description (x-death header -> tenacity in-handler)</name>
  <read_first>
    - .planning/REQUIREMENTS.md (line 42 — BM-11)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-08 / D-09 / D-10
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §TZ Drift Check (BM-11 entry)
    - src/bet_maker/entrypoints/messaging.py (Plan 05 — confirms tenacity 3 attempts wrap)
  </read_first>
  <action>
    Edit `.planning/REQUIREMENTS.md`. Locate the BM-11 bullet (currently around line 42):

    Current text:
    ```
    - [ ] **BM-11**: DLX `events.dlx` + DLQ `bet_maker.events.finished.dlq` с bounded retries (max 3) через `x-death` header
    ```

    Replace with:
    ```
    - [ ] **BM-11**: DLX `bsw.events.dlx` + DLQ `bet_maker.events.finished.dlq`; bounded in-handler retries для transient ошибок через `tenacity` (3 попытки, exponential backoff `multiplier=0.2, min=0.2, max=2` вокруг `settle_bets_for_event`); poison-сообщения (ValidationError / DecodeError / UnsupportedSchemaVersion / IntegrityError) сразу `reject(requeue=False) → DLQ`; nack(requeue=True) НЕ используется (R7). Per D-08/D-09 (Phase 5 CONTEXT.md).
    ```

    Key elements that must appear in the new text:
    - DLX name corrected to `bsw.events.dlx` (was `events.dlx` — matches D-01).
    - DLQ name unchanged: `bet_maker.events.finished.dlq`.
    - Mechanism: in-handler tenacity (NOT `x-death` header).
    - Tenacity params explicit: 3 attempts, multiplier=0.2 min=0.2 max=2 (matches implementation).
    - Poison classes enumerated (matches Plan 05 except-clause).
    - R7 invariant noted (no nack(requeue=True)).
    - Cross-reference to D-08/D-09 for auditability.

    Single bullet edit; no other change to surrounding requirements.
  </action>
  <verify>
    <automated>grep -q 'tenacity' .planning/REQUIREMENTS.md &amp;&amp; ! grep -q 'x-death' .planning/REQUIREMENTS.md &amp;&amp; grep -q 'bsw.events.dlx' .planning/REQUIREMENTS.md &amp;&amp; echo ok</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c 'x-death' .planning/REQUIREMENTS.md | grep -v '^#'` returns 0 (old mechanism description gone)
    - `grep -q 'tenacity' .planning/REQUIREMENTS.md` (new mechanism described)
    - `grep -q 'bsw.events.dlx' .planning/REQUIREMENTS.md` (DLX name corrected)
    - `grep -q 'bet_maker.events.finished.dlq' .planning/REQUIREMENTS.md` (DLQ name unchanged)
    - `grep -q '3 попытки' .planning/REQUIREMENTS.md` OR `grep -q '3 attempts' .planning/REQUIREMENTS.md`
    - `grep -q 'reject(requeue=False)' .planning/REQUIREMENTS.md`
    - `grep -q 'Per D-08/D-09' .planning/REQUIREMENTS.md` (cross-reference present)
    - The line still starts with `- [ ] **BM-11**:`
  </acceptance_criteria>
  <done>REQUIREMENTS.md BM-11 matches D-08/D-09 and Plan 05 messaging.py.</done>
</task>

<task type="auto">
  <name>Task 3: Run full suite to ensure doc edit did not break anything (sanity)</name>
  <read_first>
    - .planning/REQUIREMENTS.md (post-edit)
  </read_first>
  <action>
    Sanity gate. Run `uv run pytest -q` and confirm the full suite stays green. REQUIREMENTS.md is markdown — it is not imported anywhere — but the suite-wide check guards against any accidental edit to nearby production files.

    Additionally run `uv run ruff check .planning/` (no-op for markdown but exercises the check pathway) and `uv run mypy src tests` to confirm no regressions.

    No code change; this task is purely a verification gate before the SUMMARY is written.
  </action>
  <verify>
    <automated>uv run pytest -q &amp;&amp; uv run mypy src tests &amp;&amp; uv run ruff check src tests</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest -q` exits 0
    - `uv run mypy src tests` exits 0
    - `uv run ruff check src tests` exits 0
    - REQUIREMENTS.md still parses as valid markdown (visual smoke — no syntax fences left open, etc.)
  </acceptance_criteria>
  <done>Doc-sync complete; full suite still green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Documentation drift | Reviewer trust depends on REQUIREMENTS.md + codebase agreement |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-10-01 | Repudiation | Reviewer sees inconsistent prefetch value across docs and code | mitigate | Tasks 1 + 2 sync REQUIREMENTS.md to D-26 / D-08 / D-09. |
| T-05-10-02 | Tampering | Doc edit accidentally touches a code-relevant block | mitigate | Task 3 runs full suite + mypy + ruff; bounded scope of Tasks 1+2 is two specific lines. |
</threat_model>

<verification>
- `grep -q 'prefetch_count=10' .planning/REQUIREMENTS.md`
- `grep -c 'x-death' .planning/REQUIREMENTS.md | grep -v '^#'` returns 0
- `grep -c 'prefetch=20' .planning/REQUIREMENTS.md | grep -v '^#'` returns 0
- `uv run pytest -q` exits 0
- `uv run mypy src tests` exits 0
- `uv run ruff check src tests` exits 0
- Manual reviewer pass: read BM-09 and BM-11 in REQUIREMENTS.md and confirm they reflect the implemented behaviour.
</verification>

<success_criteria>
- BM-09 wording matches D-26 (prefetch_count=10 via Channel)
- BM-11 wording matches D-08 / D-09 (tenacity in-handler; poison → DLQ immediately; nack(requeue=True) never used)
- DLX name corrected to `bsw.events.dlx`
- Full suite stays green
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-10-requirements-doc-sync-SUMMARY.md` documenting: REQUIREMENTS.md before/after diff for BM-09 and BM-11, grep verification outputs, and confirmation that suite + linters stayed green.
</output>
