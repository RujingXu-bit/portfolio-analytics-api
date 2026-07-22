from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from portfolio_analytics_api.application import EmailAlreadyRegisteredError
from portfolio_analytics_api.domain import (
    AnalysisSnapshot,
    Portfolio,
    Transaction,
    TransactionType,
    User,
)
from portfolio_analytics_api.infrastructure.database.models import (
    AnalysisSnapshotRecord,
    AssetRecord,
    PortfolioRecord,
    TransactionRecord,
    UserRecord,
)


class PostgresAnalysisSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: AnalysisSnapshot) -> None:
        self._session.add(
            AnalysisSnapshotRecord(
                id=snapshot.id,
                portfolio_id=snapshot.portfolio_id,
                as_of=snapshot.as_of,
                metrics=snapshot.metrics,
                methodology=snapshot.methodology,
                summary=snapshot.summary,
                generator=snapshot.generator,
                model_name=snapshot.model_name,
                prompt_version=snapshot.prompt_version,
                generated_at=snapshot.generated_at,
            )
        )
        await self._session.flush()


class PostgresUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        self._session.add(
            UserRecord(
                id=user.id,
                email=user.email,
                password_hash=user.password_hash,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise EmailAlreadyRegisteredError(user.email) from error

    async def get(self, user_id: UUID) -> User | None:
        return _user_to_domain(await self._session.get(UserRecord, user_id))

    async def get_by_email(self, email: str) -> User | None:
        record = await self._session.scalar(
            select(UserRecord).where(UserRecord.email == email)
        )
        return _user_to_domain(record)


class PostgresPortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, portfolio: Portfolio) -> None:
        self._session.add(
            PortfolioRecord(
                id=portfolio.id,
                owner_id=portfolio.owner_id,
                name=portfolio.name,
                base_currency=portfolio.base_currency,
            )
        )
        await self._session.flush()

    async def get(self, portfolio_id: UUID) -> Portfolio | None:
        record = await self._session.get(PortfolioRecord, portfolio_id)
        return _portfolio_to_domain(record)

    async def get_for_update(self, portfolio_id: UUID) -> Portfolio | None:
        record = await self._session.scalar(
            select(PortfolioRecord)
            .where(PortfolioRecord.id == portfolio_id)
            .with_for_update()
        )
        return _portfolio_to_domain(record)


class PostgresTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, transaction: Transaction) -> None:
        asset_id = await self._asset_id(transaction.symbol)
        self._session.add(
            TransactionRecord(
                id=transaction.id,
                portfolio_id=transaction.portfolio_id,
                asset_id=asset_id,
                external_id=transaction.external_id,
                transaction_type=transaction.transaction_type.value,
                occurred_at=transaction.occurred_at,
                quantity=transaction.quantity,
                unit_price=transaction.unit_price,
                cash_amount=transaction.cash_amount,
                fees=transaction.fees,
                created_at=transaction.created_at,
            )
        )
        await self._session.flush()

    async def get_by_external_id(
        self, portfolio_id: UUID, external_id: str
    ) -> Transaction | None:
        record = await self._session.scalar(
            select(TransactionRecord).where(
                TransactionRecord.portfolio_id == portfolio_id,
                TransactionRecord.external_id == external_id,
            )
        )
        return await self._to_domain(record)

    async def list_for_portfolio(self, portfolio_id: UUID) -> tuple[Transaction, ...]:
        records = (
            await self._session.scalars(
                select(TransactionRecord)
                .where(TransactionRecord.portfolio_id == portfolio_id)
                .order_by(
                    TransactionRecord.occurred_at,
                    TransactionRecord.created_at,
                    TransactionRecord.id,
                )
            )
        ).all()
        transactions: list[Transaction] = []
        for record in records:
            transaction = await self._to_domain(record)
            if transaction is not None:
                transactions.append(transaction)
        return tuple(transactions)

    async def _asset_id(self, symbol: str | None) -> UUID | None:
        if symbol is None:
            return None
        new_id = uuid4()
        inserted_id = await self._session.scalar(
            insert(AssetRecord)
            .values(id=new_id, symbol=symbol)
            .on_conflict_do_nothing(index_elements=[AssetRecord.symbol])
            .returning(AssetRecord.id)
        )
        if inserted_id is not None:
            return inserted_id
        existing_id = await self._session.scalar(
            select(AssetRecord.id).where(AssetRecord.symbol == symbol)
        )
        if existing_id is None:
            raise RuntimeError(f"asset upsert failed for {symbol}")
        return existing_id

    async def _to_domain(self, record: TransactionRecord | None) -> Transaction | None:
        if record is None:
            return None
        symbol = None
        if record.asset_id is not None:
            symbol = await self._session.scalar(
                select(AssetRecord.symbol).where(AssetRecord.id == record.asset_id)
            )
            if symbol is None:
                raise RuntimeError(f"asset {record.asset_id} was not found")
        return Transaction(
            id=record.id,
            portfolio_id=record.portfolio_id,
            external_id=record.external_id,
            transaction_type=TransactionType(record.transaction_type),
            occurred_at=record.occurred_at,
            created_at=record.created_at,
            symbol=symbol,
            quantity=record.quantity,
            unit_price=record.unit_price,
            cash_amount=record.cash_amount,
            fees=record.fees,
        )


def _portfolio_to_domain(record: PortfolioRecord | None) -> Portfolio | None:
    if record is None:
        return None
    return Portfolio(
        id=record.id,
        owner_id=record.owner_id,
        name=record.name,
        base_currency=record.base_currency,
    )


def _user_to_domain(record: UserRecord | None) -> User | None:
    if record is None:
        return None
    return User(
        id=record.id,
        email=record.email,
        password_hash=record.password_hash,
    )
