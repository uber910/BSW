---
phase: 06-reconciliation-job
plan: 03
type: execute
wave: 1
depends_on: [01, 02]
files_modified:
  - src/bet_maker/schemas/bets.py
  - alembic/versions/20260518_0003_bet_status_cancelled.py
  - tests/bet_maker/migrations/test_0003_cancelled.py
autonomous: true
requirements: [BM-12]
tags: [enum, alembic, autocommit-block, cancelled]

must_haves:
  truths:
    - "BetStatus.CANCELLED exists in Python enum as value 'cancelled'"
    - "Alembic 0003 migration adds 'cancelled' to PG bet_status ENUM"
    - "Migration uses op.get_context().autocommit_block() to escape the migration transaction"
    - "alembic upgrade head can be rerun without error (IF NOT EXISTS)"
    - "Existing Bet ORM, BetStatus.PENDING/WON/LOST untouched"
  artifacts:
    - path: "src/bet_maker/schemas/bets.py"
      provides: "BetStatus.CANCELLED = 'cancelled' enum member"
      contains: "CANCELLED"
    - path: "alembic/versions/20260518_0003_bet_status_cancelled.py"
      provides: "PG ALTER TYPE adding 'cancelled' value"
      contains: "autocommit_block"
    - path: "tests/bet_maker/migrations/test_0003_cancelled.py"
      provides: "real assertions for the migration (replaces Wave-0 stub)"
      contains: "ADD VALUE"
  key_links:
    - from: "src/bet_maker/schemas/bets.py BetStatus"
      to: "PG bet_status ENUM (via models/bet.py SqlEnum)"
      via: "string-valued Python enum maps 1:1 to PG ENUM labels"
      pattern: "CANCELLED = \"cancelled\""
    - from: "alembic 0003"
      to: "alembic 0002 (down_revision chain)"
      via: "down_revision = '0002_bets_settled_columns'"
      pattern: "down_revision = \"0002_bets_settled_columns\""
---

<objective>
Add the fourth bet-status value `CANCELLED` to both the Python `BetStatus` enum AND the PostgreSQL native ENUM `bet_status`, behind a properly transactional-escaped Alembic migration. After this plan:

- `BetStatus.CANCELLED.value == "cancelled"` (lower-case to match RESEARCH.md Pattern 4 and existing migration 0002 style).
- `alembic upgrade head` succeeds against a fresh DB AND against a DB already at revision 0003 (idempotent).
- The migration uses `op.get_context().autocommit_block()` — the critical pitfall from RESEARCH.md Pattern 4 / Pitfall 1, because PostgreSQL forbids `ALTER TYPE ... ADD VALUE` inside a transaction block, and Alembic's async env wraps every migration in one.
- The existing `Bet` ORM is untouched — SQLAlchemy 2.0 with a string-valued Python enum auto-accepts the new label without re-creating the type (RESEARCH.md Assumption A2; we will verify via the post-migration test).
- Phase 5 settled tests must continue to pass (zero regression on `tests/bet_maker/test_settle.py`).

Purpose: This is the **only** plan in Phase 6 that touches the data layer schema. All downstream interactors / repositories / reconciler logic assume `BetStatus.CANCELLED` exists. Splitting this from settings (06-04) and repo (06-05) lets all three Wave 1 plans run in parallel — they have no overlapping files.

Output: One Python enum value added, one Alembic migration file added, one Wave-0 stub turned into real assertions.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/06-reconciliation-job/06-CONTEXT.md
@.planning/phases/06-reconciliation-job/06-RESEARCH.md
@src/bet_maker/schemas/bets.py
@alembic/versions/20260515_0001_bets_initial.py
@alembic/versions/20260518_0002_bets_settled_columns.py
@tests/bet_maker/migrations/test_0003_cancelled.py
</context>

<interfaces>
Existing BetStatus shape (`src/bet_maker/schemas/bets.py`):
```python
class BetStatus(str, Enum):
    PENDING = "PENDING"
    WON = "WON"
    LOST = "LOST"
```

