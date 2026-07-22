from datetime import date
from decimal import Decimal

import pytest

from portfolio_analytics_api.domain import AnalyticsMethodology


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def analytics_methodology() -> AnalyticsMethodology:
    """Provide deterministic, illustrative assumptions for unit tests."""
    return AnalyticsMethodology(
        annual_risk_free_rate=Decimal("0.04"),
        risk_free_rate_as_of=date(2026, 1, 1),
        risk_free_rate_assumption=(
            "Illustrative annual rate held constant over the analysis period."
        ),
    )
