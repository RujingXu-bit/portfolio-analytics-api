# Changelog

All notable changes to this project are documented here. The format follows
Keep a Changelog conventions, and package versions follow PEP 440.

## [1.0.0rc1] - 2026-07-22

First V1 release candidate. The corresponding Git candidate tag is
`v1.0.0-rc.1`; this is a validation candidate, not a general-availability
release or a production-capacity claim.

### Added

- Owned Portfolio and idempotent BUY, SELL, DEPOSIT, and WITHDRAWAL flows backed
  by PostgreSQL 16 and Alembic migrations.
- Cash-flow-adjusted multi-asset valuation with simple return, annualized
  volatility, maximum drawdown, Sharpe ratio, exact Decimal values, `as_of`,
  methodology, and market-data freshness.
- yfinance adjusted-close adapter behind bounded retries, Redis caching, and an
  explicitly marked stale fallback.
- Argon2 authentication, expiring JWT access tokens, and application-level
  ownership enforcement.
- Deterministic risk rules, optional validated DeepSeek narrative enrichment,
  Redis insight caching, and durable analysis provenance.
- Correlated UUID request IDs, secret-safe JSON logs, provider latency events,
  and measurable cache states.
- Offline CI with PostgreSQL/Redis services, a locked non-root runtime image,
  a reproducible Locust cache comparison, and an API-driven demo command.

### Candidate verification

- A locked clean-environment install with no pre-existing `.venv` or `.env`
  completed successfully. Independent PostgreSQL/Redis services passed empty
  database migration/check, application startup, and the API-driven demo using
  real AAPL adjusted-close history without an LLM credential.
- `make check` passed Ruff, format checking, strict mypy over 80 source files,
  and 158 offline unit tests at 89% branch coverage. `make test-all` passed 170
  unit/integration tests at 93% branch coverage.
- The production-only UID `10001` image passed its health/request-ID smoke.
  The `1.0.0rc1` source distribution and wheel built successfully and reported
  Python `>=3.12` metadata.
- Real yfinance and DeepSeek contract calls remain explicit opt-in checks and
  are not normal CI dependencies.
- Exact final candidate commands are recorded in `PROJECT_PLAN.md`; measured
  load-test results remain in `docs/performance.md`.

### Known limits

- Historical analytics only; no forecasting, automatic trading, or guaranteed
  return claims.
- No portfolio-list or insight-history endpoint, refresh-token/revocation
  system, second real provider, frontend, currency conversion, or production
  orchestration.
- The current 4% risk-free rate dated 2026-01-01 is an explicitly labeled
  illustrative methodology input, not a live rate.
- Published performance is a local single-worker comparison with a synthetic
  50 ms upstream, not production capacity.
