import pytest

from portfolio_analytics_api.infrastructure import (
    TwelveDataMarketDataProvider,
    YFinanceMarketDataProvider,
    create_market_data_adapter,
)


def test_factory_keeps_yfinance_as_credential_free_default() -> None:
    name, provider = create_market_data_adapter(
        provider_name="yfinance",
        request_timeout_seconds=3,
        twelve_data_api_key=None,
    )

    assert name == "yfinance"
    assert isinstance(provider, YFinanceMarketDataProvider)


def test_factory_builds_twelve_data_only_with_key() -> None:
    name, provider = create_market_data_adapter(
        provider_name="twelve_data",
        request_timeout_seconds=3,
        twelve_data_api_key=" secret ",
    )

    assert name == "twelve_data"
    assert isinstance(provider, TwelveDataMarketDataProvider)


def test_factory_fails_fast_when_twelve_data_key_is_missing() -> None:
    with pytest.raises(RuntimeError, match="TWELVE_DATA_API_KEY"):
        create_market_data_adapter(
            provider_name="twelve_data",
            request_timeout_seconds=3,
            twelve_data_api_key=None,
        )
