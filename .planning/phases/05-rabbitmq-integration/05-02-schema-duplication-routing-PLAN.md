---
phase: 05
plan: 02
type: execute
wave: 1
depends_on: [01]
files_modified:
  - src/bet_maker/schemas/messages.py
  - src/bet_maker/schemas/settle.py
  - src/bet_maker/messaging/__init__.py
  - src/bet_maker/messaging/routing.py
  - src/line_provider/messaging/__init__.py
  - src/line_provider/messaging/routing.py
  - tests/contract/test_event_finished_message_schema.py
autonomous: true
requirements: [BM-09]
must_haves:
  truths:
    - "EventFinishedMessage exists byte-for-byte identical in line_provider and bet_maker (D-28, SC#6)"
    - "Contract test fails on schema drift between services"
    - "Routing-key constants are Final[str] and live in messaging/routing.py per service (D-05)"
    - "SettleResult DTO is frozen + extra='forbid' (D-17)"
  artifacts:
    - path: "src/bet_maker/schemas/messages.py"
      provides: "duplicated EventFinishedMessage + EventTerminalState"
      contains: "class EventFinishedMessage"
    - path: "src/bet_maker/schemas/settle.py"
      provides: "SettleResult DTO (D-17)"
      contains: "class SettleResult"
    - path: "src/bet_maker/messaging/routing.py"
      provides: "EVENT_FINISHED_WIN/LOSE/WILDCARD constants"
      contains: "EVENT_FINISHED_WILDCARD"
    - path: "src/line_provider/messaging/routing.py"
      provides: "EVENT_FINISHED_WIN/LOSE constants"
      contains: "EVENT_FINISHED_WIN"
    - path: "tests/contract/test_event_finished_message_schema.py"
      provides: "schema-equality contract test"
      contains: "model_json_schema"
  key_links:
    - from: "tests/contract/test_event_finished_message_schema.py"
      to: "line_provider.schemas.messages + bet_maker.schemas.messages"
      via: "model_json_schema() byte equality"
      pattern: "model_json_schema"
---

<objective>
Establish the data contract for Phase 5. Three concerns:

