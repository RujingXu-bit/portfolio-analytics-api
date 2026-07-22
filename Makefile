.PHONY: install dev test test-cov lint format typecheck check

install:
	uv sync --locked

dev:
	uv run uvicorn portfolio_analytics_api.main:app --reload

test:
	uv run pytest --cov=portfolio_analytics_api --cov-report=term-missing

test-cov:
	uv run pytest --cov=portfolio_analytics_api --cov-report=term-missing

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

check: lint typecheck test
