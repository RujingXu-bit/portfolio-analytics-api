from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest

from portfolio_analytics_api.application import (
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataRateLimitError,
    MarketDataResult,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
)
from portfolio_analytics_api.infrastructure import TwelveDataMarketDataProvider


def _payload() -> dict[str, object]:
    return {
        "meta": {
            "symbol": "AAPL",
            "interval": "1day",
            "exchange_timezone": "America/New_York",
        },
        "values": [
            {"datetime": "2025-01-06", "close": "243.39742"},
            {"datetime": "2025-01-03", "close": "241.76815"},
            {"datetime": "2025-01-02", "close": "242.25495"},
        ],
        "status": "ok",
    }


async def _call_with_handler(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[MarketDataResult, httpx.Request]:
    captured_request: httpx.Request | None = None

    def capture(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return handler(request)

    async with httpx.AsyncClient(
        base_url="https://api.twelvedata.test",
        transport=httpx.MockTransport(capture),
    ) as client:
        provider = TwelveDataMarketDataProvider(api_key="secret-key", client=client)
        result = await provider.get_price_bars(
            " aapl ",
            date(2025, 1, 2),
            date(2025, 1, 6),
        )
    assert captured_request is not None
    return result, captured_request


@pytest.mark.anyio
async def test_provider_requests_total_return_adjustment_and_normalizes_rows() -> None:
    result, request = await _call_with_handler(
        lambda request: httpx.Response(200, json=_payload(), request=request)
    )

    assert request.url.path == "/time_series"
    assert request.url.params["symbol"] == "AAPL"
    assert request.url.params["interval"] == "1day"
    assert request.url.params["start_date"] == "2025-01-02"
    assert request.url.params["end_date"] == "2025-01-06"
    assert request.url.params["adjust"] == "all"
    assert request.url.params["apikey"] == "secret-key"
    assert [bar.date for bar in result.price_bars] == [
        date(2025, 1, 2),
        date(2025, 1, 3),
        date(2025, 1, 6),
    ]
    assert result.price_bars[0].adjusted_close == Decimal("242.25495")
    assert all(bar.symbol == "AAPL" for bar in result.price_bars)
    assert result.stale is False


@pytest.mark.anyio
async def test_provider_filters_rows_outside_requested_range() -> None:
    payload = _payload()
    values = payload["values"]
    assert isinstance(values, list)
    values.append({"datetime": "2025-01-01", "close": "1"})

    result, _ = await _call_with_handler(
        lambda request: httpx.Response(200, json=payload, request=request)
    )

    assert all(bar.date >= date(2025, 1, 2) for bar in result.price_bars)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (404, MarketDataNotFoundError),
        (429, MarketDataRateLimitError),
        (500, MarketDataUnavailableError),
        (401, MarketDataInvalidResponseError),
    ],
)
async def test_provider_maps_http_failures_to_stable_errors(
    status_code: int,
    expected_error: type[Exception],
) -> None:
    async with httpx.AsyncClient(
        base_url="https://api.twelvedata.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code, request=request)
        ),
    ) as client:
        provider = TwelveDataMarketDataProvider(api_key="secret-key", client=client)
        with pytest.raises(expected_error):
            await provider.get_price_bars("AAPL", date(2025, 1, 2), date(2025, 1, 6))


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"status": "error", "code": 400}, MarketDataNotFoundError),
        ({"status": "error", "code": 429}, MarketDataRateLimitError),
        ({"status": "error", "code": 503}, MarketDataUnavailableError),
        ({"status": "error", "code": 401}, MarketDataInvalidResponseError),
    ],
)
async def test_provider_maps_json_error_envelopes(
    payload: dict[str, object],
    expected_error: type[Exception],
) -> None:
    async with httpx.AsyncClient(
        base_url="https://api.twelvedata.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload, request=request)
        ),
    ) as client:
        provider = TwelveDataMarketDataProvider(api_key="secret-key", client=client)
        with pytest.raises(expected_error):
            await provider.get_price_bars("AAPL", date(2025, 1, 2), date(2025, 1, 6))


@pytest.mark.anyio
async def test_provider_maps_transport_timeout() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(
        base_url="https://api.twelvedata.test",
        transport=httpx.MockTransport(timeout),
    ) as client:
        provider = TwelveDataMarketDataProvider(api_key="secret-key", client=client)
        with pytest.raises(MarketDataTimeoutError):
            await provider.get_price_bars("AAPL", date(2025, 1, 2), date(2025, 1, 6))


@pytest.mark.anyio
async def test_provider_maps_transport_failure() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unavailable", request=request)

    async with httpx.AsyncClient(
        base_url="https://api.twelvedata.test",
        transport=httpx.MockTransport(fail),
    ) as client:
        provider = TwelveDataMarketDataProvider(api_key="secret-key", client=client)
        with pytest.raises(MarketDataUnavailableError):
            await provider.get_price_bars("AAPL", date(2025, 1, 2), date(2025, 1, 6))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(status="unexpected"),
        lambda payload: payload.update(meta={}),
        lambda payload: payload.update(values="not-a-list"),
        lambda payload: payload["values"].append("not-an-object"),
        lambda payload: payload["values"].append(
            {"datetime": "not-a-date", "close": "1"}
        ),
        lambda payload: payload["values"].append(
            {"datetime": "2025-01-03", "close": "1"}
        ),
        lambda payload: payload["values"].append(
            {"datetime": "2025-01-04", "close": "NaN"}
        ),
    ],
)
async def test_provider_rejects_malformed_payloads(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    payload = _payload()
    mutate(payload)
    async with httpx.AsyncClient(
        base_url="https://api.twelvedata.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload, request=request)
        ),
    ) as client:
        provider = TwelveDataMarketDataProvider(api_key="secret-key", client=client)
        with pytest.raises(MarketDataInvalidResponseError):
            await provider.get_price_bars("AAPL", date(2025, 1, 2), date(2025, 1, 6))


@pytest.mark.anyio
async def test_provider_rejects_non_json_response() -> None:
    async with httpx.AsyncClient(
        base_url="https://api.twelvedata.test",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text="not-json", request=request)
        ),
    ) as client:
        provider = TwelveDataMarketDataProvider(api_key="secret-key", client=client)
        with pytest.raises(MarketDataInvalidResponseError, match="not JSON"):
            await provider.get_price_bars("AAPL", date(2025, 1, 2), date(2025, 1, 6))


@pytest.mark.anyio
async def test_provider_validates_configuration_and_query() -> None:
    with pytest.raises(ValueError, match="API key"):
        TwelveDataMarketDataProvider(api_key=" ")
    with pytest.raises(ValueError, match="positive"):
        TwelveDataMarketDataProvider(api_key="key", request_timeout_seconds=0)
    with pytest.raises(ValueError, match="base_url"):
        TwelveDataMarketDataProvider(api_key="key", base_url=" ")

    provider = TwelveDataMarketDataProvider(api_key="key")
    with pytest.raises(MarketDataNotFoundError):
        await provider.get_price_bars(" ", date(2025, 1, 2), date(2025, 1, 6))
    with pytest.raises(ValueError, match="start_date"):
        await provider.get_price_bars("AAPL", date(2025, 1, 7), date(2025, 1, 6))
