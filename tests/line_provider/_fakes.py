"""Test doubles shared across line_provider unit/integration tests.

FakeEventBus records publish() calls for verification of commit->publish ordering
(D-12 / Anti-Pattern 2 mitigation).
"""

from __future__ import annotations

from line_provider.schemas.messages import EventFinishedMessage


class FakeEventBus:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[EventFinishedMessage, str]] = []
        self.fail = fail

    async def publish(
        self,
        message: EventFinishedMessage,
        *,
        routing_key: str,
    ) -> None:
        self.calls.append((message, routing_key))
        if self.fail:
            raise RuntimeError("FakeEventBus configured to fail")
