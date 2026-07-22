# AI-Powered Portfolio Analytics API

A FastAPI backend for deterministic and explainable portfolio analytics.

The current vertical slice persists portfolios and idempotent transaction
ledgers in PostgreSQL, validates holdings rules, and returns deterministic
multi-asset portfolio analytics using adjusted-close history from yfinance.
It can optionally enrich the deterministic risk summary through DeepSeek while
preserving a rule-based fallback. Unit and integration tests use fixed fake
market data and a Fake Insight Generator and do not require network access.

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
# Replace JWT_SECRET_KEY with at least 32 random characters before starting.
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

## Authentication

Register an account and exchange its credentials for a 30-minute JWT access
token. Email addresses are stored in normalized lowercase form, passwords are
stored only as Argon2 hashes, and authentication failures use one stable 401
response without distinguishing an unknown email from a wrong password.

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"investor@example.com","password":"replace-with-a-long-password"}'

curl -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"investor@example.com","password":"replace-with-a-long-password"}'
```

Use the returned `access_token` as `<token>` below. `JWT_SECRET_KEY` is required
at application startup and is read only from the
environment (or a local ignored `.env` file). The repository contains no usable
token-signing key. Every portfolio route requires the Bearer token, and the
application service returns 404 when a user guesses another user's portfolio
ID.

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
  -H 'Authorization: Bearer <token>' \
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
  -H 'Authorization: Bearer <token>' \
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
curl -H 'Authorization: Bearer <token>' http://127.0.0.1:8000/portfolios/<id>
curl -H 'Authorization: Bearer <token>' http://127.0.0.1:8000/portfolios/<id>/transactions
curl -H 'Authorization: Bearer <token>' \
  'http://127.0.0.1:8000/portfolios/<id>/analytics?start_date=2026-01-02&end_date=2026-01-06'
```

The response includes cash-flow-adjusted period simple return, annualized
volatility, maximum drawdown, Sharpe ratio, exact latest portfolio value, cash
balance, security weights, `as_of`, methodology, and a `stale` flag describing
market-data freshness. Multiple traded symbols are valued together. Security
weights use total portfolio value, including cash, as the denominator. Data
survives application restarts.

Generate the deterministic historical risk summary for the same date range:

```bash
curl -X POST -H 'Authorization: Bearer <token>' \
  'http://127.0.0.1:8000/portfolios/<id>/insights?start_date=2026-01-02&end_date=2026-01-06'
```

The versioned rules describe volatility, drawdown, historical Sharpe ratio,
latest single-security concentration, missing-data limitations, and stale data.
They always determine the risk level and factors. With no `DEEPSEEK_API_KEY`,
or if DeepSeek times out, errors, or fails strict response validation, the API
returns those rules unchanged. With a key, DeepSeek `deepseek-v4-flash` may
enrich only the narrative from the structured metrics and methodology. Add the
key only to the ignored local `.env`; never commit it:

```dotenv
DEEPSEEK_API_KEY=<your-local-key>
```

Successful generated narratives are cached in Redis for 86,400 seconds by
default. Every insight result is saved as an `AnalysisSnapshot` containing the
actual generator/model, prompt or rule version, generation time, input metrics
summary, and methodology. All paths retain the fixed informational-use and
non-investment-advice disclaimer.

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
