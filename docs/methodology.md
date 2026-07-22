# Financial Methodology

This document defines the deterministic financial conventions used by the
portfolio analytics API. Calculated results must include an `as_of` date and
the methodology values needed to explain and reproduce the result.

## Price basis

Historical returns use adjusted close prices. Adjusted close is selected
because it accounts for corporate actions such as stock splits and dividends.

Market data providers must convert their responses into the domain `PriceBar`
type. Provider response objects and Pandas DataFrames must not enter the domain
or application layers.

`PriceBar.date` is the trading-session date in the instrument's listing
exchange timezone, not the calendar date obtained by truncating a UTC
timestamp. A provider must preserve an explicit session date when its source
supplies one. When the source supplies a timestamp instead, the provider must
first convert that timestamp to the listing exchange timezone and only then
extract the date. The adapter must reject a timestamp whose exchange timezone
cannot be determined rather than silently applying the host timezone or UTC.
Provider-specific timestamp and timezone handling belongs at this adapter
boundary; domain analytics operate only on the normalized date.

The yfinance adapter requests daily data with `auto_adjust=False` and reads the
explicit `Adj Close` column. Its end parameter is exclusive, so the adapter adds
one day to the API's inclusive requested end date. Rows with missing or
non-positive adjusted close, a missing exchange timezone, or duplicate session
dates are rejected instead of silently repaired or deduplicated. Non-trading
days simply have no observation.

The optional Twelve Data adapter requests `time_series` with `interval=1day`,
the inclusive requested date bounds, and `adjust=all`. Under that provider's
contract, `all` applies both split and dividend adjustments, so the normalized
`close` remains the same total-return price basis used by yfinance `Adj Close`.
Daily datetimes are explicit exchange-local session dates; the adapter requires
the response's `exchange_timezone` metadata and never derives a date from the
host timezone. Missing, duplicate, non-positive, non-finite, or malformed rows
are rejected under the same domain-facing error boundary.

Prices remain `Decimal` values in domain objects. Statistical calculations may
explicitly convert copies of those values to floating-point numbers, but must
not overwrite the original prices.

## Return convention

The V1 return convention is the simple daily return:

```text
daily return = (current adjusted close / previous adjusted close) - 1
```

Price observations are ordered by date before returns are calculated.
Non-trading-day gaps are allowed and are not forward-filled. Duplicate dates
and non-positive or non-finite prices are invalid inputs.

Fewer than two prices produce no daily returns. This is represented by an
empty return sequence rather than an invented zero return.

## Multi-asset portfolio valuation

Portfolio analytics replay the ordered transaction ledger through each market
observation date in the requested inclusive range. A transaction takes effect
on the UTC calendar date derived from its aware `occurred_at` timestamp. Only
transactions on or before a valuation date are included, so a future trade can
never alter an earlier value.

End-of-day portfolio value is:

```text
portfolio value = cash balance + sum(position quantity × latest known price)
```

Cash is an explicit portfolio asset. DEPOSIT increases cash and WITHDRAWAL
decreases it; their stated cash amounts are external flows. BUY exchanges cash
for a position and SELL exchanges a position for cash. Every transaction fee
reduces cash and therefore portfolio value on its UTC date.

W2 deliberately allowed imported BUY records without matching DEPOSIT records.
To keep those ledgers analyzable, a BUY whose cost exceeds available cash
creates an implicit external contribution for exactly the shortfall. This keeps
cash at zero rather than inventing a negative margin balance. A WITHDRAWAL still
requires available cash and fails valuation otherwise. The implicit contribution
is included in cash-flow adjustment and is not treated as investment return.

For consecutive valuatable dates, the simple portfolio return is:

```text
period return = (current value - net external flow) / previous value - 1
```

`net external flow` includes DEPOSIT, negative WITHDRAWAL, and any implicit BUY
funding since the previous emitted valuation. Trades funded by existing cash are
internal transfers. Fees remain in performance because they reduce current
value but are not removed from the numerator as external flows.

The range `simple_return` compounds these cash-flow-adjusted period returns.
Volatility and Sharpe Ratio use the same period-return series. Maximum drawdown
is calculated from its cumulative wealth index, not raw portfolio value, so a
deposit cannot create an artificial gain or reset a drawdown.

## Multi-asset date alignment and weights

Each required symbol is requested independently through the same
`MarketDataProvider`. Valuation dates are the sorted union of provider market
dates. A price may be carried forward only after it has been observed; the
system never backfills from a future observation. Dates before every active
position has an observed price are omitted. A required symbol with no usable
price in the entire requested range produces a stable analytics error.

