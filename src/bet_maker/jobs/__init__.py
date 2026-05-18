"""Long-running asyncio background jobs.

Distinct from `api/` (HTTP routes + AMQP subscribers): a job
is started by lifespan, lives for the duration of the process, and
yields to the loop only via `await`. The reconciler is the first
inhabitant; future health-watchdogs / outbox-drainers would also land
here.
"""
