import os
from datetime import date

import pytest

from portfolio_analytics_api.application import MarketDataInvalidResponseError
from portfolio_analytics_api.infrastructure import TwelveDataMarketDataProvider
from tests.contract.market_data_contract import assert_price_bar_contract

_api_key = os.getenv("TWELVE_DATA_API_KEY", "")

pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(
        os.getenv("RUN_MARKET_DATA_CONTRACT") != "1" or not _api_key,
        reason=(
            "set RUN_MARKET_DATA_CONTRACT=1 and TWELVE_DATA_API_KEY to access "
            "the real provider"
        ),
    ),
]


@pytest.mark.anyio
async def test_twelve_data_provider_contract() -> None:
    provider = TwelveDataMarketDataProvider(
        api_key=_api_key,
        request_timeout_seconds=10,
    )
    start_date = date(2025, 1, 2)
    end_date = date(2025, 1, 10)

    result = await provider.get_price_bars("AAPL", start_date, end_date)

    assert_price_bar_contract(
        result.price_bars,
        symbol="AAPL",
        start_date=start_date,
        end_date=end_date,
    )
    assert result.stale is False


@pytest.mark.anyio
async def test_twelve_data_provider_rejects_truncated_long_window() -> None:
    provider = TwelveDataMarketDataProvider(
        api_key=_api_key,
        request_timeout_seconds=30,
    )

    with pytest.raises(
        MarketDataInvalidResponseError,
        match="truncated at the 5000-point limit",
    ):
        await provider.get_price_bars(
            "AAPL",
            date(2000, 1, 1),
            date(2026, 1, 1),
        )
