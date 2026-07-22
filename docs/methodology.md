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

The analytics API reports historical measurements. It does not predict prices,
guarantee returns, or provide automatic buy or sell advice.
