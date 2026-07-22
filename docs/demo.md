# Three-Minute V1 Release Demo

This demo uses only public HTTP endpoints. It creates its own uniquely named
user, portfolio, deposit, and BUY; proves transaction idempotency; calculates
analytics; and persists a risk insight. It never edits PostgreSQL manually and
does not require a temporary source-code patch.

## Prepare once

```bash
make install
cp .env.example .env
# Set a private JWT_SECRET_KEY with at least 32 characters in .env.
make infra-up
make db-upgrade
make dev
```

The normal application uses yfinance, so the live analytics portion needs
internet access but no API credential. Leave `DEEPSEEK_API_KEY` empty to
demonstrate the deterministic fallback without an external LLM.

In a second terminal, run:

```bash
make demo
```

Optional arguments can select another application URL, symbol, or inclusive
historical interval:

```bash
uv run python -m scripts.demo_flow \
  --base-url http://127.0.0.1:8000 \
  --symbol AAPL \
  --start-date 2026-01-02 \
  --end-date 2026-01-30
```

The command prints no password or access token. Its compact JSON output shows
the portfolio ID, two persisted transactions, successful idempotent replay,
the four metrics, exact latest value, freshness, deterministic risk level, and
actual insight generator/version. It also validates a UUID `X-Request-ID` on
every response.

## Timed talk track

### 0:00–0:30 — Problem and boundary

“This is a modular-monolith backend for explainable historical portfolio
analytics. PostgreSQL owns the ledger, Redis protects the market-data path,
deterministic domain code calculates every financial number, and the optional
LLM can explain—but never calculate or override—risk.”

Show the architecture diagram in `README.md`. Point out that the API layer has
no SQL or financial algorithms and that domain code has no framework or network
dependency.

### 0:30–1:15 — Public API and correctness

Run `make demo`. While it executes, explain:

- registration/login and Bearer authentication;
- owner binding on every portfolio operation;
- DEPOSIT plus BUY submitted through HTTP;
- the identical BUY replay returning the same transaction instead of double
  posting;
- Decimal persistence and ordered ledger replay.

### 1:15–2:05 — Financial result

Use the printed analytics block:

- adjusted-close data and no look-ahead price alignment;
- cash-flow-adjusted simple return;
- 252-period sample volatility, maximum drawdown, and historical Sharpe ratio;
- exact portfolio value plus `as_of`, methodology, and `stale` provenance.

State that the 4% risk-free rate dated 2026-01-01 is an illustrative, disclosed
input rather than a live observation.

### 2:05–2:35 — Resilience, security, and AI fallback

Point to the returned generator `deterministic_rules` when DeepSeek is disabled.
Explain that Redis uses versioned keys and explicit
hit/miss/stale/bypass/corrupt events;
only transient failures retry, and a retained price is never returned without
`stale: true`. Every response carries a UUID request ID, while logs exclude
bodies, queries, tokens, passwords, keys, and raw exception messages.

### 2:35–3:00 — Evidence and limits

Show the CI and measured-performance sections in `README.md`: empty-database
migration, offline unit/integration suites, non-root container smoke, and the
reproducible cold/hot cache comparison. Close by naming the limits: historical
analytics rather than prediction/advice, one real provider, no second provider,
refresh-token system, automatic trading, or multi-currency conversion. Mention
that v1.1 adds dashboard queries and Redis request limits without changing the
financial methodology, and that the independent frontend is publicly deployed.

## Demo recovery without hidden state

- A duplicate-email error is avoided by the command's unique generated user.
- Re-running the command creates a new isolated demo portfolio; it does not
  require deleting previous rows.
- If yfinance is unavailable, the API returns its stable 502/503/504 error
  rather than fabricated analytics. Do not patch the provider or hand-edit the
  database during a demo; use the verified offline tests and recorded benchmark
  as evidence, then rerun the same command when the upstream is available.
