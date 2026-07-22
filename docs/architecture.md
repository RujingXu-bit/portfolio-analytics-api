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
        -> MarketDataProvider protocol
             -> Redis cache decorator
                  -> retry/deadline decorator -> YFinanceMarketDataProvider
        -> deterministic domain analytics functions
```

The API layer validates and serializes HTTP data. It does not calculate
financial metrics or access repository storage directly.

The application layer owns use-case orchestration and transaction boundaries.
Portfolio and transaction writes use a fresh unit of work. Analytics loads the
persistent ordered transaction ledger, identifies symbols held or traded in the
requested interval, requests their date-bounded price series concurrently, and
composes the cash-flow-adjusted valuation and four domain metrics into
`PortfolioAnalytics`.

The domain layer contains immutable values and deterministic financial
functions. It has no FastAPI, database, Pandas, provider, network, system clock,
or infrastructure dependency.

The infrastructure layer supplies PostgreSQL repositories, a real yfinance
adapter, and offline adapters used by unit tests. Both providers return only the
project's `PriceBar` type. The yfinance adapter runs its blocking SDK call in a
worker thread, explicitly requests unadjusted columns so it can select `Adj
Close`, and normalizes the exchange-local session date before returning data.
Pandas and vendor response objects never leave the infrastructure layer.

Week 2 persistence uses SQLAlchemy 2.x with asyncpg. ORM records and Alembic
metadata live only in the infrastructure layer; domain values remain framework
independent. Database sessions are created at a use-case boundary, and schema
migrations are explicit deployment commands rather than application-startup
side effects. Redis is connected through `CachedMarketDataProvider`, which
decorates the real provider without changing application services. Keys are
versioned by provider, interval, price basis, symbol, and date range. Mutable
daily ranges use a short TTL, completed historical ranges use a longer TTL, and
a longer-lived shadow copy supports stale fallback. Cache misses call a bounded
retry decorator, which retries only transient provider failures within one
operation deadline before reaching yfinance. After retries are exhausted, the
cache decorator may return a valid shadow copy marked stale. Corrupt payloads
and Redis failures are logged and safely bypassed. The async Redis client is
closed with the database engine during application shutdown.

PostgreSQL access is organized behind Portfolio and Transaction repository
protocols and a small unit-of-work boundary. Creating a transaction locks its
Portfolio row, checks the portfolio-scoped idempotency key, replays the ordered
ledger, and commits the new row atomically. The domain replay order is
`occurred_at`, ingestion `created_at`, then transaction ID. BUY and SELL affect
security positions; DEPOSIT and WITHDRAWAL are recorded but W2 does not enforce
a cash balance.

The W3.5 valuation engine is a pure domain component. It replays transactions by
UTC occurrence time, tracks cash and security quantities, values active
positions only with prices already observed on or before each valuation date,
and calculates returns after removing external flows. DEPOSIT, WITHDRAWAL, and
unfunded BUY shortfalls are external flows; BUY and SELL otherwise transfer
value between cash and securities. Fees reduce performance. The latest security
weights use total portfolio value, including cash, as their denominator.

## Current scope

The API persists Portfolio and Transaction resources and exposes creation,
lookup, ordered transaction listing, and multi-asset analytics. Data survives
process and engine recreation. The Week 3 market-data path uses yfinance behind
Redis cache, bounded retry/deadline handling, stable upstream errors, and
explicit stale metadata. Authentication and enforced non-null ownership remain
W4 work.
