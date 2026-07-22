# Architecture

The application is a modular monolith. Framework, use-case, domain, and adapter
responsibilities remain separate so infrastructure can change without changing
financial algorithms.

## Current request path

```text
FastAPI route
    -> PortfolioService / TransactionService / PortfolioAnalyticsService
        -> UnitOfWork -> PortfolioRepository / TransactionRepository
                         -> PostgreSQL (SQLAlchemy + asyncpg)
        -> MarketDataProvider protocol  -> FakeMarketDataProvider
        -> deterministic domain analytics functions
```

The API layer validates and serializes HTTP data. It does not calculate
financial metrics or access repository storage directly.

The application layer owns use-case orchestration and transaction boundaries.
Portfolio and transaction writes use a fresh unit of work. Analytics loads the
persistent ordered transaction ledger, identifies the current single traded
symbol, requests a date-bounded price series, and composes the four domain
metrics into `PortfolioAnalytics`.

The domain layer contains immutable values and deterministic financial
functions. It has no FastAPI, database, Pandas, provider, network, system clock,
or infrastructure dependency.

The infrastructure layer supplies PostgreSQL repositories and offline adapters
used by unit tests. The fake market data provider returns the project's
`PriceBar` type. A real market data provider remains W3.1 work.

Week 2 persistence uses SQLAlchemy 2.x with asyncpg. ORM records and Alembic
metadata live only in the infrastructure layer; domain values remain framework
independent. Database sessions are created at a use-case boundary, and schema
migrations are explicit deployment commands rather than application-startup
side effects. Redis is available in local infrastructure but is not connected
to application code until W3.2.

PostgreSQL access is organized behind Portfolio and Transaction repository
protocols and a small unit-of-work boundary. Creating a transaction locks its
Portfolio row, checks the portfolio-scoped idempotency key, replays the ordered
ledger, and commits the new row atomically. The domain replay order is
`occurred_at`, ingestion `created_at`, then transaction ID. BUY and SELL affect
security positions; DEPOSIT and WITHDRAWAL are recorded but W2 does not enforce
a cash balance.

## Current scope

The W2.4 API persists Portfolio and Transaction resources and exposes creation,
lookup, ordered transaction listing, and analytics. Data survives process and
engine recreation. Analytics accepts exactly one symbol represented by BUY or
SELL transactions; multi-asset and cash-flow-aware valuation are not part of
this slice. Authentication and enforced non-null ownership remain W4 work.
