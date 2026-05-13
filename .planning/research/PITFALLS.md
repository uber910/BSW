# Pitfalls Research

**Domain:** Two-service asynchronous Python betting system — FastAPI + FastStream (RabbitMQ) + asyncpg + SQLAlchemy 2.0 async + UoW + reconciliation job + Docker compose
**Researched:** 2026-05-13
**Confidence:** HIGH (every pitfall is anchored either to an official doc page, a tracked GitHub issue, or a Context7-verified API. Concrete API calls / config options are cited inline.)

## Framing

The Core Value of this project is **"a bet never stays in PENDING after the event has finished."** Everything in this document is filtered against that invariant: each pitfall is asked the question "would this leave a bet stuck in PENDING, or hide the fact that one is stuck, or cause it during a deploy / restart / crash?" Generic best-practice advice ("use type hints", "write tests") is omitted on purpose — STACK.md already enforces those at the CI gate.

The four buckets below map 1:1 to the dimensions requested by the orchestrator:

1. **Reliability / "stuck bet" failure modes** — 12 distinct mechanisms by which a bet ends up PENDING despite manual ack + DLQ + reconciliation.
2. **Async/await + DB pitfalls** — concrete SQLAlchemy 2.0 / asyncpg traps specific to async sessions and Decimal handling.
3. **FastStream + RabbitMQ pitfalls** — manual ack policy choices, redelivery loops, queue declaration mismatches, lifespan ordering, prefetch defaults.
4. **Docker / docker-compose pitfalls** — service ordering, healthcheck false positives, ephemeral state, signal propagation.

Phase numbering matches ARCHITECTURE.md "Suggested Build Order": **P1 skeleton, P2 line-provider HTTP, P3 bet-maker DB, P4 HTTP integration, P5 RabbitMQ, P6 reconciliation, P7 polish.**

## Critical Pitfalls — Reliability / "Stuck Bet" Failure Modes

These twelve mechanisms each can cause the Core Value violation. They are ordered roughly by likelihood at the test-task scale.

### Pitfall R1: Auto-ack consumer + crash mid-handler

**What goes wrong:**
A consumer with the FastStream default ack policy (`AckPolicy.REJECT_ON_ERROR` since FastStream 0.6) is ack'd by the broker the moment the message is delivered. If the consumer crashes after the DB UPDATE has run but before the transaction commits — or before it even runs — RabbitMQ has already removed the message. The event-finished message is gone; the bet stays PENDING forever (until reconciliation, which is a second line of defence, not the primary one).

**Why it happens:**
`AckPolicy.REJECT_ON_ERROR` is the default since FastStream 0.6.0 (the old `retry=True/N` knob was removed). Reviewers who follow tutorials often see `@router.subscriber("queue")` with no `ack_policy=` argument and assume "FastStream handles it."

**How to avoid:**
Explicitly declare `ack_policy=AckPolicy.MANUAL` on the consumer; call `await msg.ack()` only **after** `async with uow:` exits successfully (so the DB commit has happened). On exception inside the UoW context, the manager has already rolled back — call `await msg.nack(requeue=True)` for transient errors and `await msg.reject(requeue=False)` after bounded retries (see R2).

```python
from faststream import AckPolicy
from faststream.rabbit.annotations import RabbitMessage

@router.subscriber(events_finished_queue, events_exchange, ack_policy=AckPolicy.MANUAL)
async def on_event_finished(body: EventFinishedMessage, msg: RabbitMessage, uow: AsyncUnitOfWork = Depends(get_uow)) -> None:
    try:
        async with uow:
            await settle_bets_for_event(uow, event_id=body.event_id, new_state=body.new_state)
    except Exception:
        await msg.nack(requeue=True)
        raise
    await msg.ack()  # ack ONLY after commit
```

**Warning signs:**
- Bets remain PENDING after a consumer pod crash.
- `rabbitmqctl list_queues messages_unacknowledged` shows 0 after a forced kill (should be ≥1 if a message was in-flight).
- Tests cannot reproduce "kill mid-process, message redelivered" — passing means you have the wrong policy.

**Phase to address:** P5 (RabbitMQ integration) — must be wired the moment the consumer is added.

---

### Pitfall R2: Ack-after-DB-rollback split-brain (commit succeeds, ack fails)

**What goes wrong:**
The UoW commit succeeds (status is WON in PG), then the consumer calls `await msg.ack()` and the broker connection drops. RabbitMQ never sees the ack, redelivers the message after the visibility timeout, and a second worker (or the same worker after reconnect) processes the same event-finished message again. With `FOR UPDATE SKIP LOCKED` (D9) and the `WHERE status = 'PENDING'` filter in the interactor, the re-processing is a no-op — but only if the interactor is structured idempotently. The opposite split-brain — ack succeeds, then commit fails — also exists but is impossible with the recommended `async with uow: ... ; await msg.ack()` order.

**Why it happens:**
"Exactly-once" doesn't exist for AMQP. You get at-least-once plus consumer-side idempotency, or at-most-once plus message loss. Devs often pick at-most-once by accident (R1) and don't realise at-least-once requires idempotent handlers.

**How to avoid:**
Make `settle_bets_for_event(event_id, new_state)` idempotent by construction:
1. The repository's `get_pending_locked()` filters `WHERE status = 'PENDING'`; on a redelivered message the rows are no longer PENDING and the loop is empty.
2. Combined with `with_for_update(skip_locked=True)`, the second processor never even sees the rows the first one locked.
3. Optional belt-and-braces: store `last_processed_message_id` on a small `processed_events` table keyed by `(event_id, schema_version)`; on duplicate, exit early. For a test task, R2 is already covered by (1)+(2) — call it out in README.

**Warning signs:**
- Logs show "settled 0 bets for event_id=X" immediately after "settled N bets for event_id=X" — that is R2 working correctly.
- If you see "row updated twice" or duplicate state transitions on the same bet, the idempotency layer is broken.

**Phase to address:** P5 (consumer + interactor implementation) for the `FOR UPDATE` + status filter. Verification in P6 (reconciliation tests cover the same idempotency path).

---

### Pitfall R3: Status update races between consumer and reconciler

**What goes wrong:**
Both the AMQP consumer and the reconciliation worker run in the same bet-maker process. The consumer picks up an `events.finished` message; concurrently the reconciliation worker has just polled line-provider for the same event and got the same terminal state. Without serialisation, both transactions read PENDING rows, both write WON/LOST, and the second one's commit either no-ops or — under the wrong isolation — overwrites status (e.g., from WON back to WON, harmless; from a corrupted state to a corrupted state, harmful).

**Why it happens:**
Two writers, one row, no lock. PG's default `READ COMMITTED` isolation allows both transactions to start with the same snapshot; only the first to commit "wins" naturally for unique-key conflicts, but for plain UPDATEs both succeed.

**How to avoid:**
`select(Bet).where(...).with_for_update(skip_locked=True)` in `BetRepository.get_pending_locked()` (per ARCHITECTURE.md). Verified against SQLAlchemy 2.0 docs. The semantics:
- The consumer's transaction acquires the row lock.
- The reconciler's concurrent `SELECT ... FOR UPDATE SKIP LOCKED` simply skips locked rows; the reconciler returns "0 pending bets to settle" for that event.
- After the consumer commits, on the **next reconciliation tick**, the rows are no longer PENDING and the reconciler still skips them via the `WHERE status = 'PENDING'` filter.

**Important PG semantics for our scale (READ COMMITTED is default):** under READ COMMITTED, a `SELECT ... FOR UPDATE` will, when it encounters a row that was updated by a concurrent committed transaction, re-evaluate its `WHERE` clause against the newest committed row version (EvalPlanQual). That means even without SKIP LOCKED, the `WHERE status = 'PENDING'` filter would re-check and the row would no longer match. SKIP LOCKED gives us non-blocking behaviour (no wait) on top of that.

**Warning signs:**
- Tests that run consumer + reconciler concurrently against the same event don't deadlock (good).
- Logs show only one "settle_bets_for_event" succeeding per `(event_id, run)` pair.
- `pg_locks` shows brief row locks but no `granted=false` rows stuck for long.

**Phase to address:** P5 (`with_for_update(skip_locked=True)` in `BetRepository`). Verified in P6 (test consumer+reconciler racing in the same test).

---

### Pitfall R4: Queue not durable / message not persistent → broker restart loses messages

**What goes wrong:**
`docker compose restart rabbitmq` (or a crash) discards all unacked + queued messages because either (a) the queue was declared `durable=False`, or (b) the publish was made without `delivery_mode=PERSISTENT`. Any event-finished message in flight at the restart moment vanishes — bets stay PENDING.

**Why it happens:**
RabbitMQ's "durable" is two-part: the **queue** must be durable AND each **message** must be persistent. Both default to non-durable / non-persistent in the AMQP spec.

**How to avoid:**
- Queue: `RabbitQueue("bet_maker.events.finished", durable=True, arguments={...})`. Already in ARCHITECTURE.md but verify in the consumer module.
- Exchange: `RabbitExchange("events", type="topic", durable=True)`.
- Publish: FastStream's `router.broker.publish(...)` defaults to `delivery_mode=PERSISTENT` only when publishing to a durable exchange via aio-pika's robust connection — explicitly pass `persist=True` / verify the publish path. Cross-check by running `rabbitmqctl list_queues name durable` and `list_exchanges name type durable` after compose-up.
- Add a docker-compose volume for `/var/lib/rabbitmq`: `rabbitmq_data:/var/lib/rabbitmq`. Without this, the **node name's database** on disk is wiped on container recreate even if the queue itself is durable — durable queues live in that database, and a `docker compose down -v` removes them. See R10 for the related issue.

**Warning signs:**
- `rabbitmqctl list_queues name durable` shows `false` for the events queue.
- After a `docker compose restart rabbitmq`, the queue exists but message count is 0 when it shouldn't be.
- After a `docker compose down && up`, the queue is gone entirely → R10.

**Phase to address:** P5 (queue / exchange declaration); P1 (volume in docker-compose.yml) for the persistence side.

---

### Pitfall R5: Queue / exchange redeclaration mismatch across deploys → PRECONDITION_FAILED

**What goes wrong:**
On deploy N the queue was declared `durable=True, arguments={"x-dead-letter-exchange": "events.dlx"}`. On deploy N+1 someone changes the DLX name or adds `x-message-ttl`. RabbitMQ refuses with `PRECONDITION_FAILED - inequivalent arg ... for queue '...' in vhost '/'`. The channel closes; the consumer reconnects in a tight loop; no messages are processed; bets stay PENDING until the queue is manually deleted.

