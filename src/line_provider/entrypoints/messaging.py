"""line-provider AMQP entrypoint (publisher-only) (D-24).

line-provider does NOT consume any AMQP messages — Phase 5 publishes
EventFinishedMessage on store-state transitions. This module exists
solely to own the singleton RabbitRouter instance (F5 / Anti-Pattern 5).
Lifespan calls router.broker.connect() and wires
`app.state.event_bus = RabbitEventBus(router.broker)`.

No subscriber decorators. No Channel(prefetch_count=...) — that is a
consumer-side concern (bet-maker). No exchange declarations here —
lifespan does the explicit declare (D-24 / RESEARCH §5).
"""

from __future__ import annotations

from faststream.rabbit.fastapi import RabbitRouter

from line_provider.settings.config import LineProviderSettings

_settings = LineProviderSettings()

router = RabbitRouter(str(_settings.rabbitmq_url))
