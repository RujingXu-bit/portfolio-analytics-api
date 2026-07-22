# AI-Powered Portfolio Analytics API

A FastAPI backend for deterministic and explainable portfolio analytics.

The current vertical slice persists portfolios and idempotent transaction
ledgers in PostgreSQL, validates holdings rules, and returns deterministic
analytics over fixed fake market data. A real market data adapter remains
planned Week 3 work.

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
volume. Use `make infra-logs` to follow service logs. An isolated PostgreSQL
instance for integration tests is available through `make infra-test-up` and
uses temporary storage; `make infra-test-down` removes only that test
container.

## Persistent transaction and analytics slice

The bundled fake provider exposes fixed `DEMO` adjusted-close prices. Create a
single-currency portfolio:

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
    "symbol": "DEMO",
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

The response includes period simple return, annualized volatility, maximum
drawdown, Sharpe ratio, `as_of`, and methodology. Data survives application
restarts. The current analytics path intentionally supports exactly one traded
symbol; multi-asset portfolio valuation is a separate planned task.

## Quality commands

```bash
make lint
make typecheck
make test
make test-cov
make test-integration
make test-all
make check
```

`make test` and `make test-cov` run the offline unit suite. Start the isolated
test PostgreSQL service before `make test-integration` or `make test-all`.
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
