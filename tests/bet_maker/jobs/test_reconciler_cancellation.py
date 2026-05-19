"""reconciler CancelledError propagation."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import pytest
from fastapi import FastAPI

from bet_maker.jobs.reconciler import reconciliation_loop


@pytest.mark.asyncio(loop_scope="session")
class TestReconcilerCancellation:
    async def test_cancelled_error_propagates_out_of_loop(self, app: FastAPI) -> None:
        """task.cancel() while loop awaits sleep -> CancelledError propagates."""
        task = asyncio.create_task(reconciliation_loop(app, interval_s=10.0), name="reconciliation")
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_task_cancel_then_await_terminates_cleanly(self, app: FastAPI) -> None:
        """The shutdown idiom (lifespan): cancel then `with suppress(CancelledError): await`."""
        task = asyncio.create_task(reconciliation_loop(app, interval_s=10.0), name="reconciliation")
        await asyncio.sleep(0.01)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)
        assert task.done()
        assert task.cancelled() or isinstance(task.exception(), asyncio.CancelledError)

    async def test_cancelled_error_logged_then_reraised(
        self, app: FastAPI, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The 'reconciler.cancelled' log line is emitted before re-raise."""
        task = asyncio.create_task(reconciliation_loop(app, interval_s=10.0), name="reconciliation")
        await asyncio.sleep(0.01)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)

        captured = capsys.readouterr()
        assert "reconciler.cancelled" in captured.out
