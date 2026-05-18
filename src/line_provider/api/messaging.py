"""line-provider AMQP entrypoint (publisher-only).

line-provider does NOT consume any AMQP messages — it publishes
EventFinishedMessage on store-state transitions. This module exists
solely to own the singleton RabbitRouter instance. Lifespan calls
router.broker.connect() and wires
`app.state.event_bus = RabbitEventBus(router.broker)`.

No subscriber decorators. No Channel(prefetch_count=...) — that is a
consumer-side concern (bet-maker). No exchange declarations here —
lifespan does the explicit declare.
"""

from __future__ import annotations

from faststream.rabbit.fastapi import RabbitRouter

from line_provider.settings.config import LineProviderSettings

_settings = LineProviderSettings()

router = RabbitRouter(str(_settings.rabbitmq_url))
