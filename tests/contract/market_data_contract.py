from datetime import date

from portfolio_analytics_api.domain import PriceBar


def assert_price_bar_contract(
    bars: tuple[PriceBar, ...],
    *,
    symbol: str,
    start_date: date,
    end_date: date,
) -> None:
    assert bars
    assert all(isinstance(bar, PriceBar) for bar in bars)
    assert all(bar.symbol == symbol for bar in bars)
    assert all(start_date <= bar.date <= end_date for bar in bars)
    assert all(bar.adjusted_close.is_finite() for bar in bars)
    assert all(bar.adjusted_close > 0 for bar in bars)
    dates = [bar.date for bar in bars]
    assert dates == sorted(dates)
    assert len(dates) == len(set(dates))
