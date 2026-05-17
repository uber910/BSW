---
phase: 05
plan: 03
type: execute
wave: 1
depends_on: [01]
files_modified:
  - src/bet_maker/models/bet.py
  - src/bet_maker/repositories/bets.py
  - alembic/versions/20260518_0002_bets_settled_columns.py
  - tests/bet_maker/test_repositories.py
  - tests/bet_maker/test_alembic.py
autonomous: true
requirements: [BM-10]
must_haves:
  truths:
    - "Bet ORM exposes settled_at: Mapped[datetime | None] and settled_via: Mapped[str | None] columns (D-13)"
    - "Alembic upgrade head adds settled_at + settled_via columns; downgrade reverses; rerun is idempotent"
    - "BetRepository.get_pending_locked(event_id) returns list[Bet] using FOR UPDATE SKIP LOCKED + status=PENDING filter (R3 / D-12)"
    - "Repository never commits or rolls back — UoW owns the transaction (Anti-Pattern 1 preserved)"
  artifacts:
    - path: "src/bet_maker/models/bet.py"
      provides: "Bet ORM with two new nullable columns"
      contains: "settled_at"
    - path: "src/bet_maker/repositories/bets.py"
      provides: "get_pending_locked method"
      contains: "with_for_update(skip_locked=True)"
    - path: "alembic/versions/20260518_0002_bets_settled_columns.py"
      provides: "schema migration"
      contains: "0002_bets_settled_columns"
  key_links:
    - from: "src/bet_maker/repositories/bets.py"
      to: "src/bet_maker/models/bet.py"
      via: "select(Bet).with_for_update(skip_locked=True)"
      pattern: "with_for_update.*skip_locked=True"
    - from: "src/bet_maker/repositories/bets.py"
      to: "src/bet_maker/schemas/bets.py"
      via: "BetStatus.PENDING filter"
      pattern: "Bet.status == BetStatus.PENDING"
---

<objective>
Provide the persistence layer Plan 04 (settle interactor) will sit on top of:

1. **ORM extension (D-13):** add `settled_at` (TIMESTAMPTZ nullable) and `settled_via` (Text nullable) columns to the `Bet` model so the settle interactor can record both. PG fills `settled_at` via `func.now()` in the UPDATE statement (D-14); `settled_via` is 'consumer' or 'reconciler' Literal-typed.
2. **Alembic migration:** revision `0002_bets_settled_columns` adds both columns reversibly; rerun idempotent.
3. **Repository method (R3 / D-12):** `BetRepository.get_pending_locked(event_id) -> list[Bet]` issues `SELECT * FROM bets WHERE event_id=:id AND status='PENDING' FOR UPDATE SKIP LOCKED`. This is THE idempotency mechanism for both Phase 5 consumer and Phase 6 reconciler — second caller gets 0 rows by construction.

Pitfalls guarded:
- **R3 (consumer/reconciler race double-update):** `with_for_update(skip_locked=True) + WHERE status='PENDING'` — second caller observes 0 rows, no UPDATE issued, no deadlock.
- **Anti-Pattern 1 (repository commits):** new method only issues SELECT, no flush/commit — UoW still owns the transaction.

Output: Bet model gains 2 columns; new repository method; new Alembic migration; tests for both.
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
@src/bet_maker/models/bet.py
@src/bet_maker/repositories/bets.py
@src/bet_maker/schemas/bets.py
@alembic/versions/20260515_0001_bets_initial.py
@tests/conftest.py
@tests/bet_maker/test_repositories.py
@tests/bet_maker/test_alembic.py

<interfaces>
<!-- Existing pattern reference: current Bet model + repository -->

From src/bet_maker/models/bet.py (current — extend with two new columns):
```python
class Bet(Base):
    __tablename__ = "bets"
    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[BetStatus] = mapped_column(SqlEnum(BetStatus, name="bet_status", create_type=True), nullable=False, default=BetStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
```

From src/bet_maker/repositories/bets.py (current — add get_pending_locked):
```python
class BetRepository:
    def __init__(self, session: AsyncSession) -> None: self._session = session
    def add(self, bet: Bet) -> None: self._session.add(bet)
    async def get_by_id(self, bet_id: UUID) -> Bet | None: ...
```

From src/bet_maker/schemas/bets.py:
```python
class BetStatus(str, Enum):
    PENDING = "PENDING"; WON = "WON"; LOST = "LOST"
```

