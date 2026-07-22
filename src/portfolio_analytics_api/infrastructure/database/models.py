from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from portfolio_analytics_api.infrastructure.database.base import Base


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioRecord(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        CheckConstraint(
            "base_currency = upper(base_currency) AND char_length(base_currency) = 3",
            name="base_currency_code",
        ),
        Index("ix_portfolios_owner_id", "owner_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default="USD"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AssetRecord(Base):
    __tablename__ = "assets"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TransactionRecord(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "((transaction_type IN ('BUY', 'SELL') "
            "AND asset_id IS NOT NULL AND quantity IS NOT NULL "
            "AND unit_price IS NOT NULL AND cash_amount IS NULL) "
            "OR (transaction_type IN ('DEPOSIT', 'WITHDRAWAL') "
            "AND asset_id IS NULL AND quantity IS NULL "
            "AND unit_price IS NULL AND cash_amount IS NOT NULL))",
            name="payload_matches_type",
        ),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "unit_price IS NULL OR unit_price > 0", name="unit_price_positive"
        ),
        CheckConstraint(
            "cash_amount IS NULL OR cash_amount > 0", name="cash_amount_positive"
        ),
        CheckConstraint("fees >= 0", name="fees_non_negative"),
        UniqueConstraint(
            "portfolio_id", "external_id", name="uq_transactions_portfolio_external"
        ),
        Index(
            "ix_transactions_portfolio_ledger",
            "portfolio_id",
            "occurred_at",
            "created_at",
            "id",
        ),
        Index("ix_transactions_asset_id", "asset_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    portfolio_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(28, 12), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    fees: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnalysisSnapshotRecord(Base):
    __tablename__ = "analysis_snapshots"
    __table_args__ = (
        Index(
            "ix_analysis_snapshots_portfolio_generated",
            "portfolio_id",
            "generated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    portfolio_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    methodology: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    generator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
