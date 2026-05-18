"""Shared HTTP retry-factory + LineProviderUnavailable exception.

LineProviderUnavailable signals "line-provider unreachable after retry
exhaustion". Route layer (POST /bet, GET /events) maps it to HTTP 503.
The place_bet interactor must NOT catch this — it propagates straight
through to the route ladder.

make_retry_decorator is the single retry-factory shared between
HttpEventLookup and list_active_events. The reconciler instantiates it
again with attempts=5, max_backoff=10.0.

Retry on httpx.TransportError (timeout/connect/network) and
httpx.HTTPStatusError where status_code >= 500. 4xx responses are LP's
contract responses and propagate without retry.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx
import structlog
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = structlog.get_logger()

_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])

_HTTP_5XX_FLOOR = 500


class LineProviderUnavailable(Exception):  # noqa: N818
    """line-provider unreachable after retry exhaustion.

    Route layer maps this to HTTP 503 with a static detail string.
    The place_bet interactor MUST NOT catch this.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _is_retryable(exc: BaseException) -> bool:
    """Retry on TransportError (timeout/connect/network) and 5xx
    HTTPStatusError. 4xx propagates without retry (contract responses).
    Avoid blanket retry_if_exception_type(HTTPStatusError) which would
    also retry 422 (amount > 2dp) — a user error.
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= _HTTP_5XX_FLOOR
    return False


def _log_before_sleep(retry_state: RetryCallState) -> None:
    """Emit structured retry log so retries are observable in JSON logs.

    Keep all retry state inside retry_state — no module-level contextvars
    (those belong to request-scoped bindings).
    """
    sleep_s = retry_state.next_action.sleep if retry_state.next_action else 0.0
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    log.warning(
        "line_provider.http.retry",
        attempt_number=retry_state.attempt_number,
        sleep_s=sleep_s,
        exception_type=type(exc).__name__ if exc else None,
    )


def make_retry_decorator(attempts: int, max_backoff: float) -> Callable[[_F], _F]:
    """Shared retry-factory. Reused by HttpEventLookup, list_active_events,
    and the reconciler with different params.

    Args:
        attempts: total attempts (stop_after_attempt). Default = 3 for HTTP
            routes; reconciler passes 5.
        max_backoff: upper cap on exponential wait. Default = 2.0s for HTTP
            routes; reconciler passes 10.0.
    """
    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=max_backoff),
        retry=retry_if_exception(_is_retryable),
        before_sleep=_log_before_sleep,
        reraise=True,
    )
