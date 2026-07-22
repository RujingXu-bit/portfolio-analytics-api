# AI-Powered Portfolio Analytics API

[![CI](https://github.com/RujingXu-bit/portfolio-analytics-api/actions/workflows/ci.yml/badge.svg)](https://github.com/RujingXu-bit/portfolio-analytics-api/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/RujingXu-bit/portfolio-analytics-api)](https://github.com/RujingXu-bit/portfolio-analytics-api/releases/tag/v1.1.0)
[![Live Demo](https://img.shields.io/badge/Live_Demo-Vercel-000000?logo=vercel)](https://portfolio-analytics-web-hazel.vercel.app)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js-111827?logo=nextdotjs)](https://github.com/RujingXu-bit/portfolio-analytics-web)

[Live Demo](https://portfolio-analytics-web-hazel.vercel.app) ·
[Offline Fixture](https://portfolio-analytics-web-hazel.vercel.app/demo) ·
[Three-Minute Video](https://github.com/RujingXu-bit/portfolio-analytics-api/releases/download/v1.1.0/portfolio-analytics-demo.mp4) ·
[Video Script](docs/demo-video-script.md) ·
[English Captions](docs/demo-video-captions.srt) ·
[Verification](docs/demo-video-verification.md) ·
[Backend Release](https://github.com/RujingXu-bit/portfolio-analytics-api/releases/tag/v1.1.0) ·
[Frontend Repository](https://github.com/RujingXu-bit/portfolio-analytics-web) ·
[CSV Import Guide](docs/csv-import.md) ·
[Interview Guide](docs/interview-guide.md) ·
[Resume Entry](docs/resume-project-entry.md)

![Portfolio Analytics dashboard showing four historical metrics and asset allocation](docs/assets/dashboard-demo.png)

The 1080p [three-minute narrated walkthrough](https://github.com/RujingXu-bit/portfolio-analytics-api/releases/download/v1.1.0/portfolio-analytics-demo.mp4)
covers the public full-stack workflow, financial methodology, deterministic AI
fallback, security boundary, and CI evidence. Its Provider-backed frames are
dated and labelled as pre-recorded; the outage fallback is explicitly marked as
a deterministic offline fixture.

A FastAPI modular monolith for recording portfolios and transactions, valuing
multi-asset holdings, and returning deterministic, explainable historical risk
analytics. PostgreSQL stores the owned transaction ledger, Redis caches market
data and optional generated narratives, a configured yfinance or Twelve Data
adapter supplies adjusted-close history, and an optional DeepSeek adapter can
explain metrics that the backend has already calculated.

This V1 does not predict prices, automate trades, or guarantee returns. The LLM
never calculates or overrides financial metrics or the deterministic risk
classification. Unit tests and normal CI are fully offline.

Current release: `1.1.0` / Git tag `v1.1.0`. See the
[release changelog](CHANGELOG.md), [API-only demo](docs/demo.md),
[video script](docs/demo-video-script.md), and
[interview guide](docs/interview-guide.md). The public-demo deployment runbook
is in [deployment](docs/deployment.md). This is a portfolio project, not a
production-capacity claim or investment-advice service.

完全不懂代码的使用者请从
[中文零基础项目说明](docs/项目说明-零基础.md)开始。

## Architecture

```text
HTTP client
  -> request-ID / JSON logging middleware
  -> FastAPI validation and authentication
  -> application services (ownership + transaction boundaries)
       -> SQLAlchemy repositories -> PostgreSQL 16
       -> market-data cache -> bounded retry -> observed configured provider
                               Redis 7         (yfinance or Twelve Data)
       -> deterministic domain valuation and metrics
       -> deterministic risk rules -> optional cached DeepSeek narrative
```

The API layer contains no SQL or financial algorithms. Domain calculations do
not depend on FastAPI, SQLAlchemy, Pandas, a network, or the system clock.
Provider-specific objects are converted to the project's `PriceBar` type at the
infrastructure boundary. See [architecture](docs/architecture.md),
[methodology](docs/methodology.md), and [decisions](docs/decisions.md) for the
complete design and trade-offs.

## Requirements

- Git
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop or another Docker Compose-compatible runtime
- Python 3.12; uv installs the pinned project version when needed

No external API credential is required for installation, tests, health,
authentication, or deterministic insights. Analytics require internet access.
The default yfinance provider needs no key; the optional Twelve Data provider
requires `TWELVE_DATA_API_KEY`.

## Clean installation and startup

From the repository root:

```bash
make install
cp .env.example .env
```

Replace `JWT_SECRET_KEY=replace_me` in `.env` with a private value containing at
least 32 characters. The checked-in values are local-only placeholders.

Start PostgreSQL and Redis, migrate the empty database, and run the API:

```bash
make infra-up
make infra-check
make db-upgrade
make dev
```

Application startup intentionally does not run migrations. Run
`make db-upgrade` once for a new database and after pulling a revision that
contains a new migration. `make db-check` reports whether ORM metadata would
require another migration.

The API and interactive OpenAPI documentation are available at:

- <http://127.0.0.1:8000>
- <http://127.0.0.1:8000/docs>

Verify health in another terminal:

```bash
curl -i http://127.0.0.1:8000/health
```

The response is `200 {"status":"ok"}` and includes an `X-Request-ID` header.
Stop local services without deleting the PostgreSQL volume with
`make infra-down`.

After startup, `make demo` runs the complete API-driven V1 flow without
manual database edits: registration/login, owned portfolio creation, DEPOSIT,
idempotent BUY replay, analytics, and deterministic insight. The normal app's
analytics call uses the configured provider, so this live demo requires
internet access. See the [three-minute talk track](docs/demo.md).

## Environment variables

Pydantic reads process variables first and a local `.env` second. Do not commit
`.env`; only `.env.example` is tracked.

### Application settings

| Variable | Example/default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Environment label; it does not enable a separate production mode. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `DATABASE_URL` | local PostgreSQL on `55432` | SQLAlchemy async application database URL. |
| `TEST_DATABASE_URL` | `_test` database on `55433` | Disposable integration/benchmark database; safety checks require a name ending in `_test`. |
| `REDIS_URL` | `redis://localhost:6379/0` | Application market-data and insight cache. |
| `TEST_REDIS_URL` | `redis://localhost:56379/0` | Disposable test/benchmark Redis. |
| `REDIS_CONNECT_TIMEOUT_SECONDS` | `1` | Redis connection timeout. |
| `REDIS_READ_TIMEOUT_SECONDS` | `1` | Redis read timeout. |
| `MARKET_DATA_PROVIDER` | `yfinance` | Explicit provider selection: `yfinance` or `twelve_data`; there is no silent failover. |
| `TWELVE_DATA_API_KEY` | empty | Required only when `MARKET_DATA_PROVIDER=twelve_data`; never logged or cached. |
| `MARKET_DATA_REQUEST_TIMEOUT_SECONDS` | `10` | Timeout passed to one upstream provider request. |
| `MARKET_DATA_OPERATION_TIMEOUT_SECONDS` | `12` | Deadline for the entire provider retry sequence. |
| `MARKET_DATA_MAX_ATTEMPTS` | `3` | Maximum attempts for transient provider failures. |
| `MARKET_DATA_RETRY_BACKOFF_SECONDS` | `0.25` | Initial exponential retry delay. |
| `MARKET_DATA_MUTABLE_TTL_SECONDS` | `300` | TTL for daily ranges ending today or later. |
| `MARKET_DATA_HISTORICAL_TTL_SECONDS` | `86400` | TTL for completed historical ranges. |
| `MARKET_DATA_STALE_TTL_SECONDS` | `604800` | Retention for an explicitly stale fallback copy. |
| `DEFAULT_BASE_CURRENCY` | `USD` | Validated project setting; V1 clients should still send `base_currency` explicitly when it is not USD. |
| `JWT_SECRET_KEY` | required | Private HS256 signing value, at least 32 characters. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access-token lifetime. |
| `RATE_LIMIT_ENABLED` | `true` | Enables Redis fixed-window limits; failures still fail open. |
| `RATE_LIMIT_TRUST_PROXY_HEADERS` | `false` | Trust the first `X-Forwarded-For` address only behind a controlled edge proxy. |
| `RATE_LIMIT_HASH_KEY` | falls back to JWT secret | Separate HMAC key for hashing all rate-limit identifiers; set a distinct production secret. |
| `RATE_LIMIT_NAMESPACE` | `portfolio-analytics` | Redis key prefix used to isolate this deployment. |
| `RATE_LIMIT_REGISTRATION_IP_LIMIT` / `RATE_LIMIT_REGISTRATION_WINDOW_SECONDS` | `5` / `600` | Registration requests per hashed client IP per window. |
| `RATE_LIMIT_LOGIN_IP_LIMIT` / `RATE_LIMIT_LOGIN_EMAIL_LIMIT` / `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `10` / `5` / `600` | Login requests per hashed IP and normalized-email digest per window. |
| `RATE_LIMIT_ANALYTICS_USER_LIMIT` | `20` | Analytics requests per authenticated-user digest per minute. |
| `RATE_LIMIT_INSIGHTS_USER_LIMIT` | `10` | Insight generation/history requests per user digest per minute. |
| `RATE_LIMIT_AUTHENTICATED_USER_LIMIT` / `RATE_LIMIT_AUTHENTICATED_WINDOW_SECONDS` | `120` / `60` | Other authenticated requests per user digest per window. |
| `DEEPSEEK_API_KEY` | empty | Optional; an empty value keeps insights deterministic and offline. |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Model used only when the optional key is configured. |
| `DEEPSEEK_TIMEOUT_SECONDS` | `8` | Hard application/client timeout for narrative generation. |
| `INSIGHT_CACHE_TTL_SECONDS` | `86400` | TTL for a validated generated narrative. |

`DEFAULT_BASE_CURRENCY` is retained as configuration metadata; the current
request schema defaults an omitted `base_currency` to USD. Changing this
setting does not rewrite existing portfolios or perform currency conversion.

### Compose settings

| Variable | Default | Purpose |
|---|---:|---|
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | local placeholders | Development PostgreSQL initialization. |
| `POSTGRES_PORT` | `55432` | Development PostgreSQL host port. |
| `REDIS_PORT` | `6379` | Development Redis host port. |
| `TEST_POSTGRES_DB` / `TEST_POSTGRES_USER` / `TEST_POSTGRES_PASSWORD` | `_test` placeholders | Disposable test PostgreSQL initialization. |
| `TEST_POSTGRES_PORT` | `55433` | Test PostgreSQL host port. |
| `TEST_REDIS_PORT` | `56379` | Test Redis host port. |

## Authentication and ownership

Register a user. Passwords must contain 12–128 characters and are persisted
only as Argon2 hashes:

```bash
curl -i -X POST http://127.0.0.1:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"investor@example.com","password":"local-demo-password"}'
```

Login returns a Bearer access token and its lifetime in seconds:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"investor@example.com","password":"local-demo-password"}'
```

Copy `access_token` from the response and use it below as `<token>`. Unknown
users, incorrect passwords, malformed tokens, and expired tokens share the same
401 response. Every portfolio path requires authentication. Application
services enforce ownership and return the same 404 for a missing portfolio and
another user's portfolio, resisting direct-ID enumeration.

## Implemented API

| Method | Path | Success | Purpose |
|---|---|---:|---|
| `GET` | `/health` | 200 | Process health. |
| `POST` | `/auth/register` | 201 | Register a user. |
| `POST` | `/auth/login` | 200 | Issue a Bearer access token. |
| `POST` | `/portfolios` | 201 | Create an owned portfolio. |
| `GET` | `/portfolios` | 200 | List the current user's portfolios with pagination. |
| `GET` | `/portfolios/{id}` | 200 | Read one owned portfolio. |
| `POST` | `/portfolios/{id}/transactions` | 201 or 200 replay | Create an idempotent transaction. |
| `GET` | `/portfolios/{id}/transactions` | 200 | Read the ordered transaction ledger. |
| `POST` | `/portfolios/{id}/transactions/import/preview` | 200 | Validate a UTF-8 CSV without writing. |
| `POST` | `/portfolios/{id}/transactions/import` | 200 | Commit valid CSV rows with per-row outcomes. |
| `GET` | `/portfolios/{id}/analytics` | 200 | Calculate historical portfolio analytics. |
| `POST` | `/portfolios/{id}/insights` | 200 | Persist and return a deterministic or enriched risk summary. |
| `GET` | `/portfolios/{id}/insights` | 200 | Read persisted analysis snapshots with pagination. |

Both list endpoints return `items`, `total`, `limit`, and `offset`. `limit`
defaults to 20 and is capped at 100; `offset` defaults to zero. Portfolio rows
are newest-first by creation time, and snapshots are newest-first by generation
time, with IDs used as deterministic tie-breakers. Every result remains scoped
to the authenticated owner.

Public-demo request limits are documented in [deployment](docs/deployment.md).
An exceeded limit returns 429 with `{"error":{"code":"rate_limited",...}}`
and a whole-second `Retry-After` header. Redis keys contain keyed digests rather
than plaintext emails, IPs, user IDs, JWTs, or request bodies. Redis failure is
logged as `rate_limit_bypass` and the core request continues.

### Portfolio and transaction flow

Create a portfolio:

```bash
curl -X POST http://127.0.0.1:8000/portfolios \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Demo portfolio","base_currency":"USD"}'
```

Use its returned `id` as `<portfolio-id>`. A BUY or SELL requires `symbol`,
`quantity`, and `unit_price`; a DEPOSIT or WITHDRAWAL instead requires
`cash_amount`. All accept non-negative `fees` and a timezone-aware
`occurred_at`.

```bash
curl -i -X POST \
  http://127.0.0.1:8000/portfolios/<portfolio-id>/transactions \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "external_id":"demo-buy-001",
    "transaction_type":"BUY",
    "occurred_at":"2026-01-02T09:00:00Z",
    "symbol":"AAPL",
    "quantity":"2",
    "unit_price":"100",
    "fees":"0"
  }'
```

`external_id` is unique within a portfolio. Repeating an identical normalized
payload returns the existing transaction with 200 and never posts it twice;
reusing the ID for different data returns 409. Holdings may not become
negative.

Read the portfolio and ledger:

```bash
curl -H 'Authorization: Bearer <token>' \
  http://127.0.0.1:8000/portfolios/<portfolio-id>

curl -H 'Authorization: Bearer <token>' \
  http://127.0.0.1:8000/portfolios/<portfolio-id>/transactions
```

List owned portfolios for a dashboard:

```bash
curl -H 'Authorization: Bearer <token>' \
  'http://127.0.0.1:8000/portfolios?limit=20&offset=0'
```

The ledger is ordered by occurrence time, ingestion time, and ID. PostgreSQL
uses `NUMERIC` columns and Python business objects use `Decimal` for quantities,
prices, cash, and fees.

For batch input, follow the [CSV import guide](docs/csv-import.md). Preview is
write-free and reports `ready`, `replay`, or `invalid` per row. Commit processes
the same CSV through the existing ownership, Decimal, domain, ledger-lock, and
idempotency boundaries and reports `created`, `replayed`, or `failed`; an
expected row failure does not hide or roll back successful rows.

### Analytics

Both dates are required and inclusive:

```bash
curl -H 'Authorization: Bearer <token>' \
  'http://127.0.0.1:8000/portfolios/<portfolio-id>/analytics?start_date=2026-01-02&end_date=2026-01-30'
```

The response contains `as_of`, cash-flow-adjusted `simple_return`, annualized
volatility, maximum drawdown, Sharpe ratio, exact latest `portfolio_value` and
`cash_balance`, per-security market values and weights, `methodology`, and the
aggregate market-data `stale` flag. An undefined statistic is JSON `null`.

Historical daily prices use adjusted close. Transactions are replayed without
look-ahead; each valuation uses only prices already observed. Valuation dates
are the union of symbol trading dates, and an old close may be carried forward
only after it has appeared. External deposits, withdrawals, and the explicit
funding shortfall of an imported BUY are removed from the performance return;
fees remain in performance. Weights divide security market value by total
portfolio value including cash.

Metrics use simple period returns and 252 annual periods. The current running
app exposes an illustrative annual risk-free rate of 4%, dated 2026-01-01 and
held constant over the requested interval; it is fixture methodology, not a
live observed rate. Sharpe ratio is undefined for insufficient or zero-
volatility returns. Maximum drawdown is calculated from the cash-flow-adjusted
cumulative wealth path. Every assumption is repeated in the response and fully
defined in [financial methodology](docs/methodology.md).

### Risk insight

```bash
curl -X POST -H 'Authorization: Bearer <token>' \
  'http://127.0.0.1:8000/portfolios/<portfolio-id>/insights?start_date=2026-01-02&end_date=2026-01-30'
```

`risk-rules-v1` deterministically classifies volatility, drawdown, historical
Sharpe ratio, and latest single-security concentration. It always controls the
risk level, factors, limitations, and informational-use disclaimer. If
`DEEPSEEK_API_KEY` is absent—or the model times out, is rate-limited, returns
invalid JSON, or fails content validation—the same endpoint succeeds with the
rules summary.

When enabled, DeepSeek receives only structured metrics, symbol weights,
methodology, `as_of`, and freshness. It receives no credentials, user identity,
portfolio name, transactions, raw prices, or cash balance. It may enrich only
the narrative and additional limitations. Successful generated narratives are
cached, and every returned result is saved as an `AnalysisSnapshot` with its
actual generator, model, prompt/rule version, generated time, and structured
input summary. Read the saved history with:

```bash
curl -H 'Authorization: Bearer <token>' \
  'http://127.0.0.1:8000/portfolios/<portfolio-id>/insights?limit=20&offset=0'
```

Historical RC rows whose optional narrative provenance fields were empty remain
readable; those fields are returned as JSON `null`. No schema migration is
needed for these query endpoints.

## Errors, request IDs, and logs

Errors use one stable envelope:

```json
{
  "error": {
    "code": "portfolio_not_found",
    "message": "portfolio 00000000-0000-0000-0000-000000000000 was not found"
  }
}
```

Validation uses `validation_error`; duplicate registration does not echo the
email. Unexpected exceptions return only `internal_error` and a generic
message. Market-data errors map as follows when no stale copy can be used:

| Condition | HTTP | Code |
|---|---:|---|
| invalid or empty symbol data | 422 | `market_data_not_found` |
| malformed provider data | 502 | `market_data_invalid_response` |
| rate limit | 503 | `market_data_rate_limited` |
| temporary provider/network failure | 503 | `market_data_unavailable` |
| operation timeout | 504 | `market_data_timeout` |

Every HTTP response includes `X-Request-ID`. A valid caller-supplied UUID is
normalized and retained; a missing or invalid value is replaced and the
invalid text is never logged. Application and Uvicorn logs are UTC, one-line
JSON with fixed fields for the request, cache, provider outcome, status, and
latency. They do not include bodies, query strings, headers, passwords, JWTs,
API keys, settings, cache payloads, or raw exception messages.

## Cache, retry, and stale behavior

Market-data cache keys are versioned by provider, interval, price basis,
symbol, and inclusive date range. With the defaults, ranges ending today or
later live for 300 seconds, completed history for 86,400 seconds, and a shadow
copy for 604,800 seconds. Transient provider failures use at most three calls,
0.25/0.5-second backoff, and one 12-second operation deadline. After retries
are exhausted, only a validated retained copy may return with `stale: true`.
Deterministic symbol/data errors never use stale data. Corrupt entries and Redis
failures are bypassed safely. V1 exposes daily history, not a quote endpoint.

Cache logs use the measurable states `hit`, `miss`, `stale`, `bypass`, and
`corrupt`. Provider logs describe only actual upstream attempts and include
duration, success/failure, and a stable error category.

## Runtime image

Build the Python 3.12 slim image and run its isolated health smoke:

```bash
make image-build
make image-smoke
```

The locked image contains production dependencies and Alembic revisions, runs
as non-root UID `10001`, and does not contain tests, local environments, or
benchmark artifacts. The smoke starts a short-lived container on a random
loopback port and validates `/health` plus `X-Request-ID`.

To run the image against the Compose services after `make infra-up` and
`make db-upgrade`:

```bash
docker run --rm --name portfolio-analytics-api \
  --network portfolio-analytics_default \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://portfolio:portfolio_local_only@postgres:5432/portfolio \
  -e REDIS_URL=redis://redis:6379/0 \
  -e JWT_SECRET_KEY=replace-with-at-least-32-private-characters \
  portfolio-analytics-api:local
```

This remains the local invocation. The checked-in Render Blueprint and the
Neon/Upstash secret, migration, health, and rollback procedure are documented
in [public demo deployment](docs/deployment.md). That baseline does not claim
high availability or a production SLA.

## Tests, CI, and measured performance

Useful commands:

```bash
make lint                  # Ruff and formatting check
make typecheck             # strict mypy
make test                  # offline unit tests with coverage
make check                 # lint + typecheck + offline unit tests
make infra-test-up         # disposable PostgreSQL/Redis test services
make test-integration      # PostgreSQL/Redis integration tests
make test-all              # unit + integration tests with coverage
make load-test             # offline cold/hot Locust benchmark
make test-contract         # opt-in real yfinance contract
make image-smoke           # build and health-check the runtime image
make demo                  # public API V1 release flow
```

`make test-integration`, `make test-all`, and `make load-test` require the
disposable test services. Stop only those containers with
`make infra-test-down`. The migration integration test refuses to reset a
database whose name does not end in `_test`. Normal unit/integration tests and
CI never call yfinance or DeepSeek. A real DeepSeek contract additionally
requires `RUN_DEEPSEEK_CONTRACT=1` and a local `DEEPSEEK_API_KEY`; it is not
enabled by a normal quality command.

The final W5.4 local `make test-all` run on 2026-07-22 passed 168 tests (156
unit, 12 integration) with 93% combined branch coverage. `make check` passed
Ruff, format checking, strict mypy over 78 source files, and the 156-test unit
suite with 89% branch coverage. These are repository test results, not a claim
about untested production environments.

The formal `1.0.0` release gates passed 170 tests (158 unit, 12 integration)
with 93% combined branch coverage; `make check` covered 80 source files and the
158-test unit suite at 89% branch coverage. The non-root image smoke and the
`1.0.0` wheel/source-distribution build also passed with Python requirement
`>=3.12`; exact commands and results are recorded in `PROJECT_PLAN.md` and
`CHANGELOG.md`.

The reproducible W5.2 local load test used macOS 26.5.2 arm64, Python 3.12.13,
Locust 2.46.1, one Uvicorn worker, PostgreSQL 16, Redis 7, 10 users spawned at
2 users/second for 60 seconds, 2,000 deterministic price bars, and a synthetic
provider delayed by 50 ms:

| Scenario | Requests | P50 | P95 | Throughput | Errors | Cache hit rate |
|---|---:|---:|---:|---:|---:|---:|
| Cold, unique 60–252-day ranges | 7,448 | 66 ms | 120 ms | 124.343 req/s | 0 | 0% |
| Hot, repeated prewarmed 252-day range | 25,020 | 22 ms | 34 ms | 417.561 req/s | 0 | 100% |

The cold run logged 7,448 provider calls at 51.000 ms P50 and 52.023 ms P95;
the measured hot interval made no provider call. This is a local, single-worker
comparison of cache paths with a synthetic upstream—not a production capacity
or yfinance performance claim. Full reproduction details are in
[performance results](docs/performance.md).

GitHub Actions uses the pinned uv version and lockfile, PostgreSQL 16 and Redis
7 service containers, CI-only settings, an empty `_test` migration/check,
offline unit and integration suites, and the runtime image smoke. Any command
failure stops the job; external provider contracts are excluded.

## Security and V1 limits

- Secrets come only from environment variables; the repository contains no
  usable token or API key.
- Passwords are Argon2 hashes; JWT validation pins HS256 and validates issuer,
  audience, type, issue time, and expiry.
- Users can access only their own portfolios, transactions, analytics, and
  generated insight flow.
- Financial values persist as decimal `NUMERIC`, never binary floating-point.
- The API provides historical analytics and informational risk explanations,
  not investment advice.

The `v1.1.0` backend adds owner-scoped portfolio/snapshot queries, Redis request
limits, and reproducible Render/Neon/Upstash configuration. The independent
[Next.js frontend](https://github.com/RujingXu-bit/portfolio-analytics-web) is
available as a [public demo](https://portfolio-analytics-web-hazel.vercel.app).
The project now supports explicit yfinance/Twelve Data selection and
preview-first CSV transaction import. It still has no automatic provider
failover, refresh tokens, token revocation, automatic trading, or multi-currency
conversion.

## Project structure

```text
src/portfolio_analytics_api/
├── api/              # HTTP routes, schemas, dependencies, middleware
├── application/      # use cases, ownership, transaction boundaries
├── core/             # settings and structured logging
├── domain/           # deterministic values, valuation, metrics, risk rules
├── infrastructure/   # PostgreSQL, Redis, market data, JWT, DeepSeek adapters
└── main.py            # application assembly

tests/
├── unit/             # fast and offline
├── integration/      # disposable PostgreSQL and Redis
└── contract/         # explicit real external calls
```