1. **Schema duplication (D-28 / SC#6):** copy `EventFinishedMessage` + `EventTerminalState` byte-for-byte from `line_provider/schemas/messages.py` into `bet_maker/schemas/messages.py`. Zero cross-service imports.
2. **SettleResult DTO (D-17):** new immutable `extra="forbid"` Pydantic model used as the return type of the future `settle_bets_for_event` interactor (Plan 04) and as a structured-log payload shape (Plan 05).
3. **Routing constants (D-05):** new `messaging/` sub-package in both services with `Final[str]` constants for the three routing keys. Single source of truth — rename, never edit (R5).

The contract test from `tests/contract/test_event_finished_message_schema.py` flips from skip to a real `model_json_schema()` byte-equality assertion. CI fails on drift.

Pitfalls guarded: F7 (`extra="forbid"` + `schema_version` field re-used), F8 (routing keys single-sourced), R5 (constants are `Final[str]`).

Output: 4 new code files, 1 new __init__.py per service, 1 contract test promoted from stub to real.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/phases/05-rabbitmq-integration/05-CONTEXT.md
@.planning/phases/05-rabbitmq-integration/05-RESEARCH.md
@.planning/phases/05-rabbitmq-integration/05-PATTERNS.md
@src/line_provider/schemas/messages.py
@src/bet_maker/schemas/bets.py

<interfaces>
<!-- Source of truth: existing line-provider schema being copied -->

From src/line_provider/schemas/messages.py (byte-for-byte copy target):
```python
from __future__ import annotations
from decimal import Decimal
from enum import Enum
from typing import Annotated
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

class EventTerminalState(str, Enum):
    FINISHED_WIN = "FINISHED_WIN"
    FINISHED_LOSE = "FINISHED_LOSE"

class EventFinishedMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Annotated[int, Field(ge=1)] = 1
    event_id: UUID
    new_state: EventTerminalState
    coefficient: Annotated[Decimal, Field(gt=Decimal("0"), max_digits=8, decimal_places=2)]
    occurred_at: AwareDatetime
    correlation_id: str
```

From src/line_provider/interactors/set_event_state.py lines 19-22 (existing dict to replace later):
```python
_TERMINAL_TO_ROUTING: dict[EventState, str] = {
    EventState.FINISHED_WIN: "event.finished.win",
    EventState.FINISHED_LOSE: "event.finished.lose",
}
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Duplicate EventFinishedMessage into bet_maker/schemas/messages.py</name>
  <read_first>
    - src/line_provider/schemas/messages.py (full file — copy target)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/schemas/messages.py`
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-28
  </read_first>
  <action>
    Create `src/bet_maker/schemas/messages.py`. Copy `src/line_provider/schemas/messages.py` byte-for-byte. The ONLY allowed deviation is the module docstring noting this is the bet-maker duplicate (D-28: no cross-service imports). Do NOT add a new field, do NOT reorder fields, do NOT change `ConfigDict` flags, do NOT touch `Annotated[...]` constraints. Final file shape:

    ```python
    """EventFinishedMessage — byte-for-byte duplicate of line_provider/schemas/messages.py.

    D-28: schema duplication enforcement; no cross-service imports.
    CI contract test tests/contract/test_event_finished_message_schema.py enforces equality.
    """
    from __future__ import annotations

    from decimal import Decimal
    from enum import Enum
    from typing import Annotated
    from uuid import UUID

    from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


    class EventTerminalState(str, Enum):
        FINISHED_WIN = "FINISHED_WIN"
        FINISHED_LOSE = "FINISHED_LOSE"


    class EventFinishedMessage(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

        schema_version: Annotated[int, Field(ge=1)] = 1
        event_id: UUID
        new_state: EventTerminalState
        coefficient: Annotated[Decimal, Field(gt=Decimal("0"), max_digits=8, decimal_places=2)]
        occurred_at: AwareDatetime
        correlation_id: str
    ```

    No new dependencies, no new imports beyond what line-provider uses.
  </action>
  <verify>
    <automated>uv run python -c "import json; from line_provider.schemas.messages import EventFinishedMessage as L; from bet_maker.schemas.messages import EventFinishedMessage as B; assert json.dumps(L.model_json_schema(), sort_keys=True) == json.dumps(B.model_json_schema(), sort_keys=True), 'drift'; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/bet_maker/schemas/messages.py`
    - `grep -c "class EventFinishedMessage" src/bet_maker/schemas/messages.py` returns 1
    - `grep -c "class EventTerminalState" src/bet_maker/schemas/messages.py` returns 1
    - `grep -q 'ConfigDict(frozen=True, extra="forbid")' src/bet_maker/schemas/messages.py`
    - `grep -q 'schema_version: Annotated\[int, Field(ge=1)\] = 1' src/bet_maker/schemas/messages.py`
    - `grep -q 'from line_provider' src/bet_maker/schemas/messages.py` returns EMPTY (no cross-service import)
    - `uv run mypy src/bet_maker/schemas/messages.py` exits 0
  </acceptance_criteria>
  <done>Bet-maker has its own copy; CI contract test (Task 3) will lock equality going forward.</done>
</task>

<task type="auto">
  <name>Task 2: Create SettleResult DTO in src/bet_maker/schemas/settle.py</name>
  <read_first>
    - src/bet_maker/schemas/bets.py (`BetRead` Pydantic pattern reference)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-17
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/schemas/settle.py`
  </read_first>
  <action>
    Create `src/bet_maker/schemas/settle.py`. Per D-17 the DTO is the return type of `settle_bets_for_event` (Plan 04). Use `frozen=True, extra="forbid"` (constructed in Python code, not from ORM, so NOT `from_attributes=True`). Import `EventTerminalState` from the bet-maker copy (D-28 — same-service import only).

    ```python
    """SettleResult — return DTO of settle_bets_for_event interactor (D-17).

    Phase 5 / D-17 / D-13: shape returned by settle_bets_for_event so callers
    (consumer handler in Plan 05, reconciler in Phase 6) get a typed snapshot
    of which bets were settled and via which path.
    """
    from __future__ import annotations

    from datetime import datetime
    from typing import Literal
    from uuid import UUID

    from pydantic import BaseModel, ConfigDict

    from bet_maker.schemas.messages import EventTerminalState


    class SettleResult(BaseModel):
        """Immutable result of one settle_bets_for_event invocation.

        settled_count: number of rows flipped from PENDING to WON/LOST in this call.
                       0 = idempotent no-op (D-15/D-16).
        settled_bet_ids: list of bet ids that were settled in this call.
        settled_via: 'consumer' (Phase 5) or 'reconciler' (Phase 6).
        settled_at: Python-side timestamp filled by caller (PG fills the column
                    server-side via func.now() in the UPDATE statement — D-14).
        """

        model_config = ConfigDict(frozen=True, extra="forbid")

        event_id: UUID
        terminal_state: EventTerminalState
        settled_count: int
        settled_bet_ids: list[UUID]
        settled_via: Literal["consumer", "reconciler"]
        settled_at: datetime
    ```
  </action>
  <verify>
    <automated>uv run python -c "from bet_maker.schemas.settle import SettleResult; assert SettleResult.model_config.get('frozen') is True and SettleResult.model_config.get('extra') == 'forbid'; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/bet_maker/schemas/settle.py`
    - `grep -c "class SettleResult" src/bet_maker/schemas/settle.py` returns 1
    - `grep -q 'ConfigDict(frozen=True, extra="forbid")' src/bet_maker/schemas/settle.py`
    - `grep -q 'settled_via: Literal\["consumer", "reconciler"\]' src/bet_maker/schemas/settle.py`
    - `grep -q 'from bet_maker.schemas.messages import EventTerminalState' src/bet_maker/schemas/settle.py`
    - `uv run mypy src/bet_maker/schemas/settle.py` exits 0
  </acceptance_criteria>
  <done>SettleResult importable, frozen, forbids extra fields, ready for Plan 04 interactor.</done>
</task>

<task type="auto">
  <name>Task 3: Create messaging/routing.py constants in both services + new packages</name>
  <read_first>
    - src/line_provider/interactors/set_event_state.py lines 19-22 (existing dict to retire)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-05
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/messaging/routing.py` and §`src/line_provider/messaging/routing.py`
  </read_first>
  <action>
    Create FOUR new files. Both `messaging/__init__.py` are EMPTY (zero bytes). Both `routing.py` files contain identical `Final[str]` constants.

    File 1 — `src/bet_maker/messaging/__init__.py`: empty.

    File 2 — `src/bet_maker/messaging/routing.py`:
    ```python
    """AMQP routing-key constants — bet-maker consumer side (D-05).

    F8: single source of truth for routing keys; CI integration test
    asserts the binding bsw.events --event.finished.*--> bet_maker.events.finished
    exists at runtime. R5: rename, never edit — keep stability across deploys.
    """
    from __future__ import annotations

    from typing import Final

    EVENT_FINISHED_WIN: Final[str] = "event.finished.win"
    EVENT_FINISHED_LOSE: Final[str] = "event.finished.lose"
    EVENT_FINISHED_WILDCARD: Final[str] = "event.finished.*"
    ```

    File 3 — `src/line_provider/messaging/__init__.py`: empty.

    File 4 — `src/line_provider/messaging/routing.py`: byte-identical to bet-maker `routing.py`. Do NOT add `EVENT_FINISHED_WILDCARD` only on one side — keep all three constants in both files so the constants line up symmetrically (D-05). Module docstring may differ ("publisher side" vs "consumer side").

    Per D-05 the existing `_TERMINAL_TO_ROUTING` dict in `set_event_state.py` is left untouched in this plan (Plan 06 rewires `set_event_state.py` to import from the new module). This task creates the modules only; integration happens in Plan 06.
  </action>
  <verify>
    <automated>uv run python -c "from bet_maker.messaging.routing import EVENT_FINISHED_WIN as BW, EVENT_FINISHED_LOSE as BL, EVENT_FINISHED_WILDCARD as BWC; from line_provider.messaging.routing import EVENT_FINISHED_WIN as LW, EVENT_FINISHED_LOSE as LL, EVENT_FINISHED_WILDCARD as LWC; assert (BW, BL, BWC) == (LW, LL, LWC) == ('event.finished.win', 'event.finished.lose', 'event.finished.*'); print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `test -f src/bet_maker/messaging/__init__.py` and `test -f src/bet_maker/messaging/routing.py`
    - `test -f src/line_provider/messaging/__init__.py` and `test -f src/line_provider/messaging/routing.py`
    - `grep -c 'Final\[str\]' src/bet_maker/messaging/routing.py | grep -v '^#'` returns 3
    - `grep -c 'Final\[str\]' src/line_provider/messaging/routing.py | grep -v '^#'` returns 3
    - `grep -q 'EVENT_FINISHED_WILDCARD: Final\[str\] = "event.finished.\*"' src/bet_maker/messaging/routing.py`
    - `grep -q 'EVENT_FINISHED_WILDCARD: Final\[str\] = "event.finished.\*"' src/line_provider/messaging/routing.py`
    - `uv run mypy src/bet_maker/messaging src/line_provider/messaging` exits 0
    - `uv run ruff check src/bet_maker/messaging src/line_provider/messaging` exits 0
  </acceptance_criteria>
  <done>Both messaging sub-packages exist; constants importable from either service; mypy/ruff clean.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Promote contract test stub to real model_json_schema equality assertion</name>
  <read_first>
    - tests/contract/test_event_finished_message_schema.py (current stub from Plan 01)
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §Contract test (D-29)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`tests/contract/test_event_finished_message_schema.py`
  </read_first>
  <behavior>
    - Test "test_schemas_are_identical": `json.dumps(LP.model_json_schema(), sort_keys=True) == json.dumps(BM.model_json_schema(), sort_keys=True)` — passes ONLY if schemas match byte-for-byte.
    - Test "test_drift_is_detected_when_field_added": construct a subclass of `BMMessage` with an extra field, prove `model_json_schema()` differs (sanity check — not a regression test, just guards the assertion form itself).
    - Test "test_schema_version_field_is_present_with_default_1": both copies expose `schema_version` with default 1.
  </behavior>
  <action>
    Replace the stub file `tests/contract/test_event_finished_message_schema.py` with a real synchronous test module (no `@pytest.mark.asyncio` — pure schema comparison). Mirror the analog in PATTERNS.md §Contract test:

    ```python
    """Contract test: EventFinishedMessage must be byte-for-byte identical
    across line_provider and bet_maker (D-28, D-29 / SC#6).

    A failing test here means a developer modified one copy without
    updating the other — CI breaks the PR before deployment drift can
    occur in production.
    """
    from __future__ import annotations

    import json

    from bet_maker.schemas.messages import EventFinishedMessage as BMMessage
    from line_provider.schemas.messages import EventFinishedMessage as LPMessage


    def test_schemas_are_identical() -> None:
        lp_schema = json.dumps(LPMessage.model_json_schema(), sort_keys=True)
        bm_schema = json.dumps(BMMessage.model_json_schema(), sort_keys=True)
        assert lp_schema == bm_schema, (
            "EventFinishedMessage schema drift detected between line_provider "
            "and bet_maker — re-sync src/bet_maker/schemas/messages.py with "
            "src/line_provider/schemas/messages.py byte-for-byte (D-28)."
        )


    def test_schema_version_field_is_present_with_default_one() -> None:
        lp_fields = LPMessage.model_fields
        bm_fields = BMMessage.model_fields
        assert "schema_version" in lp_fields
        assert "schema_version" in bm_fields
        assert lp_fields["schema_version"].default == 1
        assert bm_fields["schema_version"].default == 1


    def test_extra_forbid_is_set_on_both() -> None:
        assert LPMessage.model_config.get("extra") == "forbid"
        assert BMMessage.model_config.get("extra") == "forbid"
    ```
  </action>
  <verify>
    <automated>uv run pytest tests/contract/test_event_finished_message_schema.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `uv run pytest tests/contract/test_event_finished_message_schema.py -x -q` exits 0 with 3 passed
    - `grep -q 'pytest.skip("Wave 0 stub' tests/contract/test_event_finished_message_schema.py` returns EMPTY (stub removed)
    - `grep -q 'model_json_schema()' tests/contract/test_event_finished_message_schema.py`
    - `grep -q 'sort_keys=True' tests/contract/test_event_finished_message_schema.py`
    - `uv run mypy tests/contract/test_event_finished_message_schema.py` exits 0
  </acceptance_criteria>
  <done>Contract test green; future drift across services causes CI failure.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Inter-service AMQP payload | Untrusted (line-provider could be compromised; bet-maker must validate strictly) |
| Routing-key constants | Internal contract — affects topology declarations and DLQ wiring |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-02-01 | Tampering | EventFinishedMessage payload from broker | mitigate | `ConfigDict(frozen=True, extra="forbid")` rejects extra/mutated fields; `schema_version` field validated by Plan 05 handler before any DB write (F7). |
| T-05-02-02 | Spoofing | A second service publishing fake EventFinishedMessage | accept | Single-tenant local docker-compose, AMQP guest/guest is fine for test task; Phase 7 will note this as out-of-scope hardening. |
| T-05-02-03 | Repudiation | Schema drift between services causing silent payload mismatch | mitigate | Plan 02 Task 4 contract test in CI; drift = failing PR test (D-29). |
| T-05-02-04 | Information disclosure | `correlation_id` includes sensitive request data | accept | correlation_id is a request UUID, not PII; structlog binding uses it for traceability (A7). |
</threat_model>

<verification>
- All 3 contract tests in `tests/contract/test_event_finished_message_schema.py` pass
- `uv run python -c "import line_provider.schemas.messages, bet_maker.schemas.messages, bet_maker.schemas.settle, bet_maker.messaging.routing, line_provider.messaging.routing"` exits 0
- `uv run mypy src tests` exits 0
- `uv run ruff check src tests` exits 0
- `grep -r "from line_provider" src/bet_maker` returns NO matches (no cross-service imports)
- `grep -r "from bet_maker" src/line_provider` returns NO matches
</verification>

<success_criteria>
- `EventFinishedMessage` byte-for-byte identical across services (validated by `model_json_schema()` sort_keys equality)
- `SettleResult` DTO available for Plan 04 interactor
- `messaging/routing.py` modules exist in both services with three `Final[str]` constants
- Contract test green (3 passed)
- No cross-service imports introduced
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-02-schema-duplication-routing-SUMMARY.md` documenting: byte-equality verification output, list of files added, routing-key constants table, and confirmation that no cross-service imports exist.
</output>
