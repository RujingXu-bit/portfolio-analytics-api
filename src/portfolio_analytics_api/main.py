from datetime import date
from decimal import Decimal

from portfolio_analytics_api.api import create_app
from portfolio_analytics_api.domain import AnalyticsMethodology, PriceBar
from portfolio_analytics_api.infrastructure import (
    FakeMarketDataProvider,
    InMemoryPortfolioRepository,
)

_DEMO_PRICE_BARS = (
    PriceBar(symbol="DEMO", date=date(2026, 1, 2), adjusted_close=Decimal("100")),
    PriceBar(symbol="DEMO", date=date(2026, 1, 5), adjusted_close=Decimal("110")),
    PriceBar(symbol="DEMO", date=date(2026, 1, 6), adjusted_close=Decimal("99")),
)

app = create_app(
    portfolio_repository=InMemoryPortfolioRepository(),
    market_data_provider=FakeMarketDataProvider({"DEMO": _DEMO_PRICE_BARS}),
    methodology=AnalyticsMethodology(
        annual_risk_free_rate=Decimal("0.04"),
        risk_free_rate_as_of=date(2026, 1, 1),
        risk_free_rate_assumption=(
            "Illustrative W1.4 fixture rate held constant over the analysis period."
        ),
    ),
)
