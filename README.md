# AI-Powered Portfolio Analytics API

A FastAPI backend for deterministic and explainable portfolio analytics.

The current in-memory vertical slice provides portfolio creation and
deterministic analytics over fixed fake market data, alongside the health
endpoint and project quality tooling. It is intentionally offline and will be
replaced by persistent repositories and a real market data adapter in later
planned tasks.

## Financial methodology

The domain types, deterministic metric calculations, and V1 financial
conventions are documented in [`docs/methodology.md`](docs/methodology.md).

## Requirements

- uv
- Git
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

## In-memory analytics slice

The bundled fake provider exposes fixed `DEMO` adjusted-close prices. Create a
temporary single-symbol portfolio:

```bash
curl -X POST http://127.0.0.1:8000/portfolios \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Demo portfolio",
    "transactions": [{
      "external_id": "demo-buy-001",
      "transaction_type": "BUY",
      "occurred_at": "2026-01-02T09:00:00Z",
      "symbol": "DEMO",
      "quantity": "2",
      "unit_price": "100",
      "fees": "0"
    }]
  }'
```

Use the returned `id` to request reproducible analytics:

```bash
curl 'http://127.0.0.1:8000/portfolios/<id>/analytics?start_date=2026-01-02&end_date=2026-01-06'
```

The response includes period simple return, annualized volatility, maximum
drawdown, Sharpe ratio, `as_of`, and methodology. This Week 1 slice supports
exactly one traded symbol; persistent transaction rules and multi-asset
portfolio valuation belong to later tasks in `PROJECT_PLAN.md`.

## Quality commands

```bash
make lint
make typecheck
make test
make test-cov
make check
```

`make test-cov` runs the complete test suite with branch coverage and an
uncovered-line report. It is also the explicit coverage command used by the
Week 1 milestone review.

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
