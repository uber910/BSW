"""Unit tests for facades/line_provider_client.py — predicate + factory.

BM-04 / D-03 / D-05 / D-07: retry-factory behaviour. No HTTP server
needed — we test the predicate against fabricated httpx exceptions and
test the factory against a counter-style coroutine.
"""

from __future__ import annotations

import httpx
import pytest

from bet_maker.facades.line_provider_client import (
    LineProviderUnavailable,
    _is_retryable,
    make_retry_decorator,
)


class TestLineProviderUnavailable:
    """D-07: LineProviderUnavailable carries a reason attribute."""

    def test_reason_attribute_is_set(self) -> None:
        """D-07: .reason holds the string passed in __init__."""
        exc = LineProviderUnavailable(reason="connection refused")
        assert exc.reason == "connection refused"

    def test_str_returns_reason(self) -> None:
        """D-07: str(exc) yields the reason for traceback hygiene."""
        exc = LineProviderUnavailable(reason="timeout after 5s")
        assert str(exc) == "timeout after 5s"

    def test_subclass_of_exception(self) -> None:
        """D-07: LineProviderUnavailable is a regular Exception."""
        assert issubclass(LineProviderUnavailable, Exception)


class TestIsRetryable:
    """D-05: retry predicate — TransportError + 5xx are retryable; 4xx is not."""

    def test_transport_error_is_retryable(self) -> None:
        """D-05: httpx.TransportError -> True (covers timeout, connect, network)."""
        exc = httpx.ConnectError("connection refused")
        assert _is_retryable(exc) is True

    def test_read_timeout_is_retryable(self) -> None:
        """D-05: ReadTimeout is a TransportError subclass -> True."""
        exc = httpx.ReadTimeout("read timed out")
        assert _is_retryable(exc) is True

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_5xx_http_status_error_is_retryable(self, status_code: int) -> None:
        """D-05 / Pitfall 4: HTTPStatusError 5xx -> True."""
        request = httpx.Request("GET", "http://line-provider:8000/events")
        response = httpx.Response(status_code, request=request)
        exc = httpx.HTTPStatusError(f"upstream {status_code}", request=request, response=response)
        assert _is_retryable(exc) is True

    @pytest.mark.parametrize("status_code", [400, 404, 409, 422])
    def test_4xx_http_status_error_is_not_retryable(self, status_code: int) -> None:
        """D-05 / Pitfall 4: HTTPStatusError 4xx -> False (LP contract responses)."""
        request = httpx.Request("GET", "http://line-provider:8000/event/abc")
        response = httpx.Response(status_code, request=request)
        exc = httpx.HTTPStatusError(f"upstream {status_code}", request=request, response=response)
        assert _is_retryable(exc) is False

    def test_value_error_is_not_retryable(self) -> None:
        """D-05: arbitrary non-http exceptions do not trigger retry."""
        assert _is_retryable(ValueError("bad payload")) is False


class TestMakeRetryDecorator:
    """D-03 / D-11: factory returns a tenacity decorator with the right wiring."""

    def test_returns_callable_decorator(self) -> None:
        """make_retry_decorator returns a callable that can wrap a function."""
        decorator = make_retry_decorator(attempts=3, max_backoff=2.0)
        assert callable(decorator)

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self) -> None:
        """D-03: retryable exception once, success second time -> succeeds with no raise."""
        counter = {"calls": 0}

        decorator = make_retry_decorator(attempts=3, max_backoff=0.1)

        @decorator
        async def flaky() -> str:
            counter["calls"] += 1
            if counter["calls"] < 2:
                # Fabricate a retryable httpx.ConnectError on the first call
                raise httpx.ConnectError("transient")
            return "ok"

        result = await flaky()
        assert result == "ok"
        assert counter["calls"] == 2

    @pytest.mark.asyncio
    async def test_exhaustion_reraises_original(self) -> None:
        """D-03 / reraise=True: after `attempts` retries the original exc propagates."""
        counter = {"calls": 0}

        decorator = make_retry_decorator(attempts=2, max_backoff=0.1)

        @decorator
        async def always_fails() -> str:
            counter["calls"] += 1
            raise httpx.ConnectError("permanent")

        with pytest.raises(httpx.ConnectError):
            await always_fails()
        assert counter["calls"] == 2  # exactly `attempts` total

    @pytest.mark.asyncio
    async def test_non_retryable_propagates_immediately(self) -> None:
        """D-05: a 422 HTTPStatusError is NOT retried — exception fires on first call."""
        counter = {"calls": 0}

        decorator = make_retry_decorator(attempts=3, max_backoff=0.1)

        @decorator
        async def returns_422() -> str:
            counter["calls"] += 1
            request = httpx.Request("GET", "http://x/y")
            response = httpx.Response(422, request=request)
            raise httpx.HTTPStatusError("ve", request=request, response=response)

        with pytest.raises(httpx.HTTPStatusError):
            await returns_422()
        assert counter["calls"] == 1  # no retry
