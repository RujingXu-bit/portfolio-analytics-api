from collections.abc import Sequence
from decimal import Decimal
from math import sqrt
from statistics import mean, stdev

from portfolio_analytics_api.domain.models import PriceBar


class InvalidPriceSeriesError(ValueError):
    """Raised when a price series cannot be used for deterministic analytics."""


def calculate_simple_returns(price_bars: Sequence[PriceBar]) -> tuple[float, ...]:
    """Return simple period returns ordered by observation date."""
    ordered_bars = _validate_and_order(price_bars)
    return tuple(
        float(current.adjusted_close / previous.adjusted_close - Decimal(1))
        for previous, current in zip(ordered_bars, ordered_bars[1:], strict=False)
    )


def calculate_annualized_volatility(
    returns: Sequence[float], annualization_periods: int = 252
) -> float | None:
    """Annualize sample standard deviation; two returns are required."""
    _validate_annualization_periods(annualization_periods)
    if len(returns) < 2:
        return None
    return stdev(returns) * sqrt(annualization_periods)


def calculate_max_drawdown(price_bars: Sequence[PriceBar]) -> float | None:
    """Return the worst peak-to-trough decline, as a non-positive fraction."""
    ordered_bars = _validate_and_order(price_bars)
    if not ordered_bars:
        return None

    peak = ordered_bars[0].adjusted_close
    max_drawdown = Decimal(0)
    for price_bar in ordered_bars[1:]:
        peak = max(peak, price_bar.adjusted_close)
        drawdown = price_bar.adjusted_close / peak - Decimal(1)
        max_drawdown = min(max_drawdown, drawdown)
    return float(max_drawdown)


def calculate_sharpe_ratio(
    returns: Sequence[float],
    annual_risk_free_rate: Decimal,
    annualization_periods: int = 252,
) -> float | None:
    """Return the annualized Sharpe ratio from simple period returns."""
    _validate_annualization_periods(annualization_periods)
    if not annual_risk_free_rate.is_finite():
        raise ValueError("annual_risk_free_rate must be finite")
    if len(returns) < 2:
        return None

    sample_volatility = stdev(returns)
    if sample_volatility == 0:
        return None

    period_risk_free_rate = float(
        annual_risk_free_rate / Decimal(annualization_periods)
    )
    return (
        (mean(returns) - period_risk_free_rate)
        / sample_volatility
        * sqrt(annualization_periods)
    )


def calculate_compounded_return(returns: Sequence[float]) -> float | None:
    """Compound cash-flow-adjusted period returns into one range return."""
    if not returns:
        return None
    wealth = 1.0
    for period_return in returns:
        wealth *= 1.0 + period_return
    return wealth - 1.0


def calculate_max_drawdown_from_returns(returns: Sequence[float]) -> float:
    """Calculate drawdown from a cash-flow-neutral cumulative wealth index."""
    wealth = 1.0
    peak = wealth
    max_drawdown = 0.0
    for period_return in returns:
        wealth *= 1.0 + period_return
        peak = max(peak, wealth)
        max_drawdown = min(max_drawdown, wealth / peak - 1.0)
    return max_drawdown


def _validate_and_order(price_bars: Sequence[PriceBar]) -> tuple[PriceBar, ...]:
    ordered_bars = tuple(sorted(price_bars, key=lambda price_bar: price_bar.date))
    seen_dates = set()
    for price_bar in ordered_bars:
        if price_bar.date in seen_dates:
            raise InvalidPriceSeriesError(
                f"duplicate price date: {price_bar.date.isoformat()}"
            )
        seen_dates.add(price_bar.date)
        if not price_bar.adjusted_close.is_finite() or price_bar.adjusted_close <= 0:
            raise InvalidPriceSeriesError(
                f"adjusted close must be finite and positive on "
                f"{price_bar.date.isoformat()}"
            )
    return ordered_bars


def _validate_annualization_periods(annualization_periods: int) -> None:
    if annualization_periods <= 0:
        raise ValueError("annualization_periods must be positive")
