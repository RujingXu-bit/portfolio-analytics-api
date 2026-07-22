# AI-Powered Portfolio Analytics API

A FastAPI backend for deterministic and explainable portfolio analytics.

The current engineering skeleton provides a health endpoint and the quality
tooling required for later portfolio and financial analytics work.

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

## Quality commands

```bash
make lint
make typecheck
make test
make check
```

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

The project is a modular monolith. Financial calculations will remain
deterministic and independent of network, database, and framework code.