From alembic/versions/20260515_0001_bets_initial.py (revision string format and op idioms):
```python
revision = "0001_bets_initial"
down_revision = None
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add settled_at + settled_via columns to Bet ORM</name>
  <read_first>
    - src/bet_maker/models/bet.py (full file)
    - .planning/phases/05-rabbitmq-integration/05-CONTEXT.md D-13 / D-14
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/models/bet.py`
  </read_first>
  <action>
    Extend `src/bet_maker/models/bet.py`. Add `import sqlalchemy as sa` near the existing `from sqlalchemy import ...` line. After the existing `updated_at` mapped_column at line 70-74, APPEND two new column declarations BEFORE the closing of the class body:

    ```python
    settled_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    settled_via: Mapped[str | None] = mapped_column(
        sa.Text(),
        nullable=True,
    )
    ```

    Add a docstring update inside the class docstring (after the existing D-09 bullets) noting D-13 / D-14:
    - `settled_at: Mapped[datetime | None] — server-filled by PG func.now() in the settle UPDATE statement; NULL while bet is PENDING (D-13/D-14).`
    - `settled_via: Mapped[str | None] — 'consumer' (Phase 5) or 'reconciler' (Phase 6); NULL while PENDING.`

    Do NOT add `server_default` — settled_* are NULL by default (Pitfall: a default of "now()" would back-fill historical PENDING bets with bogus settle times). Do NOT add any `Index` — Phase 5 traffic does not need it for a test task.
  </action>
  <verify>
    <automated>uv run python -c "from bet_maker.models.bet import Bet; cols = {c.name: c for c in Bet.__table__.columns}; assert 'settled_at' in cols and cols['settled_at'].nullable is True; assert 'settled_via' in cols and cols['settled_via'].nullable is True; print('ok')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'settled_at: Mapped\[datetime | None\]' src/bet_maker/models/bet.py`
    - `grep -q 'settled_via: Mapped\[str | None\]' src/bet_maker/models/bet.py`
    - `grep -q 'sa.DateTime(timezone=True)' src/bet_maker/models/bet.py`
    - `grep -q 'sa.Text()' src/bet_maker/models/bet.py`
    - `grep -q 'import sqlalchemy as sa' src/bet_maker/models/bet.py`
    - `grep -c 'server_default' src/bet_maker/models/bet.py | grep -v '^#'` returns 2 (only the original created_at/updated_at, NOT settled_at)
    - `uv run mypy src/bet_maker/models/bet.py` exits 0
  </acceptance_criteria>
  <done>Bet model has both new nullable columns; mypy clean; no test impact yet (Alembic migration in Task 2 closes the loop).</done>
</task>

