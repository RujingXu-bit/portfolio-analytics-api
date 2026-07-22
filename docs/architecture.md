# Architecture

The application is a modular monolith. Framework, use-case, domain, and adapter
responsibilities remain separate so infrastructure can change without changing
financial algorithms.

## Current request path

```text
RequestObservabilityMiddleware (request ID + structured request log)
    -> FastAPI route
    -> Redis fixed-window request policy (fail-open)
    -> AuthenticationService / PortfolioService / TransactionService
       / PortfolioAnalyticsService
        -> Argon2 PasswordHasher / JWT AccessTokenService
        -> UnitOfWork -> Portfolio / Transaction / AnalysisSnapshot repositories
                         -> PostgreSQL (SQLAlchemy + asyncpg)
        -> MarketDataProvider protocol
             -> Redis cache decorator
                  -> retry/deadline decorator
                       -> provider observation -> configured adapter
                                                    |-> yfinance
                                                    `-> Twelve Data
        -> deterministic domain analytics functions
        -> PortfolioInsightService -> deterministic rules
             -> cached optional InsightGenerator -> DeepSeek
```

The API layer validates and serializes HTTP data. It does not calculate
financial metrics or access repository storage directly.

The E1.2 request boundary applies Redis-backed fixed windows after request
validation. Registration uses a client-IP scope; login uses both client IP and
normalized email; authenticated routes use the verified user ID, with separate
analytics, insights, and general budgets. Every identifier is HMAC-SHA256
digested before it becomes part of a Redis key. The Lua increment/expiry pair is
atomic per bucket. Exceeded limits return the same 429 envelope and a
`Retry-After` value; Redis or response-parse failure records only
`rate_limit_bypass` plus the exception type and allows the use case to continue.
This protects shared demo capacity but is deliberately not an authorization
boundary.

Client-IP forwarding is disabled by default. The Render deployment alone
enables the first `X-Forwarded-For` address because its edge proxy is trusted;
directly reachable deployments must leave it disabled or provide an equivalent
trusted-proxy boundary.

Every HTTP request is assigned a UUID request ID. A valid incoming
`X-Request-ID` is normalized and retained; an absent or malformed value is
replaced, and the selected ID is returned on every response. The middleware
binds that ID through a `ContextVar`, so request completion, cache, provider,
and optional insight fallback events share one correlation value even when
requests overlap. Logs are one-line JSON with a fixed field allowlist. They do
not include request bodies, query strings, authorization headers, settings, or
exception messages. Unexpected exceptions return a generic 500 body while the
log retains only the exception type and stable error category.

The application layer owns use-case orchestration and transaction boundaries.
Authentication normalizes email addresses, moves Argon2 work off the event
loop, persists only password hashes, and issues time-limited access tokens. JWT
validation pins the HS256 algorithm and requires subject, issue time, expiry,
issuer, audience, and access-token type claims. The signing key is supplied only
through environment settings.

Portfolio and transaction writes use a fresh unit of work. Analytics loads the
persistent ordered transaction ledger, identifies symbols held or traded in the
requested interval, requests their date-bounded price series concurrently, and
composes the cash-flow-adjusted valuation and four domain metrics into
`PortfolioAnalytics`.

The E2.2 CSV input adapter accepts bounded UTF-8 `text/csv`, rejects unknown or
ambiguous headers, and converts each row through the same `TransactionInput`
validation into an application candidate. Preview verifies ownership before
parsing and simulates candidates against the owned ledger without writing.
Commit processes rows top to bottom by calling the existing
`TransactionService`; every created row therefore retains the Portfolio lock,
Decimal normalization, domain/position validation, unique `external_id`, and
transaction boundary. Expected row failures are returned explicitly while
successful rows remain committed.

Dashboard query use cases also stay behind repository ports. Portfolio listing
filters by the authenticated owner before applying newest-first creation order,
then `limit`/`offset`; snapshot history first verifies ownership of the parent
portfolio and then applies newest-first generation order and the same page
shape. Both use an ID tie-breaker and a separate owner-scoped count. The
snapshot response maps only already-persisted JSON and provenance columns, so
it requires no migration and preserves nullable narrative fields from RC-era
rows.

All portfolio routes resolve the current user through one Bearer-token
dependency, but authorization remains an application-service invariant rather
than a route-only check. Creation assigns the authenticated user as owner;
portfolio reads, transaction writes/listing, and analytics compare that owner
before accessing related data. A missing portfolio and another user's portfolio
both return the same 404 result to resist direct-ID enumeration. PostgreSQL also
requires non-null ownership. The W4.2 migration refuses to guess ownership when
legacy null rows exist, so it never deletes data or silently assigns it to an
arbitrary user.

The domain layer contains immutable values and deterministic financial
functions. It has no FastAPI, database, Pandas, provider, network, system clock,
or infrastructure dependency.

The infrastructure layer supplies PostgreSQL repositories, real yfinance and
Twelve Data adapters, and offline adapters used by unit tests. Every provider
returns only the project's `PriceBar` type. The yfinance adapter runs its
blocking SDK call in a worker thread, explicitly requests unadjusted columns so
it can select `Adj Close`, and normalizes the exchange-local session date. The
Twelve Data adapter performs async HTTPS, requests `interval=1day` with
`adjust=all` and `outputsize=5000`, preserves the provider's exchange-local
session date, and maps only validated close values. Responses that reach the
5,000-point provider limit fail closed as potentially truncated; incomplete
history therefore cannot reach analytics. Pandas, HTTP responses, and vendor
payloads never leave the infrastructure layer.
The observation decorator inside the retry boundary emits one latency and
outcome event for every actual provider attempt. Cache hits therefore emit a
cache event without pretending that an upstream call occurred; retryable and
deterministic failures use stable categories rather than raw vendor messages.

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
operation deadline before reaching the configured adapter. After retries are
exhausted, the cache decorator may return a valid shadow copy marked stale.
Corrupt payloads and Redis failures are logged and safely bypassed. The async
Redis client is closed with the database engine during application shutdown.

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

The W4.3 insight path composes `PortfolioAnalyticsService` with a pure,
versioned deterministic rule function. Routes do not classify risk. The domain
function receives only `PortfolioAnalytics`, emits factors in a fixed order,
handles undefined statistics and stale input explicitly, and derives
concentration from the exact latest weights. Its output carries a fixed
informational-use disclaimer and is the guaranteed fallback boundary for W4.4.

W4.4 adds an `InsightGenerator` port whose input type contains only structured
metrics, latest weights, and methodology. The DeepSeek adapter uses the
OpenAI-compatible chat endpoint in non-thinking JSON mode, an eight-second
client and application timeout, no SDK retry, and strict Pydantic validation.
The application keeps the deterministic risk level, factors, limitations, and
disclaimer authoritative; only a validated narrative and additional
limitations are merged. Any generator exception is logged by type only and
returns the rules result. Successful generated output is cached in Redis by a
SHA-256 digest of the full structured input plus generator, model, and prompt
version; Redis failures bypass the cache.

Every insight response, including fallback output, creates an
`AnalysisSnapshot`. The row stores the actual generator/model, prompt or rules
version, application generation time, exact input-metric summary, methodology,
and returned summary. API keys remain environment-only and are never part of
the input, cache value, snapshot, response, or log message.

## Current scope

The API persists Portfolio and Transaction resources and exposes creation,
owner-scoped portfolio listing and lookup, ordered transaction listing, and
multi-asset analytics. Data survives process and engine recreation. The
market-data path uses an explicitly selected yfinance or Twelve Data adapter
behind
Redis cache, bounded retry/deadline handling, stable upstream errors, and
explicit stale metadata. W4.1 provides registration, login, password hashing,
and access-token validation. W4.2 requires Bearer authentication for every
portfolio resource and enforces ownership in both application services and the
database schema.
W4.3-W4.4 expose owner-scoped risk insights with deterministic
classification, optional DeepSeek narrative enrichment, Redis result caching,
strict fallback, durable analysis provenance, and paginated snapshot history.
E1.2 adds configurable, fail-open Redis request limits and a Docker deployment
baseline; D1.1 still owns creating and accepting the actual public services.

## CI and runtime image

The GitHub Actions quality job is deliberately offline. It installs the
checked-in lockfile with the pinned uv release, then runs Ruff, the format
check, strict mypy, and unit tests. Disposable PostgreSQL 16 and Redis 7 service
containers use only test credentials. The job upgrades an empty `_test`
database to the Alembic head, checks ORM/migration drift, runs integration
tests, and finally builds and health-checks the runtime image. Real yfinance,
Twelve Data, and DeepSeek contract tests remain explicit opt-in commands and
are not CI dependencies.

The runtime image is based on Python 3.12 slim, installs only the locked
production dependency group, includes the Alembic configuration and revisions,
and runs as numeric user `10001`. Application startup never migrates the
database: an operator or deployment job must run `alembic upgrade head` before
starting a release. The image smoke command inspects the configured user and
starts an ephemeral container on a random loopback port to verify `/health` and
the response request ID. E1.2 adds a Render Blueprint that reuses this image,
runs migrations in a separate pre-deploy step, and delegates TLS termination
and runtime secrets to Render. Actual cloud provisioning and acceptance remain
D1.1 work, and the design does not claim high availability.

## Local load-test boundary

W5.2 adds a Locust harness outside production application code. It assembles
the same FastAPI middleware, authentication, SQLAlchemy repositories, analytics
service, Redis cache, and financial domain path against the disposable `_test`
PostgreSQL and Redis services. Only the external yfinance adapter is replaced
by a deterministic 2,000-bar provider with a fixed 50 ms delay. Cold requests
use unique date ranges; hot requests share one prewarmed key. The runner parses
Locust's final response-time histogram and correlates request counts with
structured cache/provider events, failing if either scenario reports errors or
does not retain its intended cache state. It never invokes yfinance or an LLM.