**Why it happens:**
RabbitMQ does not allow changing an existing queue's arguments. A live queue's parameters are frozen at first-declaration time. aio-pika (which FastStream wraps) propagates the broker's 406 error as a channel close, and FastStream's RobustChannel attempts to redeclare — same error — forever.

**How to avoid:**
- Lock the queue/exchange config in one module (`infrastructure/broker/rabbit.py`) and never change it casually. Treat it like a DB migration.
- If a change is needed: name the new queue differently (`bet_maker.events.finished.v2`), bind both old and new for a grace period, then drain and delete the old one.
- Pin the exact arguments dictionary in code and assert it against `rabbitmqctl list_queues name arguments` in an integration test.
- In dev: a `docker compose down -v` wipes RabbitMQ state and the new declaration succeeds. Never do that in any environment with real messages.

**Warning signs:**
- Application logs flood with `aiormq.exceptions.ChannelPreconditionFailed` or `PRECONDITION_FAILED - inequivalent arg`.
- `rabbitmqctl list_consumers` is empty even though the consumer is supposed to be subscribed.
- Health check on `/health` reports rabbitmq=ok because the connection is up, but no messages flow → see R6.

**Phase to address:** P5 (initial declaration); P7 (rename-not-edit discipline noted in README).

---

### Pitfall R6: Healthcheck reports OK while consumer is broken

**What goes wrong:**
`/health` pings RabbitMQ by opening a channel; the channel opens successfully because the connection is fine. The consumer, however, is in a tight reconnect loop due to R5 or is stuck because of a poison-message redelivery loop (R7). `docker compose up` reports both services healthy. No bets settle. The Core Value silently fails.

**Why it happens:**
A connection-level ping doesn't verify a subscription is active and consuming. RabbitMQ separates "I can talk to the broker" from "my subscription has a consumer with prefetched messages."

**How to avoid:**
The `/health` endpoint should check **subscription liveness**, not just connection:
- Verify `len(router.broker._subscribers) > 0` and each subscriber's connection state.
- Add a Prometheus-style internal counter `consumer_messages_processed_total` and expose its value as part of `/health` (or a separate `/ready` endpoint). If it hasn't incremented in 5× the expected message interval AND there are queued messages, surface as unhealthy.
- For a test task, the minimum viable check: ping the channel AND verify subscriber count > 0. Mention in README that "production would add a liveness counter for the subscription."

**Warning signs:**
- `/health` returns 200 but `rabbitmqctl list_queues messages messages_ready` keeps growing.
- `rabbitmqctl list_consumers` returns empty for `bet_maker.events.finished`.
- Reviewer's manual test "PATCH event → wait → GET /bets" doesn't show settled bets.

**Phase to address:** P5 (basic ping); P6 or P7 (subscriber-count assertion + counter, before final demo).

---

### Pitfall R7: Poison-message redelivery loop in DLQ-misconfigured queue

**What goes wrong:**
A message with bad payload (schema mismatch, e.g., from a future `schema_version`) causes the handler to raise. Without a delivery-count limit, RabbitMQ requeues the message indefinitely. The consumer is stuck on this one message; messages behind it in the queue never get processed. Bets for those events stay PENDING.

