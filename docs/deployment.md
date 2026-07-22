# Public demo deployment

This repository includes a Render Blueprint for the API only. The intended
public-demo topology is:

```text
Vercel frontend/BFF (F1/D1)
        -> Render Starter Docker API (Frankfurt)
              -> Neon PostgreSQL (nearest available EU region)
              -> Upstash Redis (nearest available EU region)
```

This is a low-cost portfolio demonstration, not a production SLA or a high-
availability design. The actual public deployment and end-to-end acceptance
remain D1.1 work.

## 1. Create the data services

Create Neon PostgreSQL and Upstash Redis databases near Render's `frankfurt`
region. Keep their credentials only in the provider dashboards and Render
environment settings.

For `DATABASE_URL`, start from Neon's pooled connection string, change the
driver prefix to `postgresql+asyncpg://`, retain TLS, and use an asyncpg-
compatible query string such as `?ssl=require`. Do not paste the value into a
tracked file. Validate it with the pre-deploy migration before accepting the
deployment.

For `REDIS_URL`, copy Upstash's TLS TCP connection string for a read/write user;
it begins with `rediss://`. A read-only credential cannot support cache writes,
`INCR`, `EXPIRE`, or the atomic rate-limit Lua script.

## 2. Create the Render service

Create a Blueprint from this repository's `render.yaml`. The Blueprint uses the
checked-in Dockerfile, the Starter plan, the Frankfurt region, deploy-after-CI,
`/health`, and a pre-deploy `alembic upgrade head`. Enter `DATABASE_URL` and
`REDIS_URL` through the Render dashboard when prompted. Render generates the
JWT signing and rate-limit HMAC secrets.

Do not configure `DEEPSEEK_API_KEY` for the public demo. The API will use the
deterministic `risk-rules-v1` fallback and remain independent of an LLM quota.

The Blueprint enables forwarded-IP handling because Render is the trusted edge
proxy. Do not copy that setting to an environment where arbitrary clients can
reach Uvicorn directly; otherwise a caller could forge `X-Forwarded-For`.

## 3. Deployment acceptance

Before attaching a frontend, verify:

1. The pre-deploy migration exits successfully.
2. `GET /health` returns 200 and an `X-Request-ID`.
3. Registration and login return stable JSON errors and eventually return 429
   with `Retry-After` at the documented boundaries.
4. A registered user can create a portfolio, write an idempotent transaction,
   run analytics, generate a deterministic insight, and read snapshot history.
5. Another user receives the same 404 for that portfolio as for a missing ID.
6. Application logs contain neither passwords, JWTs, database/Redis URLs,
   plaintext emails, request bodies, nor rate-limit identifiers.

The public registration UI must say: “Demo only. Do not enter real financial or
sensitive information. Demo data may be reset.”

## 4. Migration and rollback

Migrations run as a separate pre-deploy command; application startup never
changes the schema. For this release, `alembic check` reports no new schema
operation. Before a future migration, take a provider-supported database backup
or branch, review the migration, then deploy.

To roll back application code, redeploy the last known-good Git commit or tag.
Do not run `alembic downgrade` automatically: review data compatibility and get
explicit authorization before any destructive schema action. Rate-limit and
cache keys are disposable and versioned; PostgreSQL user data is not.

## 5. Operational limits

- Registration: 5 requests per IP per 10 minutes.
- Login: 10 requests per IP and 5 requests per HMAC-hashed normalized email per
  10 minutes.
- Analytics: 20 requests per authenticated user per minute.
- Insights, including history reads: 10 requests per authenticated user per
  minute.
- Other authenticated portfolio routes: 120 requests per user per minute.

Redis increments and expiry are atomic within each fixed window. Keys contain
only a scope, time bucket, and keyed SHA-256 digest—never plaintext email, IP,
JWT, or request body. Redis failures log `rate_limit_bypass` with only the
exception type and allow the core request to continue. This fail-open policy
preserves demo availability but means rate limiting is not a security boundary
when Redis is unavailable.

Provider setup references: [Render Blueprints](https://render.com/docs/blueprint-spec),
[Render health checks](https://render.com/docs/health-checks),
[Neon pooled connections](https://neon.com/docs/connect/connection-pooling), and
[Upstash Redis connections](https://upstash.com/docs/redis/overall/getstarted).
