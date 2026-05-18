"""Lifespan: reconciler_event_lookup + reconciliation_task wiring (Plan 06-08 / BM-12)."""

from __future__ import annotations

import asyncio
import inspect

import pytest
from fastapi import FastAPI

from bet_maker.facades.http_event_lookup import HttpEventLookup
from bet_maker.lifespan import lifespan


@pytest.mark.asyncio(loop_scope="session")
class TestLifespanReconciler:
    async def test_reconciler_event_lookup_pinned_on_state(self, app: FastAPI) -> None:
        assert hasattr(app.state, "reconciler_event_lookup")
        assert isinstance(app.state.reconciler_event_lookup, HttpEventLookup)

    async def test_reconciliation_task_pinned_on_state(self, app: FastAPI) -> None:
        assert hasattr(app.state, "reconciliation_task")
        assert isinstance(app.state.reconciliation_task, asyncio.Task)
        assert not app.state.reconciliation_task.done(), (
            "reconciliation task died during lifespan startup — see logs"
        )

    async def test_task_name_is_reconciliation(self, app: FastAPI) -> None:
        assert app.state.reconciliation_task.get_name() == "reconciliation"

    async def test_task_started_after_broker_connect(self) -> None:
        """D-15: create_task must come AFTER router.broker.connect() in source order."""
        src = inspect.getsource(lifespan)
        broker_connect_pos = src.index("await rabbit_router.broker.connect()")
        create_task_pos = src.index("create_task(")
        assert broker_connect_pos < create_task_pos, (
            f"create_task ({create_task_pos}) must follow broker.connect ({broker_connect_pos})"
        )
        assert "reconciliation_loop" in src[create_task_pos : create_task_pos + 200]

    async def test_task_cancelled_first_in_shutdown_finally(self) -> None:
        """D-16: in the finally block, task.cancel() precedes broker.close()."""
        src = inspect.getsource(lifespan)
        shutdown_marker = 'log.info("bet_maker.shutdown")'
        shutdown_start = src.index(shutdown_marker)
        shutdown_block = src[shutdown_start:]
        cancel_pos = shutdown_block.index("reconciliation_task.cancel()")
        broker_close_pos = shutdown_block.index("await rabbit_router.broker.close()")
        assert cancel_pos < broker_close_pos, (
            "reconciliation_task.cancel() must precede broker.close() in shutdown"
        )
