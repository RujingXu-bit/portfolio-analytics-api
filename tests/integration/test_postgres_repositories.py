import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from portfolio_analytics_api.application import (
    AuthenticationService,
    EmailAlreadyRegisteredError,
    NewTransaction,
    TransactionIdempotencyConflictError,
    TransactionService,
)
from portfolio_analytics_api.domain import (
    InvalidTransactionError,
    Portfolio,
    TransactionType,
    User,
)
from portfolio_analytics_api.infrastructure import (
    Argon2PasswordHasher,
    JwtAccessTokenService,
)
from portfolio_analytics_api.infrastructure.database import (
    AsyncSessionFactory,
    SqlAlchemyUnitOfWork,
)

PORTFOLIO_ID = UUID("10000000-0000-0000-0000-000000000001")
OWNER_ID = UUID("10000000-0000-0000-0000-000000000002")
AUTH_SECRET = "repository-integration-test-secret-key-32-characters"


@pytest.mark.anyio
async def test_user_repository_persists_hash_and_normalized_unique_email(
    session_factory: AsyncSessionFactory,
) -> None:
    service = AuthenticationService(
        lambda: unit_of_work_factory(session_factory),
        password_hasher=Argon2PasswordHasher(),
        access_token_service=JwtAccessTokenService(AUTH_SECRET, 30),
    )

    user = await service.register(" Investor@Example.com ", "long test password")
    token = await service.login("investor@example.com", "long test password")
    async with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        persisted = await unit_of_work.users.get(user.id)

    assert persisted is not None
    assert persisted.email == "investor@example.com"
    assert persisted.password_hash != "long test password"
    assert JwtAccessTokenService(AUTH_SECRET, 30).verify(token.value) == user.id
    with pytest.raises(EmailAlreadyRegisteredError):
        await service.register("INVESTOR@example.com", "another test password")


def unit_of_work_factory(
    session_factory: AsyncSessionFactory,
) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(session_factory)


def trade(
    external_id: str,
    transaction_type: TransactionType,
    quantity: str,
    *,
    day: int,
) -> NewTransaction:
    return NewTransaction(
        external_id=external_id,
        transaction_type=transaction_type,
        occurred_at=datetime(2026, 1, day, 9, tzinfo=UTC),
        symbol="AAPL",
        quantity=Decimal(quantity),
        unit_price=Decimal("123.12345678"),
        fees=Decimal("0.00000001"),
    )


async def add_portfolio(session_factory: AsyncSessionFactory) -> None:
    async with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        await unit_of_work.users.add(
            User(
                id=OWNER_ID,
                email="portfolio-owner@example.com",
                password_hash="$argon2id$test-placeholder",
            )
        )
        await unit_of_work.portfolios.add(
            Portfolio(
                id=PORTFOLIO_ID,
                owner_id=OWNER_ID,
                name="Persistent portfolio",
                base_currency="USD",
            )
        )
        await unit_of_work.commit()


@pytest.mark.anyio
async def test_repository_preserves_decimals_order_and_idempotency(
    session_factory: AsyncSessionFactory,
) -> None:
    await add_portfolio(session_factory)
    service = TransactionService(lambda: unit_of_work_factory(session_factory))

    first = await service.create(
        OWNER_ID,
        PORTFOLIO_ID,
        trade("buy-001", TransactionType.BUY, "2.000000000001", day=2),
    )
    await service.create(
        OWNER_ID,
        PORTFOLIO_ID,
        trade("sell-001", TransactionType.SELL, "0.5", day=3),
    )
    retry = await service.create(
        OWNER_ID,
        PORTFOLIO_ID,
        trade("buy-001", TransactionType.BUY, "2.000000000001", day=2),
    )
    listed = await service.list(OWNER_ID, PORTFOLIO_ID)

    assert first.created is True
    assert retry.created is False
    assert retry.transaction.id == first.transaction.id
    assert [transaction.external_id for transaction in listed] == [
        "buy-001",
        "sell-001",
    ]
    assert listed[0].quantity == Decimal("2.000000000001")
    assert listed[0].unit_price == Decimal("123.12345678")
    assert listed[0].fees == Decimal("0.00000001")

    with pytest.raises(TransactionIdempotencyConflictError):
        await service.create(
            OWNER_ID,
            PORTFOLIO_ID,
            trade("buy-001", TransactionType.BUY, "3", day=2),
        )
    assert len(await service.list(OWNER_ID, PORTFOLIO_ID)) == 2


@pytest.mark.anyio
async def test_concurrent_sells_cannot_create_negative_position(
    session_factory: AsyncSessionFactory,
) -> None:
    await add_portfolio(session_factory)
    service = TransactionService(lambda: unit_of_work_factory(session_factory))
    await service.create(
        OWNER_ID,
        PORTFOLIO_ID,
        trade("buy-001", TransactionType.BUY, "1", day=2),
    )

    results = await asyncio.gather(
        service.create(
            OWNER_ID,
            PORTFOLIO_ID,
            trade("sell-001", TransactionType.SELL, "1", day=3),
        ),
        service.create(
            OWNER_ID,
            PORTFOLIO_ID,
            trade("sell-002", TransactionType.SELL, "1", day=3),
        ),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, BaseException) for result in results) == 1
    errors = [result for result in results if isinstance(result, BaseException)]
    assert len(errors) == 1
    assert isinstance(errors[0], InvalidTransactionError)
    assert len(await service.list(OWNER_ID, PORTFOLIO_ID)) == 2


@pytest.mark.anyio
async def test_concurrent_identical_requests_create_one_transaction(
    session_factory: AsyncSessionFactory,
) -> None:
    await add_portfolio(session_factory)
    service = TransactionService(lambda: unit_of_work_factory(session_factory))

    results = await asyncio.gather(
        service.create(
            OWNER_ID,
            PORTFOLIO_ID,
            trade("buy-001", TransactionType.BUY, "1", day=2),
        ),
        service.create(
            OWNER_ID,
            PORTFOLIO_ID,
            trade("buy-001", TransactionType.BUY, "1", day=2),
        ),
    )

    assert sorted(result.created for result in results) == [False, True]
    assert results[0].transaction.id == results[1].transaction.id
    assert len(await service.list(OWNER_ID, PORTFOLIO_ID)) == 1
