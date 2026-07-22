from typing import Literal

from portfolio_analytics_api.application import MarketDataProvider
from portfolio_analytics_api.infrastructure.market_data.twelve_data_provider import (
    TwelveDataMarketDataProvider,
)
from portfolio_analytics_api.infrastructure.market_data.yfinance_provider import (
    YFinanceMarketDataProvider,
)

MarketDataProviderName = Literal["yfinance", "twelve_data"]


def create_market_data_adapter(
    *,
    provider_name: MarketDataProviderName,
    request_timeout_seconds: float,
    twelve_data_api_key: str | None,
) -> tuple[str, MarketDataProvider]:
    if provider_name == "yfinance":
        return (
            provider_name,
            YFinanceMarketDataProvider(
                request_timeout_seconds=request_timeout_seconds,
            ),
        )
    if not twelve_data_api_key or not twelve_data_api_key.strip():
        raise RuntimeError(
            "TWELVE_DATA_API_KEY must be configured when "
            "MARKET_DATA_PROVIDER=twelve_data"
        )
    return (
        provider_name,
        TwelveDataMarketDataProvider(
            api_key=twelve_data_api_key,
            request_timeout_seconds=request_timeout_seconds,
        ),
    )
