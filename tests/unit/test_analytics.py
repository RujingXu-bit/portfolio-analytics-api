from datetime import date
from decimal import Decimal
from math import sqrt

import pytest

from portfolio_analytics_api.domain import (
    InvalidPriceSeriesError,
    PriceBar,
    calculate_annualized_volatility,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_simple_returns,
)


def price_bar(day: int, adjusted_close: str) -> PriceBar:
    return PriceBar(
        symbol="TEST",
        date=date(2026, 1, day),
        adjusted_close=Decimal(adjusted_close),
    )


@pytest.mark.parametrize("price_bars", [[], [price_bar(2, "100")]])
def test_insufficient_prices_have_no_returns(
    price_bars: list[PriceBar],
) -> None:
    returns = calculate_simple_returns(price_bars)

    assert returns == ()
    assert calculate_annualized_volatility(returns) is None
    assert calculate_sharpe_ratio(returns, Decimal("0.04")) is None


def test_small_series_matches_hand_checked_metrics() -> None:
    price_bars = [price_bar(2, "100"), price_bar(5, "110"), price_bar(6, "99")]

    returns = calculate_simple_returns(price_bars)

    assert returns == pytest.approx((0.1, -0.1))
    assert calculate_annualized_volatility(returns) == pytest.approx(
        0.2 / sqrt(2) * sqrt(252)
    )
    assert calculate_max_drawdown(price_bars) == pytest.approx(-0.1)
    assert calculate_sharpe_ratio(returns, Decimal("0")) == pytest.approx(0.0)


def test_prices_are_sorted_and_missing_dates_are_not_filled() -> None:
    price_bars = [price_bar(10, "121"), price_bar(2, "100"), price_bar(6, "110")]

    assert calculate_simple_returns(price_bars) == pytest.approx((0.1, 0.1))


def test_constant_prices_have_zero_volatility_and_undefined_sharpe() -> None:
    price_bars = [price_bar(2, "100"), price_bar(3, "100"), price_bar(4, "100")]
    returns = calculate_simple_returns(price_bars)

    assert calculate_annualized_volatility(returns) == 0.0
    assert calculate_max_drawdown(price_bars) == 0.0
    assert calculate_sharpe_ratio(returns, Decimal("0.04")) is None


def test_continuously_falling_prices_draw_down_from_initial_peak() -> None:
    price_bars = [price_bar(2, "100"), price_bar(3, "80"), price_bar(4, "60")]

    assert calculate_max_drawdown(price_bars) == pytest.approx(-0.4)


def test_empty_drawdown_is_undefined_and_single_price_drawdown_is_zero() -> None:
    assert calculate_max_drawdown([]) is None
    assert calculate_max_drawdown([price_bar(2, "100")]) == 0.0


def test_sharpe_uses_configured_periods_and_risk_free_rate() -> None:
    returns = (0.01, 0.03)

    result = calculate_sharpe_ratio(
        returns,
        annual_risk_free_rate=Decimal("0.12"),
        annualization_periods=12,
    )

    assert result == pytest.approx(sqrt(12) / sqrt(2))


@pytest.mark.parametrize("adjusted_close", ["0", "-1", "NaN", "Infinity"])
def test_non_positive_or_non_finite_price_is_rejected(
    adjusted_close: str,
) -> None:
    with pytest.raises(
        InvalidPriceSeriesError, match="adjusted close must be finite and positive"
    ):
        calculate_simple_returns([price_bar(2, adjusted_close)])


def test_duplicate_date_is_rejected() -> None:
    with pytest.raises(InvalidPriceSeriesError, match="duplicate price date"):
        calculate_max_drawdown([price_bar(2, "100"), price_bar(2, "101")])


@pytest.mark.parametrize("annualization_periods", [0, -1])
def test_non_positive_annualization_period_is_rejected(
    annualization_periods: int,
) -> None:
    with pytest.raises(ValueError, match="annualization_periods must be positive"):
        calculate_annualized_volatility((0.01, 0.02), annualization_periods)

    with pytest.raises(ValueError, match="annualization_periods must be positive"):
        calculate_sharpe_ratio((0.01, 0.02), Decimal("0.04"), annualization_periods)


def test_non_finite_risk_free_rate_is_rejected() -> None:
    with pytest.raises(ValueError, match="annual_risk_free_rate must be finite"):
        calculate_sharpe_ratio((0.01, 0.02), Decimal("NaN"))
