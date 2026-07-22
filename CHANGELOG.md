# Changelog

All notable changes to this project are documented here. The format follows
Keep a Changelog conventions, and package versions follow PEP 440.

## [Unreleased]

### Added

- An async Twelve Data market-data adapter using total-return-adjusted daily
  prices, the existing `PriceBar` contract, stable provider errors, bounded
  retries, provider-specific cache keys, and an opt-in real contract test.
- Explicit `MARKET_DATA_PROVIDER` configuration. yfinance remains the
  credential-free default; Twelve Data requires an environment-only API key
  and never activates through silent failover.

## [1.1.0] - 2026-07-22

First public-demo backend enhancement release. The corresponding Git tag is
`v1.1.0`.

### Added

- Owner-scoped, newest-first, offset-paginated Portfolio listing and
  AnalysisSnapshot history APIs, including compatibility with nullable RC-era
  snapshot provenance.
- Redis fixed-window limits for registration, login IP and keyed email,
  analytics, insights, and other authenticated routes. Rate-limit identifiers
  are HMAC-SHA256 digests; 429 responses use the stable `rate_limited` code and
  `Retry-After`.
- Fail-open Redis degradation with secret-safe `rate_limit_bypass` logging.
- A Render Docker Blueprint and Neon/Upstash deployment runbook for the later
  public-demo deployment task.

### Security and deployment notes

- Forwarded client-IP headers are disabled by default and enabled only in the
  Render Blueprint, where Render is the trusted edge proxy.
- The public configuration intentionally omits `DEEPSEEK_API_KEY`; deterministic
  risk summaries remain the reliable default.
- This configuration is a portfolio-demo baseline, not a production SLA,
  high-availability design, or authorization boundary.

### Release verification

- `make check` passed Ruff, formatting, strict mypy over 85 source files, and
  177 offline unit tests at 89% branch coverage.
- `make test-all` passed all 192 unit/integration tests at 93% branch coverage,
  including empty-database migrations and a real Redis concurrent fixed-window
  boundary/expiry check.
- The production-only non-root image passed `make image-smoke`; `uv build`
  produced the `1.1.0` wheel and source distribution with Python `>=3.12`
  metadata. `uv lock --check`, `make db-check`, Compose validation, Render YAML
  parsing, and `git diff --check` also passed.

## [1.0.0] - 2026-07-22

First general-availability V1 release. This promotes the accepted
`v1.0.0-rc.1` candidate without changing its runtime API or financial
methodology. The corresponding Git tag is `v1.0.0`.

### Release verification

- Week 5 and the final milestone review passed on a synchronized, clean
  `origin/main` baseline with no unresolved findings.
- `make check` passed Ruff, formatting, strict mypy over 80 source files, and
  158 offline unit tests at 89% branch coverage. `make test-all` passed all 170
  unit/integration tests at 93% branch coverage, including the empty-database
  migration checks.
- `make image-smoke` built the production-only image and passed its non-root
  health/request-ID smoke. `uv build` produced the `1.0.0` wheel and source
  distribution with Python `>=3.12` metadata; `uv lock --check`, Compose
  validation, and `git diff --check` also passed.
- Real yfinance and DeepSeek contract calls remain explicit opt-in checks and
  are not normal CI dependencies.

### Known limits

- Historical analytics only; no forecasting, automatic trading, guaranteed
  returns, production-capacity claim, or investment advice.
- No portfolio-list or insight-history endpoint, refresh-token/revocation
  system, second real provider, frontend, currency conversion, rate limiting,
  or production orchestration in `v1.0.0`.
- The 4% risk-free rate dated 2026-01-01 remains an explicitly labeled
  illustrative methodology input rather than a live observation.

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
