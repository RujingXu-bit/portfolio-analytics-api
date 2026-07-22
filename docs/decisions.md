# Architecture Decisions

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
