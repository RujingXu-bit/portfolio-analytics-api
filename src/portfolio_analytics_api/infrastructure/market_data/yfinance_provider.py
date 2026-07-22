import asyncio
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import pandas as pd
import yfinance as yf  # type: ignore[import-untyped]
from curl_cffi.requests.exceptions import (
    HTTPError,
    RequestException,
    Timeout,
)
from yfinance.exceptions import (  # type: ignore[import-untyped]
    YFDataException,
    YFPricesMissingError,
    YFRateLimitError,
    YFTickerMissingError,
    YFTzMissingError,
)

from portfolio_analytics_api.application import (
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataRateLimitError,
    MarketDataResult,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
)
from portfolio_analytics_api.domain import PriceBar

HistoryLoader = Callable[..., pd.DataFrame]


class YFinanceMarketDataProvider:
    def __init__(
        self,
        request_timeout_seconds: float = 10.0,
        history_loader: HistoryLoader | None = None,
    ) -> None:
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        self._request_timeout_seconds = request_timeout_seconds
        self._history_loader = history_loader or _load_history

    async def get_price_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> MarketDataResult:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise MarketDataNotFoundError(normalized_symbol)
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")

        try:
            history = await asyncio.to_thread(
                self._history_loader,
                normalized_symbol,
                start=start_date,
                end=end_date + timedelta(days=1),
                interval="1d",
                actions=False,
                auto_adjust=False,
                back_adjust=False,
                repair=False,
                keepna=True,
                timeout=self._request_timeout_seconds,
            )
        except (YFPricesMissingError, YFTickerMissingError, YFTzMissingError) as error:
            raise MarketDataNotFoundError(normalized_symbol) from error
        except YFRateLimitError as error:
            raise MarketDataRateLimitError from error
        except Timeout as error:
            raise MarketDataTimeoutError from error
        except HTTPError as error:
            status_code = getattr(error.response, "status_code", None)
            if status_code == 429:
                raise MarketDataRateLimitError from error
            if isinstance(status_code, int) and status_code >= 500:
                raise MarketDataUnavailableError from error
            if status_code == 404:
                raise MarketDataNotFoundError(normalized_symbol) from error
            raise MarketDataInvalidResponseError(
                "provider rejected the history request"
            ) from error
        except RequestException as error:
            raise MarketDataUnavailableError from error
        except YFDataException as error:
            raise MarketDataInvalidResponseError("provider data error") from error

        return MarketDataResult(
            _normalize_history(
                normalized_symbol,
                start_date,
                end_date,
                history,
            )
        )


def _load_history(symbol: str, **kwargs: Any) -> pd.DataFrame:
    return cast(pd.DataFrame, yf.Ticker(symbol).history(**kwargs))


def _normalize_history(
    symbol: str,
    start_date: date,
    end_date: date,
    history: pd.DataFrame,
) -> tuple[PriceBar, ...]:
    if not isinstance(history, pd.DataFrame):
        raise MarketDataInvalidResponseError("expected a Pandas DataFrame")
    if history.empty:
        raise MarketDataNotFoundError(symbol)
    if "Adj Close" not in history.columns:
        raise MarketDataInvalidResponseError("adjusted close column is missing")
    if not isinstance(history.index, pd.DatetimeIndex):
        raise MarketDataInvalidResponseError("price index is not datetime based")
    if history.index.tz is None:
        raise MarketDataInvalidResponseError("exchange timezone is missing")

    bars: list[PriceBar] = []
    seen_dates: set[date] = set()
    adjusted_close = history["Adj Close"]
    for raw_timestamp, raw_price in zip(
        history.index,
        adjusted_close,
        strict=True,
    ):
        if not isinstance(raw_timestamp, pd.Timestamp):
            raise MarketDataInvalidResponseError("price index contains invalid values")
        timestamp = raw_timestamp
        session_date = timestamp.date()
        if not start_date <= session_date <= end_date:
            continue
        if session_date in seen_dates:
            raise MarketDataInvalidResponseError(
                f"duplicate session date {session_date.isoformat()}"
            )
        if pd.isna(raw_price) or str(raw_price).strip().lower() in {
            "nan",
            "nat",
            "none",
        }:
            raise MarketDataInvalidResponseError(
                f"adjusted close is missing for {session_date.isoformat()}"
            )
        try:
            price = Decimal(str(raw_price))
        except (InvalidOperation, ValueError) as error:
            raise MarketDataInvalidResponseError(
                f"adjusted close is invalid for {session_date.isoformat()}"
            ) from error
        if not price.is_finite() or price <= 0:
            raise MarketDataInvalidResponseError(
                f"adjusted close must be positive for {session_date.isoformat()}"
            )
        seen_dates.add(session_date)
        bars.append(
            PriceBar(
                symbol=symbol,
                date=session_date,
                adjusted_close=price,
            )
        )

    if not bars:
        raise MarketDataNotFoundError(symbol)
    return tuple(sorted(bars, key=lambda bar: bar.date))
