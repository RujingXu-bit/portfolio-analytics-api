# AI-Powered Portfolio Analytics API

A FastAPI backend for deterministic and explainable portfolio analytics.

The current vertical slice persists portfolios and idempotent transaction
ledgers in PostgreSQL, validates holdings rules, and returns deterministic
multi-asset portfolio analytics using adjusted-close history from yfinance.
Unit and integration tests continue to use fixed fake market data and do not
require network access.

## Financial methodology

The domain types, deterministic metric calculations, and V1 financial
conventions are documented in [`docs/methodology.md`](docs/methodology.md).

## Requirements

- uv
- Git
- Docker Desktop or another Docker Compose-compatible runtime
- Python 3.12, installed automatically by uv when required

## Install

From the project root:

```bash
make install

```

This installs the locked application and development dependencies from
`uv.lock`.

## Run the application

```bash
cp .env.example .env
make infra-up
make db-upgrade
make dev
```

The API is available at <http://127.0.0.1:8000>.

Check application health in a second terminal:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Interactive API documentation is available at
<http://127.0.0.1:8000/docs>.

## Local infrastructure

Docker Compose provides PostgreSQL 16 and Redis 7 for local development. The
checked-in example values are local-only placeholders, not production
credentials:

```bash
cp .env.example .env
make infra-up
make infra-check
```

`make infra-down` stops the services without deleting the PostgreSQL data
volume. Use `make infra-logs` to follow service logs. Isolated PostgreSQL and
Redis instances for integration tests are available through
`make infra-test-up`; `make infra-test-down` removes only those test containers.

Market-data cache keys include the schema version, provider, interval, price
basis, symbol, and inclusive date range. A range ending today or later uses the
short mutable-data TTL; completed historical ranges use the longer historical
TTL. Transient provider failures are retried at most three times within a
12-second operation deadline. After retries are exhausted, a valid retained
copy may be returned with top-level analytics field `stale: true`; deterministic
symbol/data errors and damaged cache content never use that fallback. Redis
failures safely bypass the cache. Quote caching is not exposed because V1 has
no quote endpoint or provider method.

## Persistent transaction and analytics slice

The running application uses yfinance and accepts symbols supported by Yahoo
Finance. Create a single-currency, potentially multi-asset portfolio:

```bash
curl -X POST http://127.0.0.1:8000/portfolios \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Demo portfolio",
    "base_currency": "USD"
  }'
```

Use the returned `id` to add a transaction. Repeating the same normalized
payload with the same `external_id` returns the existing transaction without
posting it twice:

```bash
curl -X POST http://127.0.0.1:8000/portfolios/<id>/transactions \
  -H 'Content-Type: application/json' \
  -d '{
    "external_id": "demo-buy-001",
    "transaction_type": "BUY",
    "occurred_at": "2026-01-02T09:00:00Z",
    "symbol": "AAPL",
    "quantity": "2",
    "unit_price": "100",
    "fees": "0"
  }'
```

Retrieve the portfolio, ordered transaction ledger, or reproducible analytics:

```bash
curl http://127.0.0.1:8000/portfolios/<id>
curl http://127.0.0.1:8000/portfolios/<id>/transactions
curl 'http://127.0.0.1:8000/portfolios/<id>/analytics?start_date=2026-01-02&end_date=2026-01-06'
```

The response includes cash-flow-adjusted period simple return, annualized
volatility, maximum drawdown, Sharpe ratio, exact latest portfolio value, cash
balance, security weights, `as_of`, methodology, and a `stale` flag describing
market-data freshness. Multiple traded symbols are valued together. Security
weights use total portfolio value, including cash, as the denominator. Data
survives application restarts.

Upstream rate limiting and availability failures return stable 503 errors when
no stale fallback exists; provider timeouts return 504, malformed upstream data
returns 502, and invalid or empty symbols retain the existing 422 mapping.

## Quality commands

```bash
make lint
make typecheck
make test
make test-cov
make test-integration
make test-all
make check
make test-contract
```

`make test` and `make test-cov` run the offline unit suite. Start the isolated
test PostgreSQL service before `make test-integration` or `make test-all`.
`make test-contract` is the only command that enables the optional real
yfinance network contract test; it is not part of normal CI.
Database migrations are explicit: run `make db-upgrade` after starting the
development infrastructure; application startup never applies migrations.

To apply automatic formatting:

```bash
make format
```

## Project structure

```text
src/portfolio_analytics_api/
├── api/
├── application/
├── core/
├── domain/
├── infrastructure/
└── main.py

tests/
├── unit/
├── integration/
└── contract/
```

The project is a modular monolith. Financial calculations remain deterministic
and independent of network, database, and framework code. The current module
boundaries are documented in [`docs/architecture.md`](docs/architecture.md).
