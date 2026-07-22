# Architecture and Financial Methodology Interview Guide

## Architecture

### Why a modular monolith instead of microservices?

The V1 has one coherent transaction and ownership boundary. A modular monolith
keeps deployment, migrations, tests, and local demonstration simple while the
API, application, domain, and infrastructure packages preserve replaceable
boundaries. Kafka, Celery, and service splitting would add failure modes without
a demonstrated scaling need.

### Where are transaction and authorization boundaries?

Application services accept the authenticated user ID and own a fresh unit of
work. They check portfolio ownership before reads, locked transaction writes,
analytics, or insights. Missing and foreign-owned IDs share the same 404. The
database also requires non-null portfolio ownership.

### Why repositories and a `MarketDataProvider` protocol?

They keep domain types independent of SQLAlchemy and vendor responses. The
application consumes project-owned objects, so PostgreSQL, Redis, yfinance, and
offline fakes can be tested or replaced without rewriting financial functions.

### How is blocking yfinance safe in an async API?

The adapter moves the SDK call to a worker thread. An application deadline
bounds the request path, although an already-running worker call can finish in
the background. The cache and bounded retry decorators remain async.

### What happens when Redis fails?

Redis is an optimization, not a correctness dependency. Read/write failures
emit a `bypass` event and call the provider. Corrupt payloads are rejected.
Only a validated shadow copy can recover an exhausted transient provider
failure, and the response is explicitly `stale: true`.

### How do logs remain useful without leaking secrets?

A `ContextVar` propagates a normalized UUID request ID through HTTP, cache,
provider, and insight events. JSON serialization accepts only fixed fields such
as route, status, duration, provider, cache state, error category, and exception
type. It excludes request content, arbitrary headers, settings, payloads, and
raw exception messages.

## Financial correctness

### Why `Decimal` for money but floats for statistics?

Amounts, prices, quantities, fees, market values, and weights must preserve
decimal meaning and persist as PostgreSQL `NUMERIC`. Statistical algorithms can
operate on explicit float copies because standard deviation and square roots
need numeric libraries, but those approximations never overwrite the original
financial values and tests declare tolerances.

### Why adjusted close?

Historical returns should reflect splits and distributions. The yfinance
adapter explicitly requests unadjusted columns and selects `Adj Close`, then
normalizes exchange-local session dates. Missing timezone, duplicate date,
non-positive price, or malformed data is rejected rather than guessed.

### How are external cash flows removed from returns?

For each consecutive valuation date, the numerator subtracts net DEPOSIT,
WITHDRAWAL, and any explicit funding shortfall for an imported BUY. BUY/SELL
funded from existing cash are internal transfers. Fees are not removed, so they
reduce performance. The full-period simple return compounds those adjusted
period returns.

### How is look-ahead bias prevented across symbols?

Transactions are replayed only through each valuation date. Valuation dates are
the union of observed market dates, and a symbol's price can be carried forward
only after it has been observed. A future close is never backfilled into an
earlier portfolio value.

### How are the four metrics defined?

- Simple return compounds cash-flow-adjusted period returns.
- Annualized volatility is sample standard deviation times the square root of
  the configured 252 periods.
- Maximum drawdown is the worst fall from a prior peak in the cumulative
  adjusted-return wealth path.
- Sharpe ratio annualizes mean excess period return divided by sample standard
  deviation; it is undefined for insufficient or zero-volatility data.

### Why expose methodology and `as_of`?

The same number can mean different things under different price bases,
annualization, risk-free rates, cash-flow treatment, or date alignment.
Returning these inputs and the last actual valuation date makes results
explainable and reproducible instead of presenting false precision.

### Is the 4% risk-free rate current market data?

No. It is an illustrative rate dated 2026-01-01 and explicitly labeled as held
constant over the interval. The domain accepts the rate as input; replacing it
with an approved live source is a configuration/integration task, not a change
to the metric algorithm.

## Reliability, AI, and delivery

### Which provider failures retry?

Only rate limits, transient network/server failures, and timeouts are
retryable. Invalid symbols, empty history, or malformed deterministic data do
not retry. Defaults are three attempts, 0.25/0.5-second backoff, and one
12-second sequence deadline.

### What authority does the LLM have?

None over financial values, risk level, core factors, or disclaimer. It sees a
small structured metrics/methodology payload and may enrich narrative text.
Strict schema/content validation, timeout, rate limit, parsing failure, or a
missing key returns `risk-rules-v1` without breaking analytics.

### What does CI prove—and not prove?

It proves the lockfile installs, static checks pass, unit tests are offline, an
empty PostgreSQL database migrates without drift, PostgreSQL/Redis integration
passes, and the non-root runtime image starts. The v1.1 tests also cover atomic
rate-limit boundaries, expiry, failure bypass, and identifier hashing. CI does
not prove yfinance or DeepSeek availability, production capacity, an actual
cloud deployment, or high availability.

### What do the load-test numbers mean?

They compare cold and prewarmed cache paths on one local Uvicorn worker with a
deterministic 50 ms provider. Request/error/cache/provider counts are
cross-checked, so the comparison is reproducible. The workload does not model
real yfinance, production hardware, distributed clients, or internet latency
and must not be presented as capacity planning.

### What would you build next?

The independent frontend and public deployment are accepted. Twelve Data is now
available as an explicitly configured second market-data provider; automatic
failover is deliberately out of scope. The next evidence-led enhancement is a
preview-first CSV import with stable idempotency keys. A live dated risk-free-
rate source and token revocation remain reasonable later additions.
Do not add prediction, automatic trading, or distributed infrastructure merely
for architecture theater.
