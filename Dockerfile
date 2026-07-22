FROM ghcr.io/astral-sh/uv:0.11.30 AS uv

FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY --from=uv /uv /uvx /usr/local/bin/
COPY .python-version pyproject.toml uv.lock README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

RUN uv sync --locked --no-dev --no-editable \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER 10001
EXPOSE 8000

CMD ["uvicorn", "portfolio_analytics_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
