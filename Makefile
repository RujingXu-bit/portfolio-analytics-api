IMAGE_NAME ?= portfolio-analytics-api:local

.PHONY: install dev demo test test-unit test-cov test-contract test-integration test-all lint format typecheck check load-test image-build image-smoke

install:
	uv sync --locked

dev:
	uv run uvicorn portfolio_analytics_api.main:app --reload

demo:
	uv run python -m scripts.demo_flow

test:
	uv run pytest tests/unit --cov=portfolio_analytics_api --cov-report=term-missing

test-unit: test

test-cov:
	uv run pytest tests/unit --cov=portfolio_analytics_api --cov-report=term-missing

test-contract:
	RUN_MARKET_DATA_CONTRACT=1 uv run pytest tests/contract -m contract

test-integration:
	uv run pytest tests/integration

test-all:
	uv run pytest tests/unit tests/integration --cov=portfolio_analytics_api --cov-report=term-missing

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

check: lint typecheck test

load-test:
	docker compose --profile test up -d --wait postgres-test redis-test
	uv run python -m benchmarks.run_load_test

image-build:
	docker build --tag $(IMAGE_NAME) .

image-smoke: image-build
	uv run python -m scripts.container_smoke $(IMAGE_NAME)

db-upgrade:
	uv run alembic upgrade head

db-check:
	uv run alembic check

infra-up:
	docker compose up -d --wait postgres redis

infra-down:
	docker compose down

infra-logs:
	docker compose logs -f postgres redis

infra-check:
	docker compose exec -T postgres sh -c 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'
	docker compose exec -T redis redis-cli ping

infra-test-up:
	docker compose --profile test up -d --wait postgres-test redis-test

infra-test-down:
	docker compose --profile test rm -sf postgres-test redis-test
