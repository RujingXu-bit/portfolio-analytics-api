from collections.abc import AsyncIterator

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from portfolio_analytics_api.core import Settings
from portfolio_analytics_api.infrastructure.database import (
    AsyncSessionFactory,
    Base,
    create_database_engine,
    create_session_factory,
)
from portfolio_analytics_api.infrastructure.database import models as database_models


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def database_engine() -> AsyncIterator[AsyncEngine]:
    database_url = Settings().test_database_url
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("integration tests require a disposable _test database")

    engine = create_database_engine(database_url)
    _ = database_models
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
def session_factory(database_engine: AsyncEngine) -> AsyncSessionFactory:
    return create_session_factory(database_engine)
