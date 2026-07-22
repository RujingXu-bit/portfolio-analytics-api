# Architecture Decisions

## 2026-07-22: Optional DeepSeek narrative with deterministic authority

### Context

W4.4 requires one LLM provider, structured response validation, bounded failure,
caching, and snapshot provenance. A DeepSeek API key is available for local use,
but tests and core analytics must not depend on that credential or an external
service.

### Decision

- Implement one `InsightGenerator` port and one DeepSeek adapter using the
  provider's OpenAI-compatible chat endpoint, `deepseek-v4-flash`, non-thinking
  JSON mode, an eight-second timeout, and no hidden SDK retries.
- Send only typed structured metrics, latest symbol weights, stale status, and
  methodology. Never send users, credentials, names, transactions, raw prices,
  or cash balances.
- Validate JSON with a strict Pydantic schema and reject extra fields, empty or
  oversized text, incomplete responses, and transaction/guaranteed-return
  language. Keep risk level, key factors, core limitations, and disclaimer
  deterministic.
- Treat the provider as optional. A missing key disables it; any generator
  exception returns `risk-rules-v1` without breaking the insight or analytics
  API.
- Cache only successful generated results in Redis, keyed by generator/model/
  prompt identity and a digest of the complete structured input. Persist every
  returned result as an `AnalysisSnapshot` with actual provenance and inputs.

### Trade-offs

JSON mode guarantees JSON syntax rather than full provider-side schema
conformance, so application Pydantic validation remains mandatory. Disabling
SDK retries favors a hard request bound and predictable fallback over masking a
transient failure. Cache entries avoid repeated cost for identical inputs but
are invalidated automatically by any model, prompt, methodology, metric, or
weight change.

## 2026-07-22: Versioned deterministic risk-summary rules

### Context

Risk explanations must remain available without an LLM and must be reproducible
from backend-computed analytics. The first version needs a simple, interview-
explainable concentration measure without expanding into sector or correlation
models.

### Decision

- Implement `risk-rules-v1` as a pure domain function over
  `PortfolioAnalytics`, with fixed factor order and thresholds documented in
  `docs/methodology.md`.
- Classify adverse signals from annualized volatility, maximum drawdown,
  historical Sharpe ratio, and the largest latest security weight. Never let an
  LLM compute or replace that risk level.
- Emit explicit missing-statistic, stale-data, historical-methodology, and
  concentration-scope limitations plus a fixed non-investment-advice statement.
- Expose the result through the authenticated, owner-scoped insights route so
  W4.4 can enrich the explanation while retaining this exact fallback.

### Trade-offs

Threshold rules are coarse and the largest security weight cannot represent
sector, issuer-family, liquidity, or correlation risk. Those limitations are
preferable to implying unsupported precision, and the rules remain stable,
offline, and easy to audit.

## 2026-07-22: Owner-scoped portfolio authorization

### Context

After W4.1 can identify a user, every portfolio and nested transaction or
analytics operation must reject another user's direct-ID guess. The Week 2
schema temporarily allowed null owners so its unauthenticated vertical slice
could be built first.

### Decision

- Require Bearer authentication on all existing `/portfolios` routes and pass
  the authenticated user ID into each application use case.
- Assign that ID during portfolio creation and compare it before portfolio
  reads, locked transaction writes, transaction listing, or analytics loading.
- Return the same `portfolio_not_found` 404 for absent and foreign-owned IDs so
  authorization does not reveal resource existence.
- Make `portfolios.owner_id` non-null in a new Alembic revision. If legacy null
  rows exist, stop with an actionable migration error instead of deleting them
  or fabricating an owner.

### Trade-offs

Each service method carries an explicit owner ID, which is slightly more
verbose but keeps authorization testable below HTTP routing. Existing databases
with pre-authentication portfolio rows require an operator-approved ownership
backfill before upgrading; there is no universally correct automatic owner.

## 2026-07-22: Password hashing and access-token boundary

### Context

W4.1 requires durable user registration and login without storing plaintext
credentials or coupling application services to one security library. Tokens
must be verifiable and expire predictably, while secrets remain outside version
control.

### Decision

- Normalize email addresses to lowercase and rely on the existing PostgreSQL
  unique constraint as the final concurrent-registration guard.
- Hash passwords with pwdlib's recommended Argon2 hasher in a worker thread;
  expose passwords to request handling as Pydantic `SecretStr` values and never
  persist or log them.
