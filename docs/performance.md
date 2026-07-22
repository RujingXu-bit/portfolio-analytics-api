# Local Load Test

## Measured result

The W5.2 cache comparison was measured on 2026-07-22 with:

- macOS 26.5.2 on arm64;
- Python 3.12.13 and Locust 2.46.1;
- one Uvicorn worker;
- PostgreSQL 16 and Redis 7 in the repository's disposable test services;
- one user, one portfolio, one BUY transaction, one symbol, and 2,000
  deterministic business-day adjusted-close bars;
- a deterministic market-data provider with a fixed 50 ms delay;
- 10 concurrent users spawned at 2 users/second for 60 seconds per scenario.

Run the same workload from the repository root:

```bash
make load-test
```

The command starts only the disposable `postgres-test` and `redis-test`
services, resets the `_test` database, migrates it from empty, seeds the fixed
fixture through the API, and writes detailed local artifacts under ignored
`.artifacts/load-test/`. Stop the test services afterward with
`make infra-test-down`.

| Scenario | Requests | P50 | P95 | Throughput | Errors | Cache hit rate |
|---|---:|---:|---:|---:|---:|---:|
| Cold cache | 7,448 | 66 ms | 120 ms | 124.343 req/s | 0 | 0% |
| Hot cache | 25,020 | 22 ms | 34 ms | 417.561 req/s | 0 | 100% |

The cold scenario used a new 60–252 trading-day date range for every request.
Application logs confirmed 7,448 misses and 7,448 provider calls; provider
latency was 51.000 ms at P50 and 52.023 ms at P95. The hot scenario repeatedly
queried one prewarmed 252-day range. Logs confirmed 25,020 hits, no misses, and
no provider calls during the measured interval.

## Interpretation and limits

This is a reproducible local comparison of the authenticated analytics,
PostgreSQL repository, Redis cache, financial calculation, serialization, and
HTTP path. The synthetic 50 ms provider isolates cache behavior without
accessing or load-testing yfinance. The result is not a production capacity
claim: it does not model real upstream latency, multiple Uvicorn workers,
distributed clients, TLS, production hardware, or internet conditions. Do not
compare or publish these numbers without retaining the environment and workload
above.