<task type="auto">
  <name>Task 2: Create Alembic migration 0002_bets_settled_columns + rehearse upgrade/downgrade/upgrade</name>
  <read_first>
    - alembic/versions/20260515_0001_bets_initial.py (header style + op idioms)
    - .planning/phases/05-rabbitmq-integration/05-RESEARCH.md §Alembic Migration (D-13)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`alembic/versions/20260518_0002_bets_settled_columns.py`
  </read_first>
  <action>
    Create `alembic/versions/20260518_0002_bets_settled_columns.py`. Mirror the Phase 3 file naming convention (`YYYYMMDD_NNNN_snake_description.py`). Use the EXACT shape from PATTERNS.md §Alembic Migration:

    ```python
    """bets settled columns -- add settled_at + settled_via

    Phase 5 / D-13: observability columns for bet settlement.
    settled_at: when the bet was settled (PG func.now() filled by UPDATE
    statement inside settle_bets_for_event interactor — D-14).
    settled_via: 'consumer' (Phase 5) or 'reconciler' (Phase 6).

    Revision ID: 0002_bets_settled_columns
    Revises: 0001_bets_initial
    Create Date: 2026-05-18
    """

    from __future__ import annotations

    import sqlalchemy as sa
    from alembic import op

    revision = "0002_bets_settled_columns"
    down_revision = "0001_bets_initial"
    branch_labels = None
    depends_on = None


    def upgrade() -> None:
        op.add_column(
            "bets",
            sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            "bets",
            sa.Column("settled_via", sa.Text(), nullable=True),
        )


    def downgrade() -> None:
        op.drop_column("bets", "settled_via")
        op.drop_column("bets", "settled_at")
    ```

    No ENUM creation (settled_via is Text, not enum). Do NOT add `server_default`. Do NOT add indexes.

    After writing the file, manually rehearse the upgrade-downgrade-upgrade cycle against a fresh test PG (the verify command does this automatically using testcontainers via the existing `apply_migrations` fixture infrastructure — see Task 3).
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker/test_alembic.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `test -f alembic/versions/20260518_0002_bets_settled_columns.py`
    - `grep -q 'revision = "0002_bets_settled_columns"' alembic/versions/20260518_0002_bets_settled_columns.py`
    - `grep -q 'down_revision = "0001_bets_initial"' alembic/versions/20260518_0002_bets_settled_columns.py`
    - `grep -q "op.add_column(.*settled_at" alembic/versions/20260518_0002_bets_settled_columns.py`
    - `grep -q "op.add_column(.*settled_via" alembic/versions/20260518_0002_bets_settled_columns.py`
    - `grep -q "op.drop_column.*settled_via" alembic/versions/20260518_0002_bets_settled_columns.py` and `grep -q "op.drop_column.*settled_at" alembic/versions/20260518_0002_bets_settled_columns.py`
    - `uv run pytest tests/bet_maker/test_alembic.py -x -q` exits 0 (Task 3 adds the upgrade/downgrade rehearsal test)
    - `uv run mypy alembic/versions/20260518_0002_bets_settled_columns.py` exits 0 (the existing per-file-ignore `"alembic/versions/*.py" = ["E501", "N999"]` covers ruff)
  </acceptance_criteria>
  <done>Migration file present; ORM and DB schema stay in sync; downgrade reverses cleanly.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Add upgrade/downgrade/upgrade rehearsal test + get_pending_locked repository test</name>
  <read_first>
    - tests/bet_maker/test_alembic.py (existing rehearsal — extend it)
    - tests/bet_maker/test_repositories.py (existing TestRuntime class shape)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/repositories/bets.py (modified)`
  </read_first>
  <behavior>
    - Test "test_0002_upgrade_downgrade_upgrade_idempotent": from migrated head, downgrade `-1`, upgrade `head`, and confirm `bets.settled_at` and `bets.settled_via` columns exist via PG `information_schema.columns`.
    - Test "test_get_pending_locked_returns_only_pending_for_event_id": insert 2 PENDING bets for event_id_A, 1 WON bet for event_id_A, 1 PENDING bet for event_id_B; assert `get_pending_locked(event_id_A)` returns exactly 2 rows (only PENDING + matching event_id).
    - Test "test_get_pending_locked_uses_for_update_skip_locked_compiled_sql": compile the SQLAlchemy expression and assert the SQL string contains `FOR UPDATE SKIP LOCKED`.
    - Test "test_get_pending_locked_empty_when_no_pending": insert 1 WON bet for event_id; assert `get_pending_locked(event_id)` returns `[]`.
  </behavior>
  <action>
    Step A — Extend `tests/bet_maker/test_alembic.py`. Add ONE new test method to the existing test class (read the current file first to find the class). The test must use the existing `apply_migrations`/`async_engine` fixtures from root `tests/conftest.py`. After upgrading to head, downgrading `-1`, and upgrading back to head, query `information_schema.columns` to assert both new columns exist:

    ```python
    @pytest.mark.asyncio(loop_scope="session")
    async def test_0002_upgrade_downgrade_upgrade_columns_present(
        self,
        async_engine: AsyncEngine,
        pg_dsn: str,
    ) -> None:
        """D-13 migration must round-trip: upgrade -> downgrade -1 -> upgrade head;
        after final upgrade, settled_at and settled_via columns are present in bets."""
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", pg_dsn)
        command.downgrade(alembic_cfg, "-1")
        command.upgrade(alembic_cfg, "head")
        async with async_engine.connect() as conn:
            rows = (
                await conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'bets' "
                        "AND column_name IN ('settled_at', 'settled_via')"
                    )
                )
            ).all()
        names = {r[0] for r in rows}
        assert names == {"settled_at", "settled_via"}
    ```

    Import shape: add `import sqlalchemy as sa` + `from alembic import command` + `from alembic.config import Config` to the top if not present. Use the EXACT existing test-class structure (`@pytest.mark.asyncio(loop_scope="session")`).

    Step B — Add a `TestGetPendingLocked` class to `tests/bet_maker/test_repositories.py`. Mirror the existing `TestRuntime` class shape. The three tests above:

    ```python
    @pytest.mark.asyncio(loop_scope="session")
    class TestGetPendingLocked:
        async def test_returns_only_pending_for_matching_event_id(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_a, event_b = uuid4(), uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                session.add(Bet(event_id=event_a, amount=Decimal("10.00"), status=BetStatus.PENDING))
                session.add(Bet(event_id=event_a, amount=Decimal("20.00"), status=BetStatus.PENDING))
                session.add(Bet(event_id=event_a, amount=Decimal("30.00"), status=BetStatus.WON))
                session.add(Bet(event_id=event_b, amount=Decimal("40.00"), status=BetStatus.PENDING))
            async with session_factory() as session:
                repo = BetRepository(session)
                rows = await repo.get_pending_locked(event_a)
            assert len(rows) == 2
            assert all(b.event_id == event_a and b.status == BetStatus.PENDING for b in rows)

        async def test_compiled_sql_uses_for_update_skip_locked(
            self, session_factory: async_sessionmaker
        ) -> None:
            from sqlalchemy import select
            from sqlalchemy.dialects import postgresql
            stmt = (
                select(Bet)
                .where(Bet.event_id == uuid4(), Bet.status == BetStatus.PENDING)
                .with_for_update(skip_locked=True)
            )
            compiled = stmt.compile(dialect=postgresql.dialect())
            assert "FOR UPDATE SKIP LOCKED" in str(compiled).upper().replace("\n", " ")

        async def test_empty_when_only_settled_bets(
            self, session_factory: async_sessionmaker
        ) -> None:
            event_id = uuid4()
            async with session_factory.begin() as session:  # type: ignore[union-attr]
                session.add(Bet(event_id=event_id, amount=Decimal("10.00"), status=BetStatus.WON))
            async with session_factory() as session:
                repo = BetRepository(session)
                rows = await repo.get_pending_locked(event_id)
            assert rows == []
    ```

    Imports to add to `test_repositories.py`: `from decimal import Decimal`, `from uuid import uuid4`, `from sqlalchemy.ext.asyncio import async_sessionmaker`, `from bet_maker.models.bet import Bet`, `from bet_maker.repositories.bets import BetRepository`, `from bet_maker.schemas.bets import BetStatus`. (Some may already be present — reuse the existing ones.) Add `import pytest` if not present.
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker/test_alembic.py tests/bet_maker/test_repositories.py -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'test_0002_upgrade_downgrade_upgrade_columns_present' tests/bet_maker/test_alembic.py`
    - `grep -q 'class TestGetPendingLocked' tests/bet_maker/test_repositories.py`
    - `grep -q 'with_for_update(skip_locked=True)' tests/bet_maker/test_repositories.py`
    - `grep -q 'FOR UPDATE SKIP LOCKED' tests/bet_maker/test_repositories.py`
    - `uv run pytest tests/bet_maker/test_alembic.py tests/bet_maker/test_repositories.py -x -q` exits 0
    - `uv run mypy src/bet_maker/repositories tests/bet_maker/test_alembic.py tests/bet_maker/test_repositories.py` exits 0
  </acceptance_criteria>
  <done>Repository + ORM + migration verified together against the real PG testcontainer; SKIP LOCKED SQL form is asserted at compile-time.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Implement BetRepository.get_pending_locked(event_id) -> list[Bet]</name>
  <read_first>
    - src/bet_maker/repositories/bets.py (full file)
    - .planning/phases/05-rabbitmq-integration/05-PATTERNS.md §`src/bet_maker/repositories/bets.py (modified)`
  </read_first>
  <behavior>
    - Method signature: `async def get_pending_locked(self, event_id: UUID) -> list[Bet]:`
    - Body: `await self._session.execute(select(Bet).where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING).with_for_update(skip_locked=True))` then `list(result.scalars().all())`.
    - No commit, no rollback, no flush — UoW owns the transaction (Anti-Pattern 1 preserved).
    - The existing TestGetPendingLocked class (created in Task 3) covers behavior.
  </behavior>
  <action>
    Extend `src/bet_maker/repositories/bets.py`. Append a new method to `BetRepository` after `get_by_id`. Add `from bet_maker.schemas.bets import BetStatus` to imports if not present.

    ```python
    async def get_pending_locked(self, event_id: UUID) -> list[Bet]:
        """Lock and return all PENDING bets for an event_id (R3 / D-12).

        SELECT * FROM bets
        WHERE event_id = :event_id AND status = 'PENDING'
        FOR UPDATE SKIP LOCKED

        This is the idempotency mechanism for both Plan 05 consumer and Phase 6
        reconciler. Two concurrent callers against the same event_id: SKIP LOCKED
        ensures exactly one acquires the rows; the other observes 0 rows and
        takes the settle.noop path (D-16). Status filter ensures redelivery
        after a prior successful settle is also a 0-row no-op.

        Row locks are released when the enclosing UoW commits (async with uow exits).
        D-18: PG default READ COMMITTED isolation is sufficient — the row lock plus
        status filter provide all needed serialisability without raising isolation.

        Anti-Pattern 1 preserved: method only SELECTs; no flush, no commit.
        """
        result = await self._session.execute(
            select(Bet)
            .where(Bet.event_id == event_id, Bet.status == BetStatus.PENDING)
            .with_for_update(skip_locked=True)
        )
        return list(result.scalars().all())
    ```
  </action>
  <verify>
    <automated>uv run pytest tests/bet_maker/test_repositories.py::TestGetPendingLocked -x -q</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q 'async def get_pending_locked' src/bet_maker/repositories/bets.py`
    - `grep -q 'with_for_update(skip_locked=True)' src/bet_maker/repositories/bets.py`
    - `grep -q 'Bet.status == BetStatus.PENDING' src/bet_maker/repositories/bets.py`
    - `grep -q 'from bet_maker.schemas.bets import BetStatus' src/bet_maker/repositories/bets.py`
    - `grep -c 'commit\|rollback' src/bet_maker/repositories/bets.py | grep -v '^#'` returns 0 — Anti-Pattern 1 preserved
    - `uv run pytest tests/bet_maker/test_repositories.py::TestGetPendingLocked -x -q` exits 0 (3 tests pass)
    - `uv run mypy src/bet_maker/repositories/bets.py` exits 0
  </acceptance_criteria>
  <done>Repository method live; all 3 TestGetPendingLocked cases pass; SQL form asserted; idempotency primitive ready for Plan 04.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Concurrent settle callers | Consumer + reconciler may run against the same event_id concurrently — DB must serialise them deterministically |
| DB migration | Production data; any mistake in down/up is unrecoverable |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-03-01 | Tampering | Concurrent UPDATE race (consumer vs reconciler) | mitigate | `with_for_update(skip_locked=True) + WHERE status='PENDING'` (Task 4) — second caller sees 0 rows by construction; integration race test in Plan 04 (R3). |
| T-05-03-02 | Denial of service | Long-held lock on settled_at/settled_via columns | mitigate | UoW commits immediately after UPDATE; row locks released; no `FOR UPDATE` outside the settle critical section. |
| T-05-03-03 | Tampering | Schema-drift after downgrade leaves NULL columns visible | accept | `nullable=True` for both columns is the intended state for PENDING bets; ORM correctly types them as `Mapped[X | None]`. |
| T-05-03-04 | Repudiation | settled_via is free-text; could be falsified by a malicious caller | mitigate | Caller is only the settle_bets_for_event interactor (Plan 04) where settled_via is a `Literal["consumer", "reconciler"]` typed parameter — no path for arbitrary strings to reach the DB. |
</threat_model>

<verification>
- `uv run pytest tests/bet_maker/test_alembic.py tests/bet_maker/test_repositories.py -x -q` exits 0
- `uv run pytest -q` exits 0 (no regressions in full suite)
- `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` (against test PG) succeeds — verified via Task 3 test
- `uv run mypy src tests` exits 0
- `uv run ruff check src tests` exits 0
</verification>

<success_criteria>
- Bet ORM exposes both new nullable columns
- Migration 0002 round-trips cleanly upgrade/downgrade/upgrade
- `BetRepository.get_pending_locked(event_id)` compiles to `SELECT ... FOR UPDATE SKIP LOCKED` and filters by PENDING
- 3 new repository tests + 1 new alembic test pass against real PG testcontainer
- No regression in existing repository tests
</success_criteria>

<output>
After completion, create `.planning/phases/05-rabbitmq-integration/05-03-repository-orm-migration-SUMMARY.md` documenting: ORM diff, migration revision string, test counts (before/after), and the `EXPLAIN ANALYZE` output of `SELECT ... FOR UPDATE SKIP LOCKED` if convenient (optional).
</output>
