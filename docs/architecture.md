# Architecture

The application is a modular monolith. The Week 1 in-memory vertical slice
keeps framework, use-case, domain, and adapter responsibilities separate so
later tasks can replace infrastructure without changing financial algorithms.

## Current request path

```text
FastAPI route
    -> PortfolioService / PortfolioAnalyticsService
        -> PortfolioRepository protocol -> InMemoryPortfolioRepository
        -> MarketDataProvider protocol  -> FakeMarketDataProvider
        -> deterministic domain analytics functions
```

The API layer validates and serializes HTTP data. It does not calculate
financial metrics or access repository storage directly.

The application layer owns use-case orchestration. Portfolio creation maps an
application transaction input into domain objects. Analytics loads a portfolio,
identifies the temporary single traded symbol, requests a date-bounded price
series, and composes the four domain metrics into `PortfolioAnalytics`.

The domain layer contains immutable values and deterministic financial
functions. It has no FastAPI, database, Pandas, provider, network, system clock,
or infrastructure dependency.

The infrastructure layer currently supplies only offline adapters. The fake
market data provider returns the project's `PriceBar` type and the in-memory
repository implements the application repository protocol. PostgreSQL and a
real market data provider are deferred to their explicit Week 2 and Week 3
tasks.

The market data provider boundary also owns timestamp normalization. It maps
each observation to the trading-session date in the instrument's listing
exchange timezone before constructing `PriceBar`; application and domain code
never infer a date from a vendor timestamp or the host timezone. The complete
normalization rule is recorded in `docs/methodology.md` and will apply to the
real provider introduced in W3.1.

## Temporary scope

The W1.4 API supports `POST /portfolios` and
`GET /portfolios/{portfolio_id}/analytics` with an inclusive date range. Data
does not survive process restarts. Analytics currently accepts exactly one
symbol represented by a BUY or SELL transaction; multi-asset holdings and
cash-flow-aware valuation are not implemented in this slice.