- Issue 30-minute HS256 access tokens containing required subject, issue time,
  expiry, issuer, audience, and token-type claims. Pin the accepted algorithm
  during verification.
- Require a signing key of at least 32 characters from `JWT_SECRET_KEY`; keep
  only a non-usable replacement marker in `.env.example`.
- Return the same 401 response for unknown users, wrong passwords, malformed
  tokens, and expired tokens. Refresh tokens and revocation remain outside V1.

### Trade-offs

Symmetric signing is simple and appropriate for this single deployable modular
monolith, but all token issuers/verifiers must protect the same secret. Access
tokens cannot be individually revoked in V1, so their lifetime stays short and
credential rotation invalidates all outstanding tokens.

## 2026-07-22: Cash-flow-adjusted multi-asset valuation

### Context

Analytics must value several securities without using future trades or prices,
while preserving compatibility with W2 ledgers that allowed BUY records without
matching DEPOSIT records. Raw changes in portfolio value cannot be reported as
returns because deposits and withdrawals would look like performance.

### Decision

- Replay aware transaction timestamps in UTC ledger order through each valuation
  date and ignore transactions after the result `as_of` date.
- Track cash plus security positions. Treat DEPOSIT and WITHDRAWAL as external
  flows and trades as internal transfers.
- Add an implicit external contribution only for the unfunded portion of a BUY;
  reject a WITHDRAWAL that exceeds cash rather than introducing margin borrowing.
- Subtract net external flow before calculating each simple period return. Fees
  always reduce value and performance.
- Align symbols on the union of observed market dates and carry only previously
  observed prices forward. Never use a future observation to value an earlier
  date.
- Return latest Decimal market values and security weights relative to total
  portfolio value, including cash, for W4 concentration rules.

### Trade-offs

Carrying a previous close makes portfolios across different trading calendars
valuatable without fabricating a future price, but it can use an older close for
an exchange holiday. The methodology exposes this policy. Implicit BUY funding
supports incomplete imported cash ledgers, while making that contribution
explicit and neutral to performance instead of silently allowing negative cash.

## 2026-07-22: Defer the optional second market-data provider

### Context

W3.1-W3.3 now provide one real yfinance adapter, deterministic fake coverage,
Redis caching, bounded retries, stable errors, and explicit stale fallback. The
required W3.5 multi-asset valuation task remains incomplete. A second real
provider is a Should/Backlog item rather than a V1 completion requirement.

### Decision

- Do not implement Finnhub, Twelve Data, or another real provider during W3.4.
- Keep the second provider in Backlog until the V1 critical path, beginning with
  W3.5, is stable and `PROJECT_PLAN.md` explicitly reprioritizes it.
- Add no provider factory, configuration enum, API credentials, endpoint, or
  dependency for an implementation that has no current consumer.
- Reuse the existing `MarketDataProvider` dependency-injection boundary and
  contract suite if a second provider is approved later.

### Trade-offs

V1 has no automatic provider failover, but avoids placing an optional external
integration ahead of required portfolio valuation, authentication, AI fallback,
and release-quality work. The current boundary preserves future switching
without changing domain calculations or application orchestration.

## 2026-07-22: Bounded market-data resilience and stale semantics

### Context

The external provider can rate-limit, time out, or return server failures. A
retry policy must not turn deterministic failures into repeated traffic or
allow an async request to wait indefinitely. Returning old data is acceptable
only when its age is explicit to API consumers.

### Decision

- Classify invalid/empty symbols and malformed data as deterministic; never
  retry them and never replace them with stale data.
- Map upstream 429 and 5xx/network failures to stable internal retryable errors;
  map transport timeouts separately.
- Attempt at most three calls with 0.25- and 0.5-second exponential backoff,
  bounded by one configurable 12-second operation deadline.
- Compose providers as cache -> retry/deadline -> yfinance. Only the outer cache
  layer may recover a retryable exhausted failure from the retained shadow key.
- Return `stale: true` in analytics when that recovery occurs; all fresh paths
  return false. Without a usable retained copy, rate limit/unavailability maps
  to HTTP 503, timeout to 504, malformed provider data to 502, and invalid or
  empty symbol data to 422.

### Trade-offs