Note: existing values are UPPER-case (PENDING/WON/LOST) and the PG ENUM was created with those exact labels in migration 0001 (`postgresql.ENUM("PENDING", "WON", "LOST", name="bet_status", ...)`).

**However**, CONTEXT.md D-03 and RESEARCH.md Pattern 4 both spell the new value as `"cancelled"` (lower-case). This is intentional inconsistency we must NOT silently fix:

- RESEARCH.md line 277 → `ALTER TYPE betstatus ADD VALUE IF NOT EXISTS 'cancelled'`
- CONTEXT.md D-03 → `CANCELLED = "cancelled"`

But the existing ENUM type is named `bet_status` (snake_case), NOT `betstatus`. RESEARCH.md has a typo there. The migration MUST target the real type name `bet_status` (verify from migration 0001).

**Decision (per D-03 verbatim — "CANCELLED = 'cancelled'")**: use lower-case `"cancelled"` for the new value. This creates a mixed-case ENUM (`PENDING`, `WON`, `LOST`, `cancelled`) but matches CONTEXT.md verbatim and the implementer's intent (cancel is a recovery status, distinct in naming). Document this discrepancy in the migration docstring.

Existing migration patterns:
```python
# 0001 — declarative ENUM create + checkfirst
bet_status = postgresql.ENUM("PENDING", "WON", "LOST", name="bet_status", create_type=False)
bet_status.create(op.get_bind(), checkfirst=True)

# 0002 — straight add_column, no autocommit needed
op.add_column("bets", sa.Column("settled_via", sa.Text(), nullable=True))
```

