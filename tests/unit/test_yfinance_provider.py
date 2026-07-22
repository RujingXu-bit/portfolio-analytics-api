import threading
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pandas as pd
import pytest
from curl_cffi.requests.exceptions import (
    ConnectionError as CurlConnectionError,
)
from curl_cffi.requests.exceptions import HTTPError, Timeout
from yfinance.exceptions import YFRateLimitError  # type: ignore[import-untyped]

from portfolio_analytics_api.application import (
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataRateLimitError,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
)
from portfolio_analytics_api.domain import PriceBar
from portfolio_analytics_api.infrastructure import YFinanceMarketDataProvider


def history_frame(
    dates: list[str],
    adjusted_closes: list[object],
    *,
    timezone: str | None = "America/New_York",
) -> pd.DataFrame:
    return pd.DataFrame(
        {"Adj Close": adjusted_closes},
        index=pd.DatetimeIndex(dates, tz=timezone, name="Date"),
    )


@pytest.mark.anyio
async def test_provider_normalizes_adjusted_close_off_event_loop() -> None:
    call: dict[str, object] = {}

    def loader(symbol: str, **kwargs: object) -> pd.DataFrame:
        call["symbol"] = symbol
        call["kwargs"] = kwargs
        call["thread_id"] = threading.get_ident()
        return history_frame(
            ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-07"],
            ["99", "100.125", "101.25", "102"],
        )

    event_loop_thread_id = threading.get_ident()
    provider = YFinanceMarketDataProvider(
        request_timeout_seconds=7.5,
        history_loader=loader,
    )

    result = await provider.get_price_bars(
        " aapl ",
        date(2026, 1, 2),
        date(2026, 1, 5),
    )

    assert result.price_bars == (
        PriceBar("AAPL", date(2026, 1, 2), Decimal("100.125")),
        PriceBar("AAPL", date(2026, 1, 5), Decimal("101.25")),
    )
    assert result.stale is False
    assert call["symbol"] == "AAPL"
    assert call["thread_id"] != event_loop_thread_id
    assert call["kwargs"] == {
        "start": date(2026, 1, 2),
        "end": date(2026, 1, 6),
        "interval": "1d",
        "actions": False,
        "auto_adjust": False,
        "back_adjust": False,
        "repair": False,
        "keepna": True,
        "timeout": 7.5,
    }


@pytest.mark.anyio
async def test_provider_reports_empty_history_as_not_found() -> None:
    provider = YFinanceMarketDataProvider(
        history_loader=lambda _symbol, **_kwargs: history_frame([], [])
    )

    with pytest.raises(MarketDataNotFoundError, match="UNKNOWN"):
        await provider.get_price_bars(
            "unknown",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (history_frame(["2026-01-02"], ["100"], timezone=None), "timezone"),
        (
            history_frame(["2026-01-02", "2026-01-02"], ["100", "101"]),
            "duplicate",
        ),
        (history_frame(["2026-01-02"], [None]), "missing"),
        (history_frame(["2026-01-02"], ["NaN"]), "missing"),
        (history_frame(["2026-01-02"], ["0"]), "positive"),
    ],
)
async def test_provider_rejects_invalid_market_data(
    frame: pd.DataFrame,
    message: str,
) -> None:
    provider = YFinanceMarketDataProvider(
        history_loader=lambda _symbol, **_kwargs: frame
    )

    with pytest.raises(MarketDataInvalidResponseError, match=message):
        await provider.get_price_bars(
            "AAPL",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )


@pytest.mark.anyio
async def test_provider_validates_configuration_and_query() -> None:
    with pytest.raises(ValueError, match="positive"):
        YFinanceMarketDataProvider(request_timeout_seconds=0)

    provider = YFinanceMarketDataProvider(
        history_loader=lambda _symbol, **_kwargs: history_frame([], [])
    )
    with pytest.raises(ValueError, match="start_date"):
        await provider.get_price_bars(
            "AAPL",
            date(2026, 2, 1),
            date(2026, 1, 1),
        )
    with pytest.raises(MarketDataNotFoundError):
        await provider.get_price_bars(
            "   ",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_error", "expected_error"),
    [
        (YFRateLimitError(), MarketDataRateLimitError),
        (Timeout("timed out"), MarketDataTimeoutError),
        (CurlConnectionError("connection failed"), MarketDataUnavailableError),
        (
            HTTPError(
                "rate limited",
                response=cast(Any, SimpleNamespace(status_code=429)),
            ),
            MarketDataRateLimitError,
        ),
        (
            HTTPError(
                "server error",
                response=cast(Any, SimpleNamespace(status_code=503)),
            ),
            MarketDataUnavailableError,
        ),
        (
            HTTPError(
                "not found",
                response=cast(Any, SimpleNamespace(status_code=404)),
            ),
            MarketDataNotFoundError,
        ),
        (
            HTTPError(
                "bad request",
                response=cast(Any, SimpleNamespace(status_code=400)),
            ),
            MarketDataInvalidResponseError,
        ),
    ],
)
async def test_provider_maps_vendor_failures_to_stable_errors(
    provider_error: Exception,
    expected_error: type[Exception],
) -> None:
    def loader(_symbol: str, **_kwargs: object) -> pd.DataFrame:
        raise provider_error

    provider = YFinanceMarketDataProvider(history_loader=loader)

    with pytest.raises(expected_error):
        await provider.get_price_bars(
            "AAPL",
            date(2026, 1, 1),
            date(2026, 1, 31),
        )