The yfinance public API exposes one request timeout rather than independent
connect/read controls. Its 10-second transport timeout is therefore combined
with the application-level 12-second deadline; Redis separately uses one-second
connect and read timeouts. A timed-out worker-thread call may finish in the
background, but the request path remains bounded by the outer deadline.

## 2026-07-22: Redis market-data cache boundary

### Context

Repeated historical queries should not repeatedly call the external provider,
but Redis availability and cached serialization must not become correctness
dependencies. The current V1 protocol exposes daily history, not live quotes.

### Decision

- Wrap `MarketDataProvider` with a Redis-backed decorator rather than putting
  cache logic in the route, analytics service, or yfinance adapter.
- Version cache keys by schema, provider, interval, price basis, symbol, and
  inclusive date range.
- Use 300 seconds for ranges ending today or later and 86,400 seconds for
  completed historical ranges. A 604,800-second shadow copy prepares the
  explicitly marked stale fallback implemented in W3.3.
- Serialize dates as ISO strings and prices as Decimal strings; validate all
  metadata and price invariants before returning cached values.
- On Redis read or write failure, log a cache bypass and preserve the upstream
  provider result. Tests use a dedicated Redis service and unique key namespace.

### Trade-offs

The date-only protocol cannot determine an exchange's exact market-close state,
so ranges ending on the current UTC date conservatively use the short TTL. No
quote method or API is added merely to create an otherwise unused quote TTL.

## 2026-07-22: First real market-data provider

### Context

V1 requires one real source while keeping deterministic tests offline. The
provider must supply adjusted-close daily history without leaking Pandas or a
vendor response into application services, and yfinance performs blocking I/O.

### Decision

- Use yfinance as the first real provider because it supplies adjusted-close
  history without requiring a repository credential for the local demo.
- Run the blocking SDK call with `asyncio.to_thread` and pass a finite request
  timeout.
- Explicitly disable automatic adjustment and map `Adj Close` into Decimal
  `PriceBar` values with exchange-local session dates.
- Keep real-network verification behind `make test-contract`; unit tests and CI
  continue to inject the fake provider.

### Trade-offs

yfinance is an unofficial wrapper around Yahoo Finance and exposes only one
public request timeout rather than separate connect and read settings. A
bounded application deadline and stable retry/error policy compensate at the
application boundary. A paid or keyed second provider remains optional and is
not needed for V1.

## 2026-07-22: PostgreSQL persistence baseline

### Context

Week 2 introduces durable portfolio and transaction storage while authentication
is intentionally deferred to Week 4. Financial values must retain decimal
precision, migrations must be reproducible, and request-level writes need an
explicit transaction boundary.

### Decision

- Use SQLAlchemy 2.x with asyncpg and one `AsyncSession` per unit of work.
- Run Alembic migrations explicitly; application startup does not mutate schema.
- Store prices, cash amounts, and fees as `NUMERIC(20,8)` and quantities as
  `NUMERIC(28,12)`; domain and application objects continue to use `Decimal`.
- Store a nullable owner foreign key during Week 2. Authentication and non-null
  ownership enforcement remain W4.1/W4.2 work.
- Keep the transaction idempotency key unique within a portfolio.
- Keep a single three-letter base currency on each portfolio. V1 does not
  perform foreign-exchange conversion.

### Trade-offs

The nullable owner permits the planned unauthenticated Week 2 slice but is not a
completed security boundary. Async SQLAlchemy adds test setup cost, while
matching the async application ports and avoiding event-loop blocking.

## 2026-07-22: Transaction ledger and idempotency

### Context

Broker imports can retry requests, insert backdated transactions, and issue
concurrent writes. A database uniqueness check alone prevents duplicate rows
but does not prevent concurrent sales from creating a negative position.

### Decision

- Normalize symbols to uppercase and aware timestamps to UTC at the application
  boundary.
- Order ledger replay by occurrence time, ingestion time, then transaction ID.
- Lock the parent Portfolio row while checking idempotency, replaying holdings,
  and inserting a transaction.
- Treat an identical retry as success with the existing transaction; reject the
  same external ID with different normalized data.
- Enforce non-negative security positions. Cash sufficiency remains outside the
  W2 scope because imported broker histories may not include funding events.

### Trade-offs

The Portfolio lock serializes writes within one portfolio, favoring correctness
and a simple explainable implementation over maximum write throughput. It does
not serialize unrelated portfolios.
