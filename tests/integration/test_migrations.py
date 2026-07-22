from asyncio import run
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Numeric, inspect, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from portfolio_analytics_api.core import Settings


def _alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _require_disposable_database(database_url: str) -> None:
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        pytest.fail(
            f"refusing to reset non-test database {database_name!r}; "
            "TEST_DATABASE_URL must end with _test"
        )


async def _reset_public_schema(database_url: str) -> None:
    _require_disposable_database(database_url)
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def _inspect_schema(connection: Connection) -> dict[str, Any]:
    inspector = inspect(connection)
    return {
        "tables": set(inspector.get_table_names()),
        "transaction_columns": {
            column["name"]: column for column in inspector.get_columns("transactions")
        },
        "transaction_uniques": {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("transactions")
        },
        "transaction_checks": {
            constraint["name"]
            for constraint in inspector.get_check_constraints("transactions")
        },
        "portfolio_foreign_keys": inspector.get_foreign_keys("portfolios"),
    }


async def _schema_details(database_url: str) -> dict[str, Any]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_inspect_schema)
    finally:
        await engine.dispose()


def test_empty_database_upgrades_to_schema_matching_orm_metadata() -> None:
    database_url = Settings().test_database_url
    run(_reset_public_schema(database_url))
    config = _alembic_config(database_url)

    command.upgrade(config, "head")
    command.check(config)

    details = run(_schema_details(database_url))
    assert details["tables"] == {
        "alembic_version",
        "analysis_snapshots",
        "assets",
        "portfolios",
        "transactions",
        "users",
    }

    columns = details["transaction_columns"]
    for name, precision, scale in (
        ("quantity", 28, 12),
        ("unit_price", 20, 8),
        ("cash_amount", 20, 8),
        ("fees", 20, 8),
    ):
        column_type = columns[name]["type"]
        assert isinstance(column_type, Numeric)
        assert column_type.precision == precision
        assert column_type.scale == scale

    assert "uq_transactions_portfolio_external" in details["transaction_uniques"]
    assert details["transaction_checks"] == {
        "ck_transactions_cash_amount_positive",
        "ck_transactions_fees_non_negative",
        "ck_transactions_payload_matches_type",
        "ck_transactions_quantity_positive",
        "ck_transactions_unit_price_positive",
    }
    assert details["portfolio_foreign_keys"][0]["referred_table"] == "users"
