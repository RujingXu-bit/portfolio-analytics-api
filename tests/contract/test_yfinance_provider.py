import os
from datetime import date

import pytest

from portfolio_analytics_api.infrastructure import YFinanceMarketDataProvider
from tests.contract.market_data_contract import assert_price_bar_contract

pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(
        os.getenv("RUN_MARKET_DATA_CONTRACT") != "1",
        reason="set RUN_MARKET_DATA_CONTRACT=1 to access the real provider",
    ),
]


@pytest.mark.anyio
async def test_yfinance_provider_contract() -> None:
    provider = YFinanceMarketDataProvider(request_timeout_seconds=10)
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