**Why it happens:**
With **classic queues** (RabbitMQ's default historically), there is no built-in delivery-count tracking. The `x-delivery-count` header is **only** populated for **quorum queues** (RabbitMQ docs). FastStream's `NackMessage` with requeue=True is forever.

**How to avoid:**
Two layers of defence:
1. **At consumer code level (works on classic queues):** track redelivery via `msg.raw_message.redelivered` flag and a Redis/in-memory counter, OR — simpler — make the handler distinguish "poison" (always fails — schema mismatch, missing field, validation error) from "transient" (DB down, network blip). For poison: `await msg.reject(requeue=False)` immediately → goes to DLX. For transient: `nack(requeue=True)`.

   ```python
   try:
       async with uow:
           await settle_bets_for_event(uow, event_id=body.event_id, new_state=body.new_state)
   except ValidationError:
       # Poison: bad payload, no point retrying
       await msg.reject(requeue=False)
       return
   except (OperationalError, asyncpg.PostgresConnectionError):
       # Transient: DB momentarily down
       await msg.nack(requeue=True)
       raise
   ```

2. **At broker level (preferred for the test task signal, requires RabbitMQ 4.0+ with quorum queues):** declare the main queue with `x-queue-type=quorum` (RabbitMQ 4.0 enforces a default `delivery-limit=20`; after 20 redeliveries the message is dead-lettered automatically). **For the test task, classic queues are simpler and adequate** as long as defence (1) is solid; mention quorum-queues as the production upgrade in README.

**Warning signs:**
- A single `event_id` appears in logs hundreds of times per minute, all with redelivered=true.
- `rabbitmqctl list_queues messages_ready` slowly grows even though throughput should be steady.
- DLQ remains empty while messages keep being redelivered.

**Phase to address:** P5 (consumer error-handling discipline + DLX wiring).

---

### Pitfall R8: Reconciliation job dies silently

**What goes wrong:**
The reconciliation `asyncio.Task` raises an uncaught exception (e.g., `httpx.ConnectError` outside the `tenacity` retry decorator, or a `RuntimeError` in the loop body). Python logs the exception once and the task ends. The main process continues running with `/health` returning OK. Messages still flow through the consumer. But the **defence-in-depth** is gone: if a single message is lost (R4, broker upgrade, etc.), nothing rescues those bets. Core Value violated invisibly.

**Why it happens:**
`asyncio.create_task` without a wrapper does not propagate exceptions to the main task; the exception is logged only when the task is garbage-collected. The lifespan's `try/finally` doesn't notice.

**How to avoid:**
Wrap the loop body in `try/except Exception:` so the loop itself never dies (ARCHITECTURE.md already shows this shape). Additionally:
- Add a `name="reconciliation"` to `asyncio.create_task(...)` so it appears in `asyncio.all_tasks()` and crash logs.
- In `/health`, check `task.done() is False AND task.exception() is None`. If the task is gone, return 503.
- Optional: emit a structlog "reconciliation.heartbeat" event each tick; an absent heartbeat for 3× the interval is a production-grade alert (skip the alerting infra for the test task — just log it).

**Warning signs:**
- "reconciliation.loop.start" appears once in logs and "reconciliation.tick.done" stops appearing.
- `/health` returns OK forever while PENDING bets accumulate behind a stopped reconciler.
- Tests that kill the AMQP consumer for one cycle and rely on the reconciler to backfill fail.

**Phase to address:** P6 (worker module). Specifically the `while not shutdown_event.is_set():` loop must be wrapped in a guard that catches all `Exception` (NOT `BaseException` — let `CancelledError` through).

---

### Pitfall R9: Reconciler races consumer at a different layer — duplicate HTTP read

**What goes wrong:**
Reconciler reads line-provider's `GET /events/{id}` and sees state=NEW (because the in-memory store was updated and the AMQP publish happened, but the HTTP cache in line-provider hasn't been invalidated, OR the reconciler raced ahead of line-provider's local state mutation). Reconciler concludes "still pending, skip." Then the AMQP consumer settles those bets fine. No correctness bug — but if line-provider has any asymmetry between the state seen by AMQP publishers and the state seen by HTTP readers (e.g., publish-before-store-write), the reconciler will lock in the wrong conclusion.

A different, real flavour: line-provider's `set_event_state` interactor publishes to AMQP *before* committing the in-memory change. Consumer settles bet (success). Reconciler queries `GET /events/{id}` 50ms later and still sees state=NEW (race). Reconciler says "no settle needed." That's fine because the consumer already settled. But if order is *reverse* — store updated, publish failed, reconciler queries and sees FINISHED — the reconciler is the ONLY path to settle and must succeed. The risk: if reconciler logic is buggy ("only act if state has been FINISHED for ≥ X seconds") it can defer indefinitely.

**Why it happens:**
Two readers of the same logical state across an HTTP boundary aren't atomic. Anti-Pattern 2 in ARCHITECTURE.md ("publishing to AMQP from inside a DB transaction") is the inverse direction of the same problem.

**How to avoid:**
- In line-provider's `interactors/set_event_state.py`: **commit to the in-memory store first, then publish.** If publish fails, the store is the source of truth and the reconciler will pick it up on its next tick. Never the reverse.
- In bet-maker's `interactors/reconcile_pending_bets.py`: as soon as line-provider reports a terminal state, settle immediately; do not add "wait N seconds" logic. The terminal state is monotonic — once FINISHED, never NEW.
- In line-provider's `infrastructure/store/in_memory.py`: state transitions under an `asyncio.Lock` (Anti-Pattern 6 in ARCHITECTURE.md). Reads do not need the lock.

**Warning signs:**
- Logs show "publish_event_finished" before "store.set_state" — order is wrong.
- Reconciler logs "skipped event X — still NEW" repeatedly, but `GET /events/X` returned FINISHED in another tab.

**Phase to address:** P2 (line-provider interactor ordering); P6 (reconciler logic must trust line-provider's monotonic terminal state).

---

### Pitfall R10: `docker compose down -v` wipes the durable queue

**What goes wrong:**
A developer runs `docker compose down -v` (or `--volumes`) to "start fresh." All volumes are removed, including RabbitMQ's `/var/lib/rabbitmq`. The next `docker compose up` re-declares the queue from code — but any messages that were in the queue before the down are gone. If this happens during a demo or in CI with real data, bets stay PENDING.

**Why it happens:**
RabbitMQ stores queue metadata + persistent messages on disk under `/var/lib/rabbitmq/mnesia/<node>`. Without a named volume, this lives in the container's writable layer and dies with the container. With `-v`, even the named volume is removed.

**How to avoid:**
- docker-compose.yml: declare `volumes: rabbitmq_data: {}` at the top level AND `volumes: - rabbitmq_data:/var/lib/rabbitmq` on the rabbitmq service.
- README: document the difference between `docker compose down` (data preserved) and `docker compose down -v` (data destroyed). For the test task, the reviewer will likely use just `down` then `up`, so durability across that cycle is the visible win.
- Same applies to PostgreSQL: `postgres_data:/var/lib/postgresql/data`.
- RabbitMQ's node name is derived from the container hostname; pin `hostname: rabbitmq` on the service so the data directory's node name stays stable across recreations (otherwise the new node can't read the old node's mnesia DB).

**Warning signs:**
- After `docker compose restart rabbitmq` the queue is gone (no volume → see Pitfall R4).
- After `docker compose down && up` the queue is gone (no volume OR hostname changed).
- `rabbitmqctl list_queues` shows the queue but with messages=0 even though messages were sent.

**Phase to address:** P1 (compose file authored with volumes + hostname).

---

### Pitfall R11: Restart with in-flight unacked messages → requeue surprise

**What goes wrong:**
A reviewer runs `docker compose restart bet-maker` mid-flow. There are 3 unacked messages on the consumer's channel. RabbitMQ's behaviour:
- If the consumer didn't have `graceful_timeout` configured (FastStream broker option), the channel closes abruptly. The 3 messages are **requeued** to the head of the queue.
- The new consumer instance picks them up and processes them. Total result: messages are processed once *eventually*, but with extra latency and a small chance of partial-DB-write being visible (the rollback in UoW should prevent this, see R2).

The actual pitfall is the **subtle ordering inversion** at restart: if message M1 was being processed and ack'd, but the ack hadn't reached the broker before the connection closed, M1 is redelivered. Combined with R2's idempotency check, this is safe — but only because R2 is solid.

**Why it happens:**
SIGTERM → broker connection closes → unacked messages requeued. This is correct AMQP behaviour, not a bug, but tests that assume "process each message exactly once" will be flaky.

**How to avoid:**
- Set FastStream `RabbitBroker(graceful_timeout=30.0)` (verified API in Context7) — broker waits up to 30s for in-flight handlers to complete before closing the channel. The lifespan shutdown order in ARCHITECTURE.md (worker → http → broker → DB) already gives the broker the right window.
- Ensure docker-compose's `stop_grace_period: 30s` on bet-maker (default is 10s, often too short).
- Ensure the Dockerfile uses **exec form** for CMD (`CMD ["python", "-m", "uvicorn", "bet_maker.app:app", "--host", "0.0.0.0", "--port", "8000"]`) so SIGTERM reaches uvicorn directly. Shell form (`CMD python -m ...`) wraps in `/bin/sh -c` and `sh` does not forward signals — uvicorn never sees SIGTERM, gets SIGKILL after grace period, broker connection closes hard, all in-flight messages requeue. See Pitfall D4.

**Warning signs:**
- Logs show "consumer drained 0 messages" on shutdown — should show the actual in-flight count.
- `docker compose down` takes the full grace period (≈ 10–30s) before exiting → SIGTERM was never received.
- "exit code 137" (SIGKILL) on the container → init system killed it forcefully.
- Tests show message ordering inversions you didn't expect.

**Phase to address:** P1 (Dockerfile CMD exec form + compose `stop_grace_period`); P5 (broker `graceful_timeout`); P7 (verify by reading `docker compose down` logs).

---

### Pitfall R12: AMQP publish from inside a DB transaction (would apply to bet-maker if it published)

**What goes wrong:**
Even though bet-maker is not designed to publish (per ARCHITECTURE.md), the temptation is real: "POST /bet receives a bet; let me also publish bet.placed for downstream consumers." If the publish is inside `async with uow:`, two failure modes appear: (a) commit succeeds, publish fails → orphan state in DB, no AMQP signal; (b) publish succeeds, commit fails → ghost message, no DB row. For line-provider the same anti-pattern is symmetric across the in-memory store (less severe, single-process, but still): publishing before the store mutation lands lets reconcilers race and lose.

**Why it happens:**
"While I'm in the transaction, let me do the thing." It feels atomic; it isn't. No transactional outbox is in scope per PROJECT.md.

**How to avoid:**
- bet-maker: **don't publish**, period. This is an explicit architectural decision (ARCHITECTURE.md). If a future requirement adds outbound events, do it via an outbox table in PG, NOT inside the same UoW.
- line-provider: publish **after** the in-memory store mutation (a single-process atomic op), never before. Wrap the mutation in `asyncio.Lock`, then publish outside the lock. If publish fails, log and trust the reconciler (which polls line-provider's HTTP API for the source-of-truth state) to recover.

**Warning signs:**
- A failing AMQP publish causes a DB rollback (or vice versa) — wrong order.
- bet-maker tests show a `publish()` call inside an `async with uow:` block.
- line-provider publishes but the subsequent HTTP `GET /events/{id}` still returns state=NEW.

**Phase to address:** P2 (line-provider interactor ordering); P3+P5 (bet-maker remains publish-free by construction).

---

## Critical Pitfalls — Async/await + DB

### Pitfall A1: `MissingGreenlet` / `greenlet_spawn` on lazy-load after commit

**What goes wrong:**
```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here.
Was IO attempted in an unexpected place?
```
Code accesses `bet.event` (a relationship) outside the `async with uow:` block, or `bet.amount` after the session was closed and the default `expire_on_commit=True` cleared the attribute. SQLAlchemy attempts to lazy-load via the async DBAPI, but there's no greenlet context to bridge sync-style attribute access into the async runtime.

**Why it happens:**
SQLAlchemy 2.0 async runs ORM internals on a greenlet to let sync-style attribute access (`obj.attr`) trigger an `await` underneath. Outside the session's greenlet, that bridge isn't there. Documented at https://docs.sqlalchemy.org/en/20/errors.html#error-xd2s.

**How to avoid:**
1. **`expire_on_commit=False` on `async_sessionmaker`** — confirmed in SQLAlchemy 2.0 docs as the recommended setting for async. Attributes loaded into the session stay populated after commit.
   ```python
   async_session = async_sessionmaker(engine, expire_on_commit=False)
   ```
2. **Convert to DTOs inside the session.** Selectors return `BetRead.model_validate(orm_obj, from_attributes=True)` while still inside the session context — never return raw ORM instances across the session boundary.
3. **Eager-load relationships** with `selectinload()` or `joinedload()` if a query crosses a relationship. For this project there are no relationships on `Bet` — but if you add `Bet.event` later, lazy loading will be a guaranteed bug.
4. **For unavoidable lazy access:** use the `AsyncAttrs` mixin on `DeclarativeBase` and call `await bet.awaitable_attrs.event` — documented at https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html.

**Warning signs:**
- `MissingGreenlet` or `greenlet_spawn has not been called` in tests or production logs.
- `DetachedInstanceError: Parent instance is not bound to a Session` — variant of the same issue.
- Tests pass when the session is open and fail when the data is "returned" from an interactor.

**Phase to address:** P3 (bet-maker DB). Set `expire_on_commit=False` from day one; converting selectors to return DTOs is part of the selector implementation.

---

### Pitfall A2: Sharing one `AsyncSession` across concurrent tasks → `InterfaceError: another operation in progress`

**What goes wrong:**
```
asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress
```
Two coroutines use the same `AsyncSession` (or the same asyncpg connection underneath) concurrently. asyncpg is **explicitly not safe for concurrent use of one connection** — it has no internal lock; you must serialise. SQLAlchemy bug https://github.com/sqlalchemy/sqlalchemy/issues/5967 and asyncpg #258/#863 document this exact failure.

**Why it happens:**
Devs naturally think "async means concurrent" and reuse a session in `asyncio.gather`. ARCHITECTURE.md's "Anti-Pattern 3" warns against it; in practice it happens by accident — e.g., a selector reads while an interactor writes inside the reconciliation loop, both reusing the same session.

**How to avoid:**
- **One session per UoW per business operation.** `async_sessionmaker` is the factory; call it per request via `Depends(get_uow)` — this is exactly what `facades/uow.py` does (ARCHITECTURE.md).
- **Never store an `AsyncSession` in `app.state` or a module-level global.** Only the `async_sessionmaker` (factory) and the `AsyncEngine` (pool owner) are safe singletons.
- **For the reconciliation worker:** the worker should construct a fresh `AsyncUnitOfWork` per tick, not share one across ticks. Each tick = one session = one transaction.
- **For `asyncio.gather` patterns:** if you must fan out N queries in parallel, give each one its own session from the same `async_sessionmaker`. asyncpg's connection pool will give each session its own connection.

**Warning signs:**
- "cannot perform operation: another operation is in progress" anywhere in logs — this is **always** session/connection sharing.
- Tests using `asyncio.gather` with one fixture-scoped session fail intermittently.
- Production load tests fail at low concurrency.

**Phase to address:** P3 (sessionmaker + UoW). Make UoW per-request; never share a session.

---

### Pitfall A3: asyncpg connection pool too small → silent stalls under settle storm

**What goes wrong:**
A single line-provider PATCH triggers settle of 200 PENDING bets. The consumer's transaction takes one pooled connection. Concurrently the reconciler ticks: it wants its own connection. The `/bets` endpoint also wants connections. With SQLAlchemy's default `pool_size=5, max_overflow=10`, you have 15 connections max — fine for the test task, but the reconciler can starve under any unrelated load.

**Why it happens:**
Default `pool_size=5` is conservative. The asyncpg driver itself has no pool concept — SQLAlchemy's pool is what manages it.

**How to avoid:**
- Set explicit pool sizes in `create_async_engine`:
  ```python
  engine = create_async_engine(
      dsn,
      pool_size=10,
      max_overflow=20,
      pool_pre_ping=True,
      pool_recycle=1800,
  )
  ```
- `pool_pre_ping=True` is critical: detects stale connections (e.g., after a `docker compose restart postgres` where the connection survives but is broken). One SELECT 1 per checkout, marginal cost.
- `pool_recycle=1800` (30 min) preempts firewall-killed idle connections — irrelevant in compose, important in any real deploy.
- PG must be sized to match: `max_connections` in postgresql.conf ≥ pool_size + max_overflow across all replicas. For test-task scale (1 bet-maker replica, 30 total connections), the default PG `max_connections=100` is plenty.

**Warning signs:**
- Requests hang waiting for a connection (no timeout → indefinite block) — set `pool_timeout=10` to fail loud instead.
- `psycopg2.OperationalError: SSL connection has been closed unexpectedly` or asyncpg equivalent → no `pool_pre_ping`.
- Reconciler logs "tick.failed" with `TimeoutError` on connection acquire under load.

**Phase to address:** P3 (engine config).

---

### Pitfall A4: Decimal coercion drift — Pydantic v2 string serialization breaks API contract

**What goes wrong:**
Pydantic v2 **serializes `Decimal` as a JSON string** (`"10.00"`), not a number (`10.00`). FastAPI happily emits `{"amount": "10.00"}`. Reviewers (or clients) expecting numeric JSON see a string and complain about the API contract. Worse: TZ specifies "two decimal places" — `Decimal("10")` serializes as `"10"`, not `"10.00"`, unless you quantize before serializing.

**Why it happens:**
Pydantic v2 changed Decimal serialization from `float()` (lossy) to `str()` (lossless). Most modern APIs accept either, but JSON-schema-driven clients (and the OpenAPI doc) will type the field as `string`, which is technically correct but surprising.

**How to avoid:**
- For HTTP responses: keep Decimal-as-string (it's the safe default; floats lose precision). Document in the OpenAPI spec that `amount` is `string` with `pattern: ^[0-9]+\.[0-9]{2}$`. Reviewers familiar with payment APIs expect this.
- For input validation: `condecimal(gt=0, max_digits=12, decimal_places=2)` in Pydantic v2:
  ```python
  from pydantic import BaseModel, condecimal

  class BetCreate(BaseModel):
      event_id: int
      amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
  ```
  This rejects `10.123` with HTTP 422 before it hits the DB.
- Always quantize before storing: `amount.quantize(Decimal("0.01"))` in `helpers/money.py`. Don't trust upstream to send exactly two decimal places.
- For AMQP message bodies: same — `Decimal` serializes as string. Both sides use Pydantic, so round-trip is safe; ensure the field type matches on both publisher and consumer schemas (`schemas/messages.py` in both services).

**Warning signs:**
- OpenAPI schema for `BetCreate.amount` shows `type: string` (correct, but confusing if you expected number).
- Tests comparing `bet["amount"] == 10.00` fail (compare against `"10.00"` instead).
- DB stores `10.123` because no `.quantize(Decimal("0.01"))` was applied.

**Phase to address:** P3 (Pydantic schemas + money helper). Validation tests in P3; OpenAPI documentation in P7.

---

### Pitfall A5: NUMERIC ↔ Decimal precision loss via asyncpg's float fallback

**What goes wrong:**
SQLAlchemy's `Numeric(precision, scale)` defaults to `asdecimal=True`, which preserves `Decimal`. But if you forget the `Numeric` import and use `Float()` accidentally, or if you use `Numeric(asdecimal=False)`, asyncpg returns Python `float`, and `10.00 - 0.10 == 9.9` becomes `9.899999999999999`. Test-task implications: bet amounts diverge from the user-submitted value by 1e-16, fails `pytest.approx`, and definitely fails an "exact match" assertion.

**Why it happens:**
Defaults are right when you use the SQLAlchemy 2.0 typed style (`Mapped[Decimal] = mapped_column(Numeric(12, 2))`). The trap is the legacy `Column(Float)` or `Numeric(asdecimal=False)` that overrides it.

**How to avoid:**
- Model uses `Mapped[Decimal] = mapped_column(Numeric(12, 2))`. SQLAlchemy infers `asdecimal=True` from the Python annotation.
- mypy strict + `pydantic.mypy` plugin will flag `Decimal` ↔ `float` type drift at the boundary.
- Test: round-trip `Decimal("10.00")` through `place_bet` → `list_bets` and assert exact equality.

**Warning signs:**
- DB column type is `double precision`, not `numeric(12,2)` — wrong SQLAlchemy type.
- Tests use `pytest.approx` on amounts — should be exact equality.
- `Decimal("10.00") + Decimal("0.10") != Decimal("10.10")` somewhere in code (it shouldn't — Decimal arithmetic is exact; if it isn't, a float crept in).

**Phase to address:** P3 (Bet model + initial Alembic migration); CI gate via mypy strict.

---

### Pitfall A6: Awaiting `AsyncSession` from a sync context (e.g., Alembic `env.py`)

**What goes wrong:**
Alembic's `env.py` is sync by default; if you stitch in `from bet_maker.infrastructure.db.engine import engine` (an async engine) and call `engine.connect()` in `run_migrations_online`, you get `TypeError: object MockConnection can't be used in 'await' expression` or a similar mismatch.

**Why it happens:**
Alembic's standard template is synchronous. SQLAlchemy 2.0 has an async-specific template that must be initialised with `alembic init -t async`.

**How to avoid:**
- `alembic init -t async alembic/` (the `-t async` template flag is the entire fix).
- In `env.py`, use `async def run_async_migrations()` + `asyncio.run(run_async_migrations())`.
- Share the DSN via `bet_maker.settings.config.BetMakerSettings().pg_dsn` — do NOT hardcode in `alembic.ini`'s `sqlalchemy.url` (Anti-Pattern 7 in ARCHITECTURE.md).

**Warning signs:**
- `alembic upgrade head` errors with `TypeError` involving `await`.
- env.py uses `connectable.connect()` synchronously against an async engine.
- Migrations work locally but fail in CI because the URL is hardcoded.

**Phase to address:** P3 (Alembic setup). Run `alembic init -t async` once and commit the env.py.

---

### Pitfall A7: structlog contextvars cross-task contamination

**What goes wrong:**
A `request_id` bound at HTTP-middleware level appears in logs from concurrent AMQP consumer handlers, or worse, two parallel requests overwrite each other's `request_id` mid-flight. Result: log lines correlate to the wrong request. Debugging the Core Value path becomes guesswork.

**Why it happens:**
structlog uses `contextvars.ContextVar` for context-local state. Python's `contextvars` are **task-local** in asyncio — *if* the consumer of the contextvar is in the same task tree. If you spawn `asyncio.create_task(...)` without first calling `contextvars.copy_context().run(...)`, the new task inherits the parent's context at creation time but later mutations don't propagate back. There was a documented bug (structlog #248, #302) where pre-async log lines created contextvars in thread-local rather than task-local scope. Fixed in structlog ≥ 21.1.0.

**How to avoid:**
- structlog ≥ 25.5.0 (pinned in STACK.md) has the fix.
- Always use `structlog.contextvars.bind_contextvars(...)` and `clear_contextvars()` in a `try/finally`, not naked `bind()`.
- In the AMQP consumer, **clear contextvars at the top of the handler** before binding the message_id, so a prior request's request_id doesn't bleed in.
  ```python
  async def on_event_finished(body, msg, uow):
      structlog.contextvars.clear_contextvars()
      structlog.contextvars.bind_contextvars(event_id=body.event_id, correlation_id=body.correlation_id, message_id=msg.message_id)
      try:
          ...
      finally:
          structlog.contextvars.clear_contextvars()
  ```
- In the FastAPI middleware, do the same: `clear_contextvars` at request start, bind `request_id`, clear on response.

**Warning signs:**
- Log lines from one HTTP request show a `request_id` you've never set.
- Two concurrent requests share the same `request_id` value.
- AMQP consumer logs show a `request_id` from a prior HTTP request.

**Phase to address:** P1 (structlog configuration + middleware); P5 (consumer binding/clearing); always paired with `try/finally`.

---

## Critical Pitfalls — FastStream + RabbitMQ

### Pitfall F1: Wrong `ack_policy` choice (REJECT_ON_ERROR vs NACK_ON_ERROR vs MANUAL)

**What goes wrong:**
FastStream 0.6 removed the old `retry=True/N` knob and replaced it with `ack_policy` (released 2026; verified in Context7 release notes). The defaults shifted:
- `REJECT_ON_ERROR` (default) — on exception, message is rejected without requeue → goes to DLX if bound, else discarded. Combined with no DLX, this **loses the message** on first failure.
- `NACK_ON_ERROR` — on exception, message is nacked with requeue → comes right back → poison loop (Pitfall R7).
- `ACK_FIRST` — ack before processing → at-most-once → message loss on crash.
- `ACK` — ack regardless of exception → at-most-once → same as ACK_FIRST for our purposes.
- `MANUAL` — full control, what we want.

Picking the wrong one is silent: tests pass, but production behaviour differs catastrophically.

**Why it happens:**
The default changed between FastStream versions. Tutorials and StackOverflow snippets often predate the change.

**How to avoid:**
- Always pass `ack_policy=AckPolicy.MANUAL` explicitly on `@router.subscriber(...)`.
- Code review rule: any subscriber without `ack_policy=` is rejected.
- Pin `faststream>=0.6,<0.7` (already in STACK.md); be aware of the default if upgrading.

**Warning signs:**
- Subscriber decorator has no `ack_policy=` argument.
- No explicit `await msg.ack()` in the handler body.
- After a forced exception, the message is gone (not in main queue, not in DLQ).

**Phase to address:** P5 (consumer implementation, day 1).

---

### Pitfall F2: Consumer prefetch / qos default → consumer monopolises queue

**What goes wrong:**
RabbitMQ's default prefetch is **unlimited** (basic.qos with prefetch_count=0). FastStream's RabbitBroker uses a single connection/channel; without an explicit prefetch_count, the consumer can buffer the entire queue in memory. If there are 10,000 PENDING events suddenly finishing, the consumer fetches all 10k messages, OOMs, and dies with all of them unacked. Worse: with `AckPolicy.MANUAL` and no prefetch limit, you can't backpressure — the consumer happily accepts more than it can process.

**Why it happens:**
RabbitMQ AMQP default is 0 = unlimited. FastStream inherits unless explicitly overridden.

**How to avoid:**
- Set `prefetch_count` on the broker (or queue) construction. For a single-consumer test task: `prefetch_count=10` is a safe default (10 in-flight messages).
  ```python
  from faststream.rabbit import RabbitBroker
  broker = RabbitBroker("amqp://guest:guest@rabbitmq:5672/", graceful_timeout=30.0)
  # On the router/subscriber, qos can be set per-queue if needed
  ```
- For FastStream's RabbitRouter, prefetch is wired at the broker level. Verify via `rabbitmqctl list_consumers` — the `prefetch_count` column should not be 0.
- Document the choice in code comment: "prefetch_count=10 because single-consumer + ~1s settle time + RabbitMQ default unlimited would risk OOM at scale."

**Warning signs:**
- Memory usage of bet-maker spikes when many events finish in a short window.
- `rabbitmqctl list_consumers` shows prefetch_count=0.
- Killing the consumer when it's mid-batch causes a flood of redeliveries (because 1000s were unacked).

**Phase to address:** P5 (broker config, when adding the consumer).

---

### Pitfall F3: FastStream + FastAPI lifespan order — broker connects before DB pool is ready

**What goes wrong:**
With FastStream's RabbitRouter integrated via `app.include_router(router)` on FastAPI ≥ 0.112.2, the router's broker lifespan auto-merges with FastAPI's. The auto-merge order isn't guaranteed to be DB-first; in some setups the broker starts subscribing before your custom lifespan's DB ping completes. A message arrives at t=0; the consumer tries to acquire a DB connection; the pool isn't initialised yet; the handler raises; with `REJECT_ON_ERROR` default the message is gone, with `MANUAL` you nack but you can't get the DB even on retry until startup finishes.

**Why it happens:**
"Auto" anything across two frameworks is fragile. The FastAPI PR fastapi/fastapi#9630 added nested lifespan merging; FastStream's RabbitRouter uses it but the **execution order of the nested lifespans is not specified**.

**How to avoid:**
- **Take explicit control of the lifespan** via the pattern in ARCHITECTURE.md "Pattern 4". Build a custom `asynccontextmanager` that:
  1. Builds engine + sessionmaker.
  2. Pings PG.
  3. Builds httpx client.
  4. Starts reconciliation worker.
  5. `yield`.
  The FastStream broker lifespan auto-merges around this, but since we control the inner `yield`, the broker won't start subscribing until our setup completes... **except** for the broker connect itself, which happens at app-build time.
- **Belt-and-braces:** use FastStream's `@broker.subscriber(...).on_startup()` or `after_startup` hooks (verified pattern) to gate subscription on a "DB ready" event. Simplest version: a top-level `asyncio.Event` that's set after the DB ping; subscribers `await asyncio.wait_for(db_ready_event.wait(), timeout=30)` at top of handler. Ugly but bulletproof.
- **Simpler alternative for the test task:** rely on docker-compose's `depends_on: condition: service_healthy` for `postgres` and `rabbitmq` (Pitfall D1) — by the time bet-maker starts, both deps are healthy. Combined with PG `pool_pre_ping=True` (A3), the first DB call in a handler is guaranteed to work.

**Warning signs:**
- Logs at startup show "consumer started" before "postgres pinged ok".
- Tests pass locally but fail in CI with first-message DB errors.
- The first AMQP message after boot fails; the second succeeds.

**Phase to address:** P5 (custom lifespan), strengthened by P1 (compose healthchecks).

---

### Pitfall F4: Manual ack pattern — ack before commit or commit before ack

**What goes wrong:**
- **Ack-before-commit:** ack first, then commit. If commit fails, the message is gone; the DB is unchanged. Bet stays PENDING.
- **Commit-before-ack:** commit first, then ack. If ack fails, the message is redelivered; the second processing should be a no-op due to idempotency (R2). This is the **correct** order.

The trap: a junior implementation puts `await msg.ack()` at the top of the handler ("get rid of it before something fails"). Or puts it inside the `async with uow:` block (which means ack happens *inside* the transaction, before commit-on-exit).

**Why it happens:**
"Ack early" sounds like a good idea (less work for the broker). It's the wrong idea.

**How to avoid:**
Strict order: `async with uow: ... ; await msg.ack()`. Commit happens on `__aexit__`, then ack. Never ack inside the `with` block.

```python
try:
    async with uow:                                  # commit on __aexit__
        await settle_bets_for_event(uow, event_id=body.event_id, new_state=body.new_state)
except Exception:
    await msg.nack(requeue=True)                     # transaction rolled back
    raise
await msg.ack()                                      # only after successful commit
```

**Warning signs:**
- `await msg.ack()` appears inside `async with uow:` block.
- `await msg.ack()` appears at the top of the handler.
- Logs show "ack" before "commit" — wrong order.

**Phase to address:** P5 (consumer impl). Code review checklist item.

---

### Pitfall F5: Two RabbitBroker instances per process (subscriber + publisher)

**What goes wrong:**
Common pattern: declare a `RabbitRouter` for the consumer side and a fresh `RabbitBroker("amqp://...")` in HTTP routes for publishing. Two connection pools, two lifespans, often diverged config. Subtle bugs: publisher uses a different DSN, or different durability defaults, or different exchange.

**Why it happens:**
The FastAPI integration shows `RabbitRouter` for consumers; the standalone FastStream docs show `RabbitBroker` for publishers. Devs copy both.

**How to avoid:**
Publish via `router.broker.publish(...)` — the same broker the subscriber uses. Wrap in a tiny `EventBus` facade injected via `Depends`. Anti-Pattern 5 in ARCHITECTURE.md.

```python
# facades/event_bus.py (line-provider)
class EventBus:
    def __init__(self, broker: RabbitBroker) -> None:
        self._broker = broker
    async def publish(self, message, *, routing_key: str) -> None:
        await self._broker.publish(message, exchange="events", routing_key=routing_key)

def get_event_bus(router: RabbitRouter = Depends(get_router)) -> EventBus:
    return EventBus(router.broker)
```

**Warning signs:**
- Two `RabbitBroker(...)` constructions in the process.
- Publish from HTTP route imports `from faststream.rabbit import RabbitBroker` directly (not via `router.broker`).
- AsyncAPI doc at `/asyncapi` only shows one side (subscriber or publisher, not both).

**Phase to address:** P5 (broker module).

---

### Pitfall F6: `TestRabbitBroker` ≠ real broker (DLX/quorum/precondition silently pass)

**What goes wrong:**
FastStream's `TestRabbitBroker` is in-memory: subscribers and publishers are patched, handlers run synchronously inside the same asyncio task. It does **not** declare exchanges/queues on a real broker, does **not** evaluate routing keys against bindings, does **not** simulate DLX behaviour. A test using only `TestRabbitBroker` will pass even if the production queue declaration is broken (R5), the DLX binding is missing, or routing keys don't match.

**Why it happens:**
TestRabbitBroker is fast and convenient. Devs rely on it exclusively.

**How to avoid:**
Two-tier test strategy (ARCHITECTURE.md "Testing Architecture"):
1. **TestRabbitBroker** for handler logic — most tests.
2. **One real RabbitMQ container (testcontainers or compose-up fixture)** for the e2e path — at least one test that exercises actual exchange/queue/DLX wiring and asserts via `rabbitmqctl list_queues / list_exchanges` that the topology is correct.

**Warning signs:**
- All consumer tests use TestRabbitBroker; no test uses a real broker.
- A test passes that declares the queue with `durable=False` (real RabbitMQ would reject due to mismatch with the production declaration).
- DLX never receives messages in tests — there's no test that actually nacks-with-no-requeue and asserts the DLQ count.

**Phase to address:** P5 (consumer tests with TestRabbitBroker); P5 or P6 (one e2e test with real RabbitMQ).

---

### Pitfall F7: Schema versioning silently broken across deploy

**What goes wrong:**
line-provider gains a new field (`tournament_id`) in `EventFinishedMessage` and publishes with `schema_version=1` (forgot to bump). bet-maker is deployed last, with the new schema expecting `tournament_id`. The old line-provider keeps publishing without it. bet-maker raises `ValidationError`, nacks → poison loop (R7) or DLQ. Bets stay PENDING.

Reverse: bet-maker is deployed first, schema_version still 1, but it now ignores fields it doesn't recognise (Pydantic v2 default). line-provider publishes a v2 message; bet-maker silently drops the new field. Worse, if v2 changes the semantics of an existing field, bet-maker mis-interprets.

**Why it happens:**
No schema-version contract enforcement. Pydantic v2 `extra="ignore"` (default) hides new fields; `extra="forbid"` (recommended for messages) raises.

**How to avoid:**
- `EventFinishedMessage` has `model_config = ConfigDict(frozen=True, extra="forbid")` (already in ARCHITECTURE.md) and a `schema_version: int = 1` field with `Field(ge=1)`.
- Consumer checks `body.schema_version <= MAX_SUPPORTED_VERSION` at top of handler:
  ```python
  if body.schema_version > 1:
      log.warn("schema_version.unsupported", got=body.schema_version, supported=1)
      await msg.reject(requeue=False)   # poison-route to DLQ; do NOT requeue
      return
  ```
- For changes: never edit `schema_version=1`. Add `schema_version=2`, support both in the consumer for one release, then drop v1.

**Warning signs:**
- DLQ fills up after a deploy.
- Consumer logs show `ValidationError` with field names you don't recognise.
- The two services' `schemas/messages.py` files diverge.

**Phase to address:** P5 (message schema design); P7 (README mentions versioning policy).

---

### Pitfall F8: Routing key mismatch (publish vs binding)

**What goes wrong:**
Publisher uses routing key `event.finished.win` (singular), consumer's queue is bound with `events.finished.*` (plural). Message is published to the exchange, the exchange has no matching binding → message is **silently discarded** (no error, no DLQ for unrouted messages by default).

**Why it happens:**
RabbitMQ topic exchanges silently drop unroutable messages unless `mandatory=True` is set on the publish AND a return listener is configured.

**How to avoid:**
- Single source of truth for routing key constants in `schemas/messages.py` of line-provider, imported (duplicated) into bet-maker's `infrastructure/broker/rabbit.py`. ARCHITECTURE.md already does this — verify the constants match.
- Use `mandatory=True` on the publish; configure a return listener that logs unroutable messages. For a test task, the simpler check is an integration test that publishes one message and asserts the consumer received it.
- Document the routing key contract explicitly in the AsyncAPI spec (free with FastStream).

**Warning signs:**
- Messages "go nowhere" — published, no consumer log, no DLQ entry.
- `rabbitmqctl list_bindings` shows the binding key you didn't expect.
- AsyncAPI at `/asyncapi` shows routing keys that don't match the binding pattern.

**Phase to address:** P5 (exchange + binding declaration; e2e test).

---

## Critical Pitfalls — Docker / docker-compose

### Pitfall D1: `depends_on` without `condition: service_healthy` → service starts before deps are ready

**What goes wrong:**
Plain `depends_on: [postgres, rabbitmq]` only waits for the container to **start**, not for the service to **accept connections**. bet-maker boots, tries to ping PG in the lifespan, fails with `ConnectionRefusedError` (PG hasn't finished initdb yet). With a `tenacity` retry it eventually succeeds, but if retry attempts are exhausted the service exits and `restart: on-failure` flaps.

Worse: line-provider starts before RabbitMQ, the publish fails on the first PATCH, but if the failure isn't surfaced loudly, the developer thinks the wiring is broken.

**Why it happens:**
The Docker Compose default `depends_on` is process-start-order, not readiness. `condition: service_healthy` requires healthchecks on the depended-on services.

**How to avoid:**
```yaml
services:
  postgres:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
  rabbitmq:
    image: rabbitmq:4.2-management-alpine
    healthcheck:
      test: ["CMD-SHELL", "rabbitmq-diagnostics -q check_port_connectivity"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 15s
  bet-maker:
    depends_on:
      postgres: { condition: service_healthy }
      rabbitmq: { condition: service_healthy }
```
- Pair with `pool_pre_ping=True` on SQLAlchemy (A3) and `tenacity` retries in the lifespan, both belt-and-braces.
- `rabbitmq-diagnostics -q check_port_connectivity` is the right RabbitMQ check; the broader `rabbitmq-diagnostics -q ping` can return OK before the broker is actually accepting AMQP connections.

**Warning signs:**
- bet-maker logs `ConnectionRefusedError` on startup, then succeeds after retries.
- `docker compose up` exits with one service in `Exited` state.
- The first `curl :8000/health` after `docker compose up` returns 503 because deps weren't ready.

**Phase to address:** P1 (compose file).

---

### Pitfall D2: Healthcheck false positives (`pg_isready` returns OK before initdb completes initial role)

**What goes wrong:**
`pg_isready` returns OK once postgres's listener is up — but the first time a `postgres` container starts, it runs initdb scripts (creates the user, creates the DB) **after** the listener starts. `pg_isready` says OK; bet-maker connects with `app_user`; `app_user` doesn't exist yet; auth fails. Subsequent `docker compose up` (where the DB already exists) works fine. The bug only appears on a fresh checkout — exactly what the reviewer does.

**Why it happens:**
The official postgres image's init scripts run from `/docker-entrypoint-initdb.d/`. They complete after the listener is up. `pg_isready` doesn't know about init scripts.

**How to avoid:**
- Use `start_period: 15s` on the postgres healthcheck — gives initdb time to finish before any health check is considered failed (start_period suppresses unhealthy state during the grace window).
- Override the healthcheck to actually authenticate:
  ```yaml
  test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
  ```
- Belt-and-braces: bet-maker's lifespan pings PG with `SELECT 1` AS `app_user` and retries with `tenacity` on `OperationalError`. If init isn't done after retries, it crashes loud.

**Warning signs:**
- Fresh `docker compose up` (no existing volume) fails on first run but succeeds on the second.
- bet-maker logs `FATAL: role "app_user" does not exist`.
- Healthcheck reports postgres healthy immediately after start, before initdb actually finishes.

**Phase to address:** P1 (compose file healthcheck) + P3 (lifespan ping with retry).

---

### Pitfall D3: Persistent volumes missing / wrong path → state lost on every recreate

**What goes wrong:**
docker-compose.yml has no `volumes:` for postgres or rabbitmq. Every `docker compose up --force-recreate` wipes the DB and the queue state. For postgres this means `alembic upgrade head` must run every time (acceptable in dev, painful in CI). For RabbitMQ this means R10 fires.

**Why it happens:**
Compose volumes are opt-in. The default config has no persistence.

**How to avoid:**
```yaml
volumes:
  postgres_data:
  rabbitmq_data:

services:
  postgres:
    volumes:
      - postgres_data:/var/lib/postgresql/data
  rabbitmq:
    hostname: rabbitmq        # pin so mnesia node name stays stable across recreations
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
```

**Warning signs:**
- Bets disappear across `docker compose down && up`.
- RabbitMQ logs "Node not registered" after a restart (changed hostname → can't read old mnesia DB → R10).
- `docker volume ls` doesn't list `bsw_postgres_data` and `bsw_rabbitmq_data`.

**Phase to address:** P1 (compose file).

---

### Pitfall D4: SIGTERM not propagated → `docker compose down` SIGKILLs after 10s

**What goes wrong:**
Dockerfile has `CMD python -m uvicorn ...` (shell form). Container runs `/bin/sh -c "python -m uvicorn ..."`. PID 1 is `/bin/sh`. SIGTERM goes to PID 1 (/bin/sh), which does NOT forward signals by default. uvicorn never sees SIGTERM. After `stop_grace_period` (default 10s), Docker sends SIGKILL. In-flight AMQP messages are forcibly disconnected → requeued → R11 amplified.

**Why it happens:**
Shell-form CMD wraps in `sh -c`; `sh` does not forward SIGTERM to children (well-documented at https://petermalmgren.com/signal-handling-docker/).

**How to avoid:**
- **Exec form** for CMD/ENTRYPOINT:
  ```dockerfile
  CMD ["python", "-m", "uvicorn", "bet_maker.app:app", "--host", "0.0.0.0", "--port", "8000"]
  ```
- Or use `tini` as init: `ENTRYPOINT ["/usr/bin/tini", "--"]` (Debian-slim images have tini available; Docker also has `--init` flag, but exec form is simpler).
- docker-compose: `stop_grace_period: 30s` on bet-maker (FastStream `graceful_timeout=30.0` matches).

**Warning signs:**
- `docker compose down` takes exactly the full grace period before exiting.
- Container exit code 137 (SIGKILL) instead of 0.
- "graceful_timeout exceeded" never appears in logs (uvicorn never got the SIGTERM to start the timer).
- Logs end abruptly without shutdown messages.

**Phase to address:** P1 (Dockerfile).

---

### Pitfall D5: Log buffering hides errors during `docker compose up`

**What goes wrong:**
Python defaults to line-buffering stdout when stdout is a TTY, but **block-buffering when stdout is a pipe** (which `docker compose logs` is). A startup error happens and gets buffered. The container appears healthy in `docker compose ps` for 30 seconds. Then it crashes; the logs flush. Looks like a crash 30s after startup; was actually instant.

**Why it happens:**
Python's default. Same as the famous "print() in a Flask app shows nothing in Docker" issue.

**How to avoid:**
- Set `PYTHONUNBUFFERED=1` in the Dockerfile or compose `environment:`:
  ```dockerfile
  ENV PYTHONUNBUFFERED=1
  ```
- Or invoke Python with `-u`:
  ```dockerfile
  CMD ["python", "-u", "-m", "uvicorn", "..."]
  ```
- structlog with `JSONRenderer` writes one line per log call which is auto-flushed, but stdlib `print()` or any non-structlog logging still buffers. Set the env var to be safe.

**Warning signs:**
- Logs appear delayed in `docker compose logs -f`.
- Errors appear all at once after a delay.
- The container crashed but you saw no log for 30s.

**Phase to address:** P1 (Dockerfile / compose env).

---

### Pitfall D6: `python:3.10-slim` rolling tag drift → Debian Trixie → asyncpg wheel surprise

**What goes wrong:**
Dockerfile uses `FROM python:3.10-slim`. The rolling `-slim` tag now resolves to Debian Trixie (Debian 13) as of mid-2025 (verified via docker-library/python repo). New glibc (2.39 vs Bookworm's 2.36), new OpenSSL, new build toolchain. asyncpg's prebuilt manylinux wheels still target older glibc — usually compatible — but if a binary dep silently changes or wheel isn't available for a new platform variant, you fall back to source build, which fails without `gcc`.

**Why it happens:**
"-slim" without distro is a rolling tag. Docker Hub re-points it on schedule.

**How to avoid:**
Pin the distro explicitly per STACK.md: `FROM python:3.10-slim-bookworm`. Use Bookworm (Debian 12) — the conservative LTS-style choice through mid-2028. Stick with it through the test-task lifetime.

**Warning signs:**
- `pip install asyncpg` falls back to "Building wheel for asyncpg" in CI (signal: prebuilt wheel didn't match platform).
- New CI failures after a Docker image cache miss with no code change.
- `gcc: command not found` during pip install on a slim image (need build deps for source builds).

**Phase to address:** P1 (Dockerfile).

---

### Pitfall D7: Bind-mount permissions break test fixtures (UID mismatch)

**What goes wrong:**
docker-compose mounts `./tests:/app/tests` for live test reload. The container runs as a non-root user (UID 1000); the bind mount is owned by your host user (also UID 1000 on Linux usually, but UID 501 on macOS). Tests that write coverage reports to `tests/.coverage` or pytest cache fail with `PermissionError`.

**Why it happens:**
Bind mounts retain host file ownership inside the container. Container's non-root user can read host-owned files only if UIDs align.

**How to avoid:**
- For CI / read-only test runs: don't bind-mount tests; copy them in `COPY tests /app/tests` and run pytest inside the container with no mount.
- For local dev with bind mounts: either (a) run the container as root in dev only, or (b) align UIDs with `--user $(id -u):$(id -g)`, or (c) avoid writes to bind-mounted paths by setting `PYTEST_CACHE_DIR=/tmp/pytest`.
- macOS specifics: Docker Desktop's gRPC-FUSE handles UID translation differently than Linux; testcontainers (per ARCHITECTURE.md) sidestep this entirely because they don't need bind mounts.

**Warning signs:**
- Tests pass on Linux dev machine, fail on macOS dev machine, or vice versa.
- `PermissionError: [Errno 13]` writing to a mounted directory.
- `.pytest_cache/.gitignore` ownership shows as `root:root` after a test run.

**Phase to address:** P1 (Dockerfile + compose) and P3 (testing fixtures).

---

### Pitfall D8: `network: host` or wrong network mode → service names don't resolve

**What goes wrong:**
Dev sets `network_mode: host` for one service to debug. DNS resolution for `postgres` and `rabbitmq` (compose's auto-generated service names) breaks because host network doesn't use compose's embedded DNS. Connection string `postgres://app@postgres/db` fails with `getaddrinfo failed`. Dev "fixes" by using `localhost` — now the code doesn't work in production-like compose, only in `network: host` mode.

**Why it happens:**
Compose's automatic service-name DNS is per-network. Host mode bypasses it.

**How to avoid:**
- All services on the default compose network (don't override `network_mode`).
- Use service names (`postgres`, `rabbitmq`) in connection strings, never `localhost` (per STACK.md).
- Bind app processes to `0.0.0.0`, not `127.0.0.1`, so external `docker compose exec` and the reviewer's host-side curl can reach them via the published port.

**Warning signs:**
- Connection strings contain `localhost` instead of service names.
- `docker compose exec bet-maker curl http://line-provider:8001/health` fails.
- One service has `network_mode: host` and the others don't.

**Phase to address:** P1 (compose file).

---

## Technical Debt Patterns

Shortcuts that might tempt you under time pressure. The "When Acceptable" column for a test task is mostly "never" — the test is graded on engineering maturity, so every shortcut visible in the codebase costs more than it saves. Listed for honest reasoning anyway.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Use `ack_policy=AckPolicy.REJECT_ON_ERROR` (default) instead of `MANUAL` | One less line of code, no try/except needed | Bets stuck in PENDING on any consumer crash; Core Value violated | **Never** for this task |
| Skip the reconciliation worker | One less worker, simpler lifespan | Single point of failure for the Core Value; one lost message = silent stuck bet forever | **Never** — it is the explicit defence-in-depth promise |
| Skip `with_for_update(skip_locked=True)` in `BetRepository.get_pending_locked()` | Slightly simpler query | Consumer + reconciler can double-process when both fire close together | **Never** — D9 is part of the contract |
| Hardcode RabbitMQ URL / PG DSN in code | Skip pydantic-settings | Can't be deployed to two different envs without code change; reviewer dings for it immediately | **Never** — pydantic-settings is 10 lines |
| Drop schema_version field from `EventFinishedMessage` | One less Pydantic field | First schema change becomes a redeploy-everything coordination problem | **Never** — the field is free |
| Skip Alembic, use `Base.metadata.create_all` | Skip migration learning curve | "Production-style" signal is gone; can't evolve schema safely | **Never** for this task; acceptable for a 1-hour spike |
| Skip volumes in docker-compose | Faster compose-up first time | State lost on every recreate (R10, D3); reviewer's bets vanish between runs | **Never** — volumes are 4 lines |
| Use shell-form CMD in Dockerfile | Slightly easier to write | SIGTERM not propagated → graceful shutdown broken (D4, R11) | **Never** — exec form is the same effort |
| Use `python:3.10-slim` rolling tag | Less typing | Tag drift breaks builds when Docker Hub re-points it (D6) | **Never** — pin distro |
| Skip `prefetch_count` config | One less line | OOM on settle storms (F2) at scale; invisible at test-task scale but is a "didn't think about it" signal | Acceptable for first PR; add by P5 finalization |
| Skip the e2e test on real RabbitMQ, rely only on `TestRabbitBroker` | Faster tests | Queue declaration mismatches and DLX bugs pass tests (F6, R5) | Acceptable for early iterations; one e2e test by P5 done |
| Skip `pool_pre_ping=True` | One less SQL ping per checkout | Stale connections after `docker restart postgres` (A3) | Acceptable for the test task's one-shot demo; mention in README that you'd add for production |
| Skip the `tenacity` retry on httpx calls from reconciler | One less decorator | Reconciler fails on transient network blips → undetected gaps in defence-in-depth (R8) | **Never** — tenacity is already in STACK.md |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| PostgreSQL via asyncpg | DSN starts with `postgres://` (psycopg2 convention) | Use `postgresql+asyncpg://...`; otherwise SQLAlchemy picks psycopg2 sync driver and you get sync-in-async hangs |
| PostgreSQL connection pool | Single pool shared across replicas via PgBouncer in transaction mode | Don't use transaction-pool mode with asyncpg — server-side prepared statements break. Use session pooling, or skip PgBouncer entirely for the test task |
| RabbitMQ via FastStream | Declaring queue with no `arguments={}` first deploy, then adding `x-dead-letter-exchange` next deploy | PRECONDITION_FAILED loop (R5). Declare all arguments on day one; rename the queue if changing |
| RabbitMQ exchange type | Using `direct` exchange and matching routing key exactly | Use `topic` (per ARCHITECTURE.md) — survives adding new routing keys without rebinding |
| RabbitMQ ack flow | Calling `msg.ack()` once, hoping ack is idempotent | Calling ack twice raises `aio_pika.exceptions.MessageProcessError`. Wrap in `if not msg.processed:` or rely on the try/except/else structure |
| line-provider → bet-maker over HTTP | Sharing one `httpx.AsyncClient` across event loops (e.g., pytest fixture scope mismatch) | One client per event loop; fixture scope must match (function-scoped client for function-scoped loop) |
| line-provider → bet-maker (reverse) | Adding a back-channel from bet-maker to line-provider | Per ARCHITECTURE.md, bet-maker does NOT publish or push back. Resist the urge |
| Alembic with async engine | Running `alembic upgrade head` against the same engine the app uses, while the app is running | Alembic's `connectable.connect()` uses one connection; concurrent app holds the pool — works, but `transaction_per_migration=True` and migration locks can deadlock. For the test task, migrate once at startup before the app starts taking traffic |
| Docker Compose service-to-service | Using `localhost` in connection strings inside containers | Use compose service names: `postgres`, `rabbitmq`, `line-provider`, `bet-maker` |
| Docker network publishing | Binding uvicorn to `127.0.0.1` | Bind to `0.0.0.0` — `127.0.0.1` inside the container is not reachable from the host |

## Performance Traps

The test task's scale is "the reviewer runs `docker compose up` once." So thresholds are aspirational, not load-tested. They matter as "would this scale?" reasoning points for the reviewer.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| N+1 queries in `list_bets` (selector lazy-loads `bet.event` per row) | `GET /bets` latency grows linearly with row count; PG logs show N+1 selects | No relationships on `Bet` in this design — but if added, use `selectinload(Bet.event)` | At ~50 bets + 50 events visible |
| Reconciler hits line-provider in a tight loop (no batching) | line-provider CPU spikes during reconciliation tick | For now: single-event GET, batched once `GET /events?ids=...` is implemented (deferred per ARCHITECTURE.md) | At ~100 PENDING events |
| asyncpg pool exhaustion on settle storm | Requests hang waiting for connection; `psql -c 'select count(*) from pg_stat_activity'` near `max_connections` | `pool_size=10, max_overflow=20` (A3); batch the settle (`UPDATE bets SET status WHERE event_id = X` is one statement, not N) | At ~50 simultaneous settle ops |
| RabbitMQ prefetch unlimited → consumer OOM | bet-maker memory spikes; OOMKilled | `prefetch_count=10` per F2 | At ~10k unprocessed messages |
| structlog JSON renderer + many keys | Single log line >5KB; stdout backpressure under high logging volume | Bind minimal context (`event_id`, `correlation_id`, `request_id`); avoid binding entire DTOs | At ~10k log lines/second |
| FastStream auto-ack with `ACK_FIRST` policy used for "throughput" | Message loss on any worker crash | Use MANUAL always — for this task throughput is not the optimization target | Never; correctness > throughput here |
| Pydantic v2 deep validation of large response bodies | `GET /bets` latency dominated by Pydantic on huge result sets | Use `from_attributes=True` validation (skips reparse); paginate `GET /bets` (limit, offset) | At ~1000 bets/response |
| In-memory dict in line-provider grows unbounded | line-provider memory grows linearly with all events ever created | TZ says in-memory — bounded by reviewer's test scenario. Acceptable; mention in README that production would use a TTL'd structure or move to DB | At ~100k events created |

## Security Mistakes

The TZ is explicit: no authn/authz. So traditional auth pitfalls are out of scope. The remaining concerns are operational hygiene that a reviewer notices.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Default `guest:guest` RabbitMQ credentials in docker-compose committed to git | Reviewer screenshots the docker-compose file with prod-looking config — bad signal | Use a `.env.example` with placeholder values and a real `.env` (gitignored); pydantic-settings reads from env |
| PG password in compose `command:` arguments | Visible in `ps aux` inside the container | Use compose env vars or Docker secrets; `POSTGRES_PASSWORD=...` in `environment:` is the conventional choice for a test task |
| `expose: 5432` to host with no auth | If reviewer happens to have postgres locally, port conflict; also exposes a dev DB to the local network | `ports:` exposes; `expose:` is container-network only. Use `expose: 5432` not `ports: 5432:5432` unless you specifically want host access |
| Logging full request bodies (including Decimal amounts → easy to skim user inputs) | "PII" in a notional sense — bets are user actions | structlog binding should exclude raw bodies; log shape/structure, not values. For a test task, less critical |
| `pydantic-settings` reads from .env that's committed | Secrets in git | `.env.example` checked in with placeholder values; `.env` in `.gitignore` |
| Exposing RabbitMQ Management UI on `0.0.0.0:15672` with default credentials in production | Anyone on the LAN can publish/purge messages | For the test task, this is the demo path — explicit `127.0.0.1:15672:15672` binding limits exposure to the reviewer's host |
| Verbose error responses leaking internal stack traces | Reveals stack/version info | FastAPI's default 500 handler in production mode is generic; ensure `debug=False` |
| AMQP credentials in connection URL logged on startup | Password in stdout | structlog masking processor for `amqp_url` field; or split credentials into separate config fields |

## "Looks Done But Isn't" Checklist

Use during P7 verification before declaring done. Each item is a thing that "looks complete" but has a hidden gap.

- [ ] **Manual ack:** every `@router.subscriber(...)` has `ack_policy=AckPolicy.MANUAL` AND an explicit `await msg.ack()` AFTER the UoW commits — grep for `subscriber(` and verify each one.
- [ ] **Idempotency:** the consumer handler runs **twice** on the same message (test that simulates broker redelivery) and produces no duplicate settlement, no error.
- [ ] **Reconciliation:** the worker loop body is wrapped in `try/except Exception:` so a single failed tick doesn't kill the loop. Verified by a test that raises in `reconcile_pending_bets`.
- [ ] **FOR UPDATE SKIP LOCKED:** the `BetRepository.get_pending_locked()` SQL is `... WITH FOR UPDATE SKIP LOCKED`. Verified by `select` output or `EXPLAIN`.
- [ ] **Durable queue + persistent messages:** `rabbitmqctl list_queues name durable messages` shows `durable=true` and surviving across `docker compose restart rabbitmq`.
- [ ] **Volumes:** `docker volume ls` lists both `bsw_postgres_data` and `bsw_rabbitmq_data`. After `docker compose down && docker compose up`, bets and queue state persist.
- [ ] **Healthcheck wired:** `docker compose ps` shows `(healthy)` next to postgres and rabbitmq before bet-maker / line-provider start.
- [ ] **`/health` checks deps:** `curl /health` returns `{"postgres":"ok","rabbitmq":"ok"}`, not just `{"ok":true}`. Returns 503 when PG is intentionally stopped (`docker compose stop postgres`).
- [ ] **DLQ wired:** force a poison message; verify it lands in `bet_maker.events.finished.dlq` (visible in RabbitMQ Management UI).
- [ ] **Schema version checked:** publish a message with `schema_version=99`; verify the consumer rejects to DLQ, doesn't crash.
- [ ] **expire_on_commit=False:** `async_sessionmaker(engine, expire_on_commit=False)` is the call. Selectors return Pydantic DTOs, never raw ORM. Verified by static check (grep for `return Bet(`, `return rows.scalars()` outside `BetRead.model_validate`).
- [ ] **SIGTERM handled:** `docker compose down` finishes in < 5s with exit code 0 in logs (not 137 / SIGKILL).
- [ ] **`python:3.10-slim-bookworm` pinned** (not rolling `python:3.10-slim`).
- [ ] **PYTHONUNBUFFERED=1** set so logs aren't buffered.
- [ ] **CMD in exec form:** `CMD ["python", ...]` not `CMD python ...`.
- [ ] **structlog clear_contextvars** in middleware and consumer handler, in `try/finally`.
- [ ] **mypy --strict** passes (CI gate); no `# type: ignore` on critical paths (UoW, repositories, handler signatures).
- [ ] **Decimal validation:** POST /bet with `amount=10.123` returns 422 (Pydantic `decimal_places=2`).
- [ ] **Decimal storage exact:** POST /bet with `amount=10.00`, GET /bets returns `"10.00"` (string) — exact roundtrip.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| R1 (auto-ack crash mid-process loses message) | LOW (already covered by reconciler) | Wait one reconciliation tick — bet settles. For affected events, manually trigger `POST /reconcile` if you add a debug endpoint |
| R4 (queue not durable, messages lost on restart) | HIGH (data loss; only reconciler recovers, and only if line-provider still knows the terminal state) | Run reconciler; for events line-provider no longer remembers (in-memory store wiped too), there is no recovery — bets stay PENDING. Mitigation: don't restart RabbitMQ without ensuring line-provider's state survives |
| R5 (queue PRECONDITION_FAILED) | MEDIUM | Stop bet-maker; `rabbitmqctl delete_queue bet_maker.events.finished`; restart bet-maker (re-declares with new args); reconciler backfills any bets that arrived during the outage |
| R7 (poison loop) | MEDIUM | Identify poison via `rabbitmqctl list_queues messages_ready` not decreasing; inspect message via Management UI; either fix the consumer code (deploy) or manually `reject(requeue=False)` the message via a debug endpoint |
| R8 (reconciler dies silently) | LOW | Restart the bet-maker container; `/health` should be upgraded to detect this in the first place |
| R10 (compose down -v wiped state) | HIGH | Restore from `pg_dump` if available; otherwise re-create test data. For the test task: just re-run the scenario |
| F3 (lifespan order wrong, first message fails) | LOW | After a few seconds the DB is up; reconciler picks up the missed event from line-provider |
| A1 (`MissingGreenlet`) | LOW | Add `expire_on_commit=False` and convert selectors to DTOs |
| A2 (`InterfaceError: another operation in progress`) | LOW | Search for shared sessions; refactor to per-UoW session |
| D4 (SIGKILL after grace period) | LOW | Switch CMD to exec form; redeploy |

## Pitfall-to-Phase Mapping

The "Phase" column is the **first** phase where the pitfall must be prevented; some span multiple phases.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| R1 — Auto-ack consumer crash | P5 | Unit test: handler raises → message redelivered (TestRabbitBroker) |
| R2 — Ack/commit split-brain | P5 | Unit test: handler runs twice on same message, settles only once |
| R3 — Consumer + reconciler race | P5 (FOR UPDATE) | P6 test: run consumer + reconciler concurrently against the same event |
| R4 — Queue not durable, persistent | P5 (queue decl) + P1 (volume) | `rabbitmqctl list_queues name durable` + `docker compose restart rabbitmq` test |
| R5 — Queue redeclare mismatch | P5 (initial decl) + P7 (README rename-not-edit policy) | Integration test asserting queue arguments match expected |
| R6 — Healthcheck reports OK while consumer broken | P5 (basic) + P6 or P7 (subscriber-count assertion) | Manually kill subscriber, hit /health, expect 503 |
| R7 — Poison-message loop | P5 (error-handling discipline + DLX) | Test: publish bad payload, verify DLQ count = 1 |
| R8 — Reconciler dies silently | P6 (try/except wrap + task name) | Test: inject exception in reconciler body, loop continues |
| R9 — Reconciler-vs-publish order | P2 (line-provider order) + P6 (reconciler logic) | Test: simulate publish-fail-after-store-write, reconciler must settle |
| R10 — docker compose down -v wipes state | P1 (volumes + hostname) | Manual test: bets survive `docker compose down && up` |
| R11 — Restart with unacked messages | P1 (Dockerfile exec form + stop_grace_period) + P5 (graceful_timeout) | Manual test: send messages, `docker compose down`, expect 0 exit code |
| R12 — Publish inside DB transaction | P2 (line-provider order) — bet-maker doesn't publish | Code review |
| A1 — MissingGreenlet on lazy load | P3 (expire_on_commit=False + DTO selectors) | mypy + integration test |
| A2 — Shared AsyncSession | P3 (UoW per request) | Static check: grep for module-level sessions |
| A3 — asyncpg pool too small | P3 (engine config) | Code review |
| A4 — Decimal coercion drift | P3 (Pydantic schemas + money helper) | Unit test exact roundtrip |
| A5 — NUMERIC ↔ Decimal precision | P3 (Bet model) | mypy + unit test |
| A6 — Alembic env.py sync | P3 (`alembic init -t async`) | `alembic upgrade head` succeeds in CI |
| A7 — structlog cross-task contamination | P1 (middleware) + P5 (consumer clear_contextvars) | Concurrent test asserting log isolation |
| F1 — Wrong ack_policy | P5 | Code review + integration test |
| F2 — Prefetch unlimited | P5 (broker config) | `rabbitmqctl list_consumers` shows prefetch_count=10 |
| F3 — Lifespan order | P5 (custom lifespan) + P1 (compose healthchecks) | Smoke test: first message after boot succeeds |
| F4 — Ack-before-commit | P5 (consumer impl) | Code review |
| F5 — Two RabbitBroker instances | P5 (EventBus facade) | grep for `RabbitBroker(` outside the broker module |
| F6 — TestRabbitBroker only | P5 | Add one real-RabbitMQ e2e test |
| F7 — Schema versioning | P5 (schema design) | Test: publish schema_version=99, expect DLQ |
| F8 — Routing key mismatch | P5 (exchange + binding) | E2E test on real broker |
| D1 — depends_on without healthy | P1 | `docker compose up` first run works |
| D2 — Healthcheck false positive | P1 (start_period) + P3 (lifespan ping retry) | Fresh-checkout test |
| D3 — Volumes missing | P1 | Bets survive recreate |
| D4 — SIGTERM not propagated | P1 (Dockerfile exec form) | `docker compose down` exit code 0 in 5s |
| D5 — Log buffering | P1 (`PYTHONUNBUFFERED=1`) | Logs appear in real time |
| D6 — Python image rolling tag | P1 (`python:3.10-slim-bookworm`) | Dockerfile review |
| D7 — Bind-mount permissions | P1 / P3 (testing fixtures) | Tests run in CI without permission errors |
| D8 — Wrong network mode | P1 | Services resolve each other by name |

## Sources

- `/ag2ai/faststream` (Context7) — `AckPolicy.MANUAL` / `RabbitMessage.ack/nack/reject` semantics, FastStream 0.6 release notes on removed `retry=True/N` and new `ack_policy`, `RabbitBroker(graceful_timeout=...)`, `RabbitQueue(arguments={"x-dead-letter-exchange":...})`, `RabbitExchange`, `TestRabbitBroker` — **HIGH confidence**
- `/websites/sqlalchemy_en_20` (Context7) — `async_sessionmaker(expire_on_commit=False)`, `with_for_update(skip_locked=True)`, `MissingGreenlet` error description, `AsyncAttrs.awaitable_attrs`, asyncpg DBAPI URL conventions, pool config — **HIGH confidence**
- https://docs.sqlalchemy.org/en/20/errors.html (MissingGreenlet, DetachedInstanceError) — **HIGH confidence**
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html (AsyncSession, AsyncAttrs, expire_on_commit guidance) — **HIGH confidence**
- https://github.com/MagicStack/asyncpg/issues/258 and #863 — `InterfaceError: cannot perform operation: another operation is in progress` from shared connections — **HIGH confidence**
- https://github.com/sqlalchemy/sqlalchemy/issues/5967 — asyncpg-with-SQLAlchemy concurrent-operation issue — **HIGH confidence**
- https://www.rabbitmq.com/docs/quorum-queues — `x-delivery-count`, default delivery-limit=20 on quorum queues (RabbitMQ 4.0+) — **HIGH confidence**
- https://www.rabbitmq.com/docs/consumer-prefetch — default unlimited prefetch, basic.qos semantics — **HIGH confidence**
- https://groups.google.com/g/rabbitmq-users/c/rwhtLMrZ1rY — PRECONDITION_FAILED inequivalent arg 'durable' across declarations — **HIGH confidence**
- https://github.com/mosquito/aio-pika/issues/165 — declare_queue with changed arguments fails with PRECONDITION_FAILED — **HIGH confidence**
- https://www.postgresql.org/docs/current/transaction-iso.html — READ COMMITTED snapshot semantics with FOR UPDATE / SKIP LOCKED, EvalPlanQual behaviour — **HIGH confidence**
- https://docs.docker.com/compose/compose-file/#depends_on — `condition: service_healthy` semantics — **HIGH confidence**
- https://hub.docker.com/_/python — slim tag distro defaults, bookworm vs trixie — **HIGH confidence**
- https://github.com/docker-library/python/blob/main/3.10/slim-trixie/Dockerfile and slim-bookworm — Debian distro choice — **HIGH confidence**
- https://petermalmgren.com/signal-handling-docker/ — PID 1 signal handling, exec form vs shell form, tini — **HIGH confidence**
- https://www.structlog.org/en/stable/contextvars.html — `bind_contextvars`, `clear_contextvars`, asyncio task-local semantics — **HIGH confidence**
- https://github.com/hynek/structlog/issues/248 and PR #302 — contextvars implementation, cross-task isolation fix in 21.1.0 — **HIGH confidence**
- https://docs.pydantic.dev/latest/migration/ — Pydantic v2 Decimal string serialization change — **HIGH confidence**
- https://github.com/pydantic/pydantic/issues/6295 and /discussions/8505 — Decimal precision and serialization in v2 — **HIGH confidence**
- https://faststream.ag2.ai/latest/api/faststream/rabbit/fastapi/fastapi/RabbitRouter/ — RabbitRouter API, FastAPI integration — **HIGH confidence**
- https://github.com/fastapi/fastapi/pull/9630 — FastAPI nested lifespan merging — **HIGH confidence**
- `/Users/dmitrydankov/Personal/BSW/.planning/PROJECT.md` — Core Value invariant, Out of Scope (no outbox, in-memory line-provider) — **HIGH confidence**
- `/Users/dmitrydankov/Personal/BSW/.planning/research/STACK.md` — pinned versions, Decimal handling, exec-form Dockerfile guidance, `python:3.10-slim-bookworm` choice — **HIGH confidence**
- `/Users/dmitrydankov/Personal/BSW/.planning/research/ARCHITECTURE.md` — UoW shape, AMQP topology, lifespan order, layered architecture, anti-patterns — **HIGH confidence**

---
*Pitfalls research for: two-service asynchronous Python betting system (FastAPI + FastStream + asyncpg + SQLAlchemy 2.0 async + reconciliation + Docker compose)*
*Researched: 2026-05-13*
