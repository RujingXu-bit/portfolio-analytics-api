from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from portfolio_analytics_api.application import (
    MarketDataInvalidResponseError,
    MarketDataNotFoundError,
    MarketDataRateLimitError,
    MarketDataResult,
    MarketDataTimeoutError,
    MarketDataUnavailableError,
)
from portfolio_analytics_api.domain import PriceBar

DEFAULT_BASE_URL = "https://api.twelvedata.com"


class TwelveDataMarketDataProvider:
    """Twelve Data daily total-return-adjusted history adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        request_timeout_seconds: float = 10.0,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_key = api_key.strip()
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_key:
            raise ValueError("Twelve Data API key must not be empty")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if not normalized_base_url:
            raise ValueError("base_url must not be empty")
        self._api_key = normalized_key
        self._request_timeout_seconds = request_timeout_seconds
        self._base_url = normalized_base_url
        self._client = client

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

        params = {
            "symbol": normalized_symbol,
            "interval": "1day",
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "adjust": "all",
            "apikey": self._api_key,
        }
        response = await self._request(params)
        _raise_for_http_status(response.status_code, normalized_symbol)
        try:
            payload = response.json()
        except ValueError as error:
            raise MarketDataInvalidResponseError(
                "provider response is not JSON"
            ) from error

        return MarketDataResult(
            _normalize_payload(
                normalized_symbol,
                start_date,
                end_date,
                payload,
            )
        )

    async def _request(self, params: Mapping[str, str]) -> httpx.Response:
        try:
            if self._client is not None:
                return await self._client.get("/time_series", params=params)
            timeout = httpx.Timeout(self._request_timeout_seconds)
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout,
            ) as client:
                return await client.get("/time_series", params=params)
        except httpx.TimeoutException as error:
            raise MarketDataTimeoutError from error
        except httpx.RequestError as error:
            raise MarketDataUnavailableError from error


def _raise_for_http_status(status_code: int, symbol: str) -> None:
    if status_code == 429:
        raise MarketDataRateLimitError
    if status_code == 404:
        raise MarketDataNotFoundError(symbol)
    if status_code >= 500:
        raise MarketDataUnavailableError
    if status_code >= 400:
        raise MarketDataInvalidResponseError("provider rejected the history request")


def _normalize_payload(
    symbol: str,
    start_date: date,
    end_date: date,
    payload: Any,
) -> tuple[PriceBar, ...]:
    if not isinstance(payload, dict):
        raise MarketDataInvalidResponseError("expected a JSON object")
    if payload.get("status") == "error":
        _raise_for_provider_error(payload, symbol)
    if payload.get("status") != "ok":
        raise MarketDataInvalidResponseError("provider status is missing or invalid")

    meta = payload.get("meta")
    if not isinstance(meta, dict) or not _nonempty_string(
        meta.get("exchange_timezone")
    ):
        raise MarketDataInvalidResponseError("exchange timezone is missing")
    values = payload.get("values")
    if not isinstance(values, list):
        raise MarketDataInvalidResponseError("price values are missing")

    bars: list[PriceBar] = []
    seen_dates: set[date] = set()
    for row in values:
        if not isinstance(row, dict):
            raise MarketDataInvalidResponseError("price row is not an object")
        session_date = _parse_session_date(row.get("datetime"))
        if not start_date <= session_date <= end_date:
            continue
        if session_date in seen_dates:
            raise MarketDataInvalidResponseError(
                f"duplicate session date {session_date.isoformat()}"
            )
        price = _parse_adjusted_close(row.get("close"), session_date)
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


def _raise_for_provider_error(payload: dict[str, Any], symbol: str) -> None:
    code = payload.get("code")
    if code == 429:
        raise MarketDataRateLimitError
    if code in {400, 404}:
        raise MarketDataNotFoundError(symbol)
    if isinstance(code, int) and code >= 500:
        raise MarketDataUnavailableError
    raise MarketDataInvalidResponseError("provider rejected the history request")


def _parse_session_date(raw_value: Any) -> date:
    if not isinstance(raw_value, str):
        raise MarketDataInvalidResponseError("session date is missing")
    try:
        return date.fromisoformat(raw_value)
    except ValueError as error:
        raise MarketDataInvalidResponseError("session date is invalid") from error


def _parse_adjusted_close(raw_value: Any, session_date: date) -> Decimal:
    if not isinstance(raw_value, str):
        raise MarketDataInvalidResponseError(
            f"adjusted close is missing for {session_date.isoformat()}"
        )
    try:
        price = Decimal(raw_value)
    except InvalidOperation as error:
        raise MarketDataInvalidResponseError(
            f"adjusted close is invalid for {session_date.isoformat()}"
        ) from error
    if not price.is_finite() or price <= 0:
        raise MarketDataInvalidResponseError(
            f"adjusted close must be positive for {session_date.isoformat()}"
        )
    return price


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