Alembic context API used here (RESEARCH.md Pattern 4):
```python
with op.get_context().autocommit_block():
    op.execute("ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'")
```
</interfaces>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add BetStatus.CANCELLED to the Python enum</name>
  <files>src/bet_maker/schemas/bets.py</files>
  <read_first>
    - src/bet_maker/schemas/bets.py (full file — to confirm `class BetStatus(str, Enum)` Python-3.10 idiom)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-03 (verbatim string value)
  </read_first>
  <behavior>
    - BetStatus exposes a fourth member named `CANCELLED` whose value is the string `"cancelled"` (lower-case — D-03 verbatim).
    - The existing three members keep their exact value strings: `PENDING="PENDING"`, `WON="WON"`, `LOST="LOST"`. They are NOT modified.
    - The class docstring is extended with a single line: "CANCELLED -- recovery status: bet flipped by reconciler when line-provider returns 404 for the event (D-03, Phase 6). Lower-case value is intentional (distinct from terminal-state set) and matches Alembic 0003 ALTER TYPE."
    - mypy strict-mode: no type errors introduced.
    - The enum still inherits `(str, Enum)` — not `StrEnum` (3.11+).
  </behavior>
  <action>
    Use Edit tool to:

    1. After the `LOST = "LOST"` line, add `CANCELLED = "cancelled"` (note exact lower-case).
    2. Update the docstring inside `class BetStatus`:
       - Below the existing `LOST -- event finished with the opposite outcome.` line, add:
         `CANCELLED -- recovery: bet flipped by reconciler when line-provider returns 404 (D-03 Phase 6).`
       - At the end of the docstring (just before the closing `"""`), keep the existing note about P2 D-20 locked-style; do not delete.

    Do NOT touch:
    - The `Amount` Annotated type
    - `BetCreate`, `BetRead`
    - The `quantize_amount` import

    Final shape of the enum body:
    ```python
    class BetStatus(str, Enum):
        """... (existing docstring, with the new CANCELLED line appended) ..."""

        PENDING = "PENDING"
        WON = "WON"
        LOST = "LOST"
        CANCELLED = "cancelled"
    ```
  </action>
  <verify>
    <automated>grep -c 'CANCELLED = "cancelled"' src/bet_maker/schemas/bets.py && uv run python -c "from bet_maker.schemas.bets import BetStatus; assert BetStatus.CANCELLED.value == 'cancelled'; assert {s.value for s in BetStatus} == {'PENDING','WON','LOST','cancelled'}" && uv run mypy src/bet_maker/schemas/bets.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -E '^\s+CANCELLED = "cancelled"' src/bet_maker/schemas/bets.py | wc -l` == 1
    - `grep -cE '^\s+(PENDING|WON|LOST|CANCELLED) =' src/bet_maker/schemas/bets.py` == 4
    - `uv run python -c "from bet_maker.schemas.bets import BetStatus; print(sorted(s.value for s in BetStatus))"` outputs `['LOST', 'PENDING', 'WON', 'cancelled']`
    - `uv run mypy src/bet_maker/` exits 0 (no new strict-mode errors)
    - `uv run ruff check src/bet_maker/schemas/bets.py` exits 0
    - Existing Phase 3-5 tests still green: `uv run pytest -x -q tests/bet_maker/test_schemas.py tests/bet_maker/test_models.py tests/bet_maker/test_settle.py` exits 0
  </acceptance_criteria>
  <done>BetStatus has exactly four members; mypy strict clean; existing schema/model/settle tests still pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create Alembic migration 0003_bet_status_cancelled with autocommit_block</name>
  <files>alembic/versions/20260518_0003_bet_status_cancelled.py, tests/bet_maker/migrations/test_0003_cancelled.py</files>
  <read_first>
    - alembic/versions/20260518_0002_bets_settled_columns.py (immediate predecessor — confirm revision id format)
    - alembic/versions/20260515_0001_bets_initial.py (confirm PG ENUM type name is `bet_status`)
    - .planning/phases/06-reconciliation-job/06-RESEARCH.md §Pattern 4 + Code Examples (Alembic 0003 reference implementation)
    - .planning/phases/06-reconciliation-job/06-CONTEXT.md §Decisions D-03 (locks the value to lower-case 'cancelled')
    - tests/bet_maker/migrations/test_0003_cancelled.py (Wave-0 stub created in Plan 06-02 — three method names already declared)
    - tests/conftest.py (apply_migrations runs `alembic upgrade head` twice — idempotency is already enforced at fixture level)
  </read_first>
  <behavior>
    - Running `alembic upgrade head` against a DB at revision 0002 succeeds and ends at revision 0003.
    - Running `alembic upgrade head` a second time is a no-op (the `IF NOT EXISTS` clause guarantees this).
    - The PG enum `bet_status` afterwards contains exactly four labels: `PENDING`, `WON`, `LOST`, `cancelled` (queryable via `SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = 'bet_status' ORDER BY enumsortorder`).
    - Inserting a Bet with `status=BetStatus.CANCELLED` succeeds after the migration. (Verified indirectly in Plan 06-06 cancel-interactor tests; here we only assert the enum surface.)
    - `op.get_context().autocommit_block()` is used. Without it, `psycopg2.errors.ActiveSqlTransaction` / `asyncpg.exceptions.ActiveSQLTransactionError` is raised. We will verify the source contains the construct.
    - `downgrade()` is a documented no-op (PG does not support `DROP VALUE` from an ENUM without recreating the type — out of scope for a test task).
  </behavior>
  <action>
    Step A — Write the migration file `alembic/versions/20260518_0003_bet_status_cancelled.py`:

    ```python
    """bet_status -- add CANCELLED value

    Phase 6 / D-03: extend PG bet_status ENUM with a fourth value 'cancelled'.
    Reconciler (Plan 06-07) flips bets to status='cancelled' when line-provider
    returns 404 for an event_id (event deleted / LP recreated).

    autocommit_block (RESEARCH.md Pattern 4 / Pitfall 1): PostgreSQL forbids
    ALTER TYPE ... ADD VALUE inside a transaction block; Alembic's async env
    wraps every migration in a transaction. op.get_context().autocommit_block()
    commits the surrounding transaction, runs the DDL with autocommit, and
    restarts a fresh transaction for any subsequent statements.

    Idempotency: IF NOT EXISTS clause (PG 9.6+) makes rerun safe.
    Downgrade: PG does not support DROP VALUE without recreating the type;
    intentionally no-op for the test-task scope.

    Note on value casing: existing labels are upper-case ('PENDING','WON','LOST').
    The new value 'cancelled' is lower-case per D-03 verbatim — distinct visual
    marker for the recovery status (cancelled != terminal outcome).

    Revision ID: 0003_bet_status_cancelled
    Revises: 0002_bets_settled_columns
    Create Date: 2026-05-18
    """

    from __future__ import annotations

    from alembic import op

    revision = "0003_bet_status_cancelled"
    down_revision = "0002_bets_settled_columns"
    branch_labels = None
    depends_on = None


    def upgrade() -> None:
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'")


    def downgrade() -> None:
        # PostgreSQL does not support DROP VALUE from ENUM without recreating
        # the type. For a test task this is acceptable — downgrade past 0003
        # is unsupported. To roll back: drop the database, alembic upgrade head
        # to 0002 against a fresh DB.
        pass
    ```

    Step B — Replace the Wave-0 stub `tests/bet_maker/migrations/test_0003_cancelled.py` with real assertions. The class name and method names are already locked by Plan 06-02; just replace the `pytest.fail` bodies. The fixture `async_engine` (from `tests/conftest.py`) runs `apply_migrations` automatically, so by the time the test fixture yields, revision 0003 is applied.

    Replacement test bodies:

    ```python
    """Alembic migration 0003 — bet_status CANCELLED ADD VALUE assertions.

    Phase 6 / Plan 06-03 / BM-12.

    apply_migrations (tests/conftest.py) runs `alembic upgrade head` twice;
    by the time `async_engine` yields, revision 0003 is applied AND the
    rerun-idempotency has been verified at fixture setup. These tests assert
    the post-conditions visible to bet_maker code.
    """

    from __future__ import annotations

    import inspect
    from pathlib import Path

    import pytest
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncEngine


    @pytest.mark.asyncio(loop_scope="session")
    class TestMigration0003:
        async def test_alter_type_adds_cancelled_value(
            self, async_engine: AsyncEngine
        ) -> None:
            """The PG bet_status ENUM contains 'cancelled' after migration."""
            query = sa.text(
                "SELECT enumlabel FROM pg_enum "
                "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                "WHERE pg_type.typname = 'bet_status' "
                "ORDER BY enumsortorder"
            )
            async with async_engine.connect() as conn:
                rows = (await conn.execute(query)).scalars().all()
            assert "cancelled" in rows
            assert set(rows) == {"PENDING", "WON", "LOST", "cancelled"}

        async def test_migration_is_idempotent_on_rerun(
            self, async_engine: AsyncEngine
        ) -> None:
            """apply_migrations fixture runs upgrade head twice (tests/conftest.py).

            If the migration were not idempotent, fixture setup would have
            already raised. Reaching this test body is the proof — assert
            schema state is the post-migration shape.
            """
            query = sa.text(
                "SELECT count(*) FROM pg_enum "
                "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                "WHERE pg_type.typname = 'bet_status'"
            )
            async with async_engine.connect() as conn:
                count = (await conn.execute(query)).scalar_one()
            assert count == 4  # PENDING + WON + LOST + cancelled

        async def test_autocommit_block_used(self) -> None:
            """RESEARCH Pitfall 1: autocommit_block is REQUIRED for ALTER TYPE
            ADD VALUE; otherwise psycopg2/asyncpg raises ActiveSqlTransaction.

            Static-introspect the migration source — the public API
            `op.get_context().autocommit_block()` MUST appear inside upgrade().
            """
            migration_path = (
                Path(__file__).parents[3]
                / "alembic"
                / "versions"
                / "20260518_0003_bet_status_cancelled.py"
            )
            source = migration_path.read_text(encoding="utf-8")
            assert "autocommit_block" in source, (
                "Plan 06-03: migration 0003 must use op.get_context().autocommit_block()"
            )
            assert "ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'" in source
    ```

    Notes:
    - The session-scoped `async_engine` fixture is already in scope (parent conftest), and `apply_migrations` runs automatically before it yields. No additional fixture wiring is needed.
    - The third test reads the migration file from `alembic/versions/...` via `Path(__file__).parents[3]` (tests/bet_maker/migrations/test_*.py → 3 levels up = repo root).
    - The first and second tests use `async_engine.connect()` (read-only — no UoW needed).
  </action>
  <verify>
    <automated>uv run pytest -x -q tests/bet_maker/migrations/test_0003_cancelled.py && uv run pytest -x -q tests/bet_maker/test_settle.py tests/bet_maker/test_repositories.py</automated>
  </verify>
  <acceptance_criteria>
    - `test -f alembic/versions/20260518_0003_bet_status_cancelled.py`
    - `grep -c "autocommit_block" alembic/versions/20260518_0003_bet_status_cancelled.py` == 1
    - `grep -c "ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'cancelled'" alembic/versions/20260518_0003_bet_status_cancelled.py` == 1
    - `grep -c "down_revision = \"0002_bets_settled_columns\"" alembic/versions/20260518_0003_bet_status_cancelled.py` == 1
    - `uv run pytest -x -q tests/bet_maker/migrations/test_0003_cancelled.py` reports 3 passed
    - `uv run pytest -x -q tests/bet_maker/test_settle.py` still reports all prior Phase-5 tests passing (zero regression)
    - `uv run mypy src/bet_maker/ alembic/versions/20260518_0003_bet_status_cancelled.py` exits 0
    - `uv run ruff check alembic/versions/20260518_0003_bet_status_cancelled.py tests/bet_maker/migrations/` exits 0
    - The Wave-0 stub file no longer contains the string `Wave-0 stub`: `grep -c "Wave-0 stub" tests/bet_maker/migrations/test_0003_cancelled.py` == 0
  </acceptance_criteria>
  <done>Migration applied; 'cancelled' label present in PG enum; rerun idempotent; 3 migration tests green; zero regression on Phase 3-5 tests.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| migration runtime → PostgreSQL DDL | Alembic executes arbitrary SQL against the production DB; faulty migration can corrupt the schema |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-03-01 | Denial of Service (broken schema) | alembic/versions/0003 | mitigate | `IF NOT EXISTS` clause + `autocommit_block` — verified by the per-task test asserting both constructs in the migration source |
| T-06-03-02 | Tampering (silent enum drift) | PG bet_status ENUM | mitigate | Test 1 asserts the exact four-label set; any future migration that adds a 5th label without updating the test triggers a failure |
| T-06-03-03 | Repudiation (untracked DDL) | git history | mitigate | Migration file lives under `alembic/versions/` with revision metadata; git commit ties it to Plan 06-03 |
</threat_model>

<verification>
- `uv run pytest -x -q tests/bet_maker/` returns 0 (no regressions on Phase 3-5 tests, 3 new tests pass).
- `uv run python -c "from bet_maker.schemas.bets import BetStatus; assert BetStatus.CANCELLED"` exits 0.
- `uv run mypy src/` exits 0.
</verification>

<success_criteria>
- BetStatus enum has CANCELLED member with value "cancelled".
- Alembic 0003 migration file uses `autocommit_block()` + `IF NOT EXISTS`.
- All three migration tests pass; idempotency proven by fixture's double-upgrade.
- Phase 3-5 test suite untouched.
</success_criteria>

<output>
Create `.planning/phases/06-reconciliation-job/06-03-SUMMARY.md` with:
- Diff summary for `src/bet_maker/schemas/bets.py` (one line added).
- Path to new migration file with full content snapshot.
- `pytest -x -q tests/bet_maker/migrations/` output snippet.
</output>

## Decision Coverage

- D-03: Extend `BetStatus` enum with `CANCELLED = "cancelled"` + Alembic 0003 ALTER TYPE inside `op.get_context().autocommit_block()`.
