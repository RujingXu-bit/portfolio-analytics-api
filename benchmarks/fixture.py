from datetime import date, timedelta
from decimal import Decimal

from portfolio_analytics_api.domain import PriceBar

BENCHMARK_SYMBOL = "BENCH"
PRICE_BAR_COUNT = 2_000
MIN_WINDOW_DAYS = 60
MAX_WINDOW_DAYS = 252


def build_price_bars() -> tuple[PriceBar, ...]:
    bars: list[PriceBar] = []
    current_date = date(2018, 1, 1)
    while len(bars) < PRICE_BAR_COUNT:
        if current_date.weekday() < 5:
            index = len(bars)
            trend = Decimal(index) * Decimal("0.025")
            cycle = Decimal((index % 17) - 8) * Decimal("0.075")
            bars.append(
                PriceBar(
                    symbol=BENCHMARK_SYMBOL,
                    date=current_date,
                    adjusted_close=Decimal("100") + trend + cycle,
                )
            )
        current_date += timedelta(days=1)
    return tuple(bars)


PRICE_BARS = build_price_bars()
TRADING_DATES = tuple(bar.date for bar in PRICE_BARS)
_WINDOW_LENGTH_COUNT = MAX_WINDOW_DAYS - MIN_WINDOW_DAYS + 1
_START_COUNT = PRICE_BAR_COUNT - MAX_WINDOW_DAYS + 1
COLD_WINDOW_CAPACITY = _START_COUNT * _WINDOW_LENGTH_COUNT


def cold_query_window(ordinal: int) -> tuple[date, date]:
    if ordinal < 0:
        raise ValueError("query ordinal must not be negative")
    normalized = ordinal % COLD_WINDOW_CAPACITY
    start_index = normalized // _WINDOW_LENGTH_COUNT
    window_length = MIN_WINDOW_DAYS + normalized % _WINDOW_LENGTH_COUNT
    end_index = start_index + window_length - 1
    return TRADING_DATES[start_index], TRADING_DATES[end_index]


def hot_query_window() -> tuple[date, date]:
    return TRADING_DATES[-MAX_WINDOW_DAYS], TRADING_DATES[-1]