The API returns each latest non-zero security position as an `asset_weight`
with its exact Decimal market value and weight relative to total portfolio
value, including cash in the denominator. Consequently, security weights may
sum to less than one when the portfolio holds cash. These weights are the
concentration input for W4.3.

## Annualization

The default annualization period is 252 trading days. The value is exposed as
`annualization_periods` rather than being hidden inside metric functions.

Annualized volatility uses the square root of the configured annualization
period and the sample standard deviation of daily returns. At least two daily
returns (three prices) are required; otherwise volatility is undefined. A
constant price series has zero volatility.

## Maximum drawdown

Maximum drawdown is the worst observed decline from a prior running peak:

```text
drawdown = (current adjusted close / running peak adjusted close) - 1
```

The result is zero for a non-declining or single-price series, negative for a
decline, and undefined for an empty series.

## Risk-free rate

The risk-free rate is an annual decimal rate supplied at the application
configuration boundary. Domain metric functions must not contain a hard-coded
risk-free rate.

For daily excess returns, V1 converts the annual rate using:

```text
daily risk-free rate = annual risk-free rate / annualization periods
```

The configured rate is assumed to remain constant over the analysis period.
Every methodology output records:

- `annual_risk_free_rate`: the configured annual decimal rate;
- `risk_free_rate_as_of`: the date associated with that rate;
- `risk_free_rate_assumption`: the assumption applied during the analysis.

Unit tests use an illustrative annual rate of `0.04`, dated `2026-01-01`. This
is deterministic fixture data and is not presented as an observed market rate.

The V1 Sharpe ratio is annualized from the mean daily excess return divided by
the sample standard deviation of daily returns. It is undefined with fewer
than two daily returns or when volatility is zero.

## Analytics output

`PortfolioAnalytics` contains the four V1 metric fields:

- simple return;
- annualized volatility;
- maximum drawdown;
- Sharpe ratio.

The result also contains `as_of` and `AnalyticsMethodology`. An undefined
metric is represented by `None`; return sequences used internally are empty
when fewer than two prices are available.

The result contains a top-level `stale` boolean. It is false for direct provider
responses and unexpired cache hits. It is true only when a transient upstream
failure exhausts its bounded retries and analytics use a validated retained
cache copy. Invalid symbols, deterministic data errors, and corrupt cache
payloads never produce stale results.

For the current analytics API, `as_of` is the last emitted portfolio valuation
date, which may be earlier than the requested end date. The response includes
the latest exact portfolio value, cash balance, asset weights, four metrics,
methodology, and aggregate market-data `stale` status. Undefined statistics are
still represented by `None`.

The analytics API reports historical measurements. It does not predict prices,
guarantee returns, or provide automatic buy or sell advice.

## Deterministic risk summary

`POST /portfolios/{id}/insights` first computes the same owned portfolio
analytics and then applies versioned `risk-rules-v1` rules. The classification
and factors have no LLM, network, database-clock, or random dependency beyond
those already needed to obtain the analytics input. Factors always appear in
this order: annualized volatility, maximum drawdown, Sharpe ratio, and latest
single-security concentration.

The adverse-signal score is transparent:

- volatility from 15% to below 30% adds 1; 30% or more adds 2;
- drawdown from -10% through above -25% adds 1; -25% or worse adds 2;
- a negative Sharpe ratio adds 1;
- largest security weight from 25% to below 50% adds 1; 50% or more adds 2.

A score below 2 is `low`, 2–3 is `moderate`, and 4 or more is `high`. Positive
Sharpe ratios do not subtract adverse points. If volatility, drawdown, and
Sharpe are all undefined, the result is `insufficient_data` even when a latest
weight exists.

Every result states that historical adjusted-close metrics are not forecasts,
records the annualization and dated risk-free-rate assumption, and explains
that latest weight concentration does not capture sectors, correlations,
liquidity, or related issuers. Missing metrics and stale market data add
explicit limitations. The fixed disclaimer is: “For informational purposes
only; not investment advice.” The rules do not generate transaction
recommendations or guaranteed-return claims.

When configured, the W4.4 DeepSeek adapter receives only a serialized structure
containing those four metrics, simple return, latest symbol weights, `as_of`,
stale status, and the complete methodology. It does not receive users,
credentials, portfolio names, transactions, cash balances, or raw price data.
The model may replace the short narrative and add up to three limitations, but
cannot alter the deterministic risk level, factors, methodology limitations, or
fixed disclaimer. JSON output is validated for its exact schema, lengths, and
transaction/reward-guarantee language. Any timeout, provider error, invalid
JSON, extra field, empty output, or unsafe wording returns the deterministic
result instead.
