"""Create the initial portfolio schema.

Revision ID: 20260722_0001
Revises:
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260722_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
        sa.UniqueConstraint("symbol", name=op.f("uq_assets_symbol")),
    )
    op.create_table(
        "portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column(
            "base_currency",
            sa.String(length=3),
            server_default="USD",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "base_currency = upper(base_currency) AND char_length(base_currency) = 3",
            name=op.f("ck_portfolios_base_currency_code"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_portfolios_owner_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolios")),
    )
    op.create_index("ix_portfolios_owner_id", "portfolios", ["owner_id"])
    op.create_table(
        "analysis_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "methodology", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("generator", sa.String(length=100), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_analysis_snapshots_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_snapshots")),
    )
    op.create_index(
        "ix_analysis_snapshots_portfolio_generated",
        "analysis_snapshots",
        ["portfolio_id", "generated_at"],
    )
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=12), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("cash_amount", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column(
            "fees",
            sa.Numeric(precision=20, scale=8),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cash_amount IS NULL OR cash_amount > 0",
            name=op.f("ck_transactions_cash_amount_positive"),
        ),
        sa.CheckConstraint("fees >= 0", name=op.f("ck_transactions_fees_non_negative")),
        sa.CheckConstraint(
            "((transaction_type IN ('BUY', 'SELL') AND asset_id IS NOT NULL "
            "AND quantity IS NOT NULL AND unit_price IS NOT NULL "
            "AND cash_amount IS NULL) OR "
            "(transaction_type IN ('DEPOSIT', 'WITHDRAWAL') "
            "AND asset_id IS NULL AND quantity IS NULL "
            "AND unit_price IS NULL AND cash_amount IS NOT NULL))",
            name=op.f("ck_transactions_payload_matches_type"),
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name=op.f("ck_transactions_quantity_positive"),
        ),
        sa.CheckConstraint(
            "unit_price IS NULL OR unit_price > 0",
            name=op.f("ck_transactions_unit_price_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_transactions_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_transactions_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_transactions")),
        sa.UniqueConstraint(
            "portfolio_id",
            "external_id",
            name="uq_transactions_portfolio_external",
        ),
    )
    op.create_index("ix_transactions_asset_id", "transactions", ["asset_id"])
    op.create_index(
        "ix_transactions_portfolio_ledger",
        "transactions",
        ["portfolio_id", "occurred_at", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_portfolio_ledger", table_name="transactions")
    op.drop_index("ix_transactions_asset_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index(
        "ix_analysis_snapshots_portfolio_generated",
        table_name="analysis_snapshots",
    )
    op.drop_table("analysis_snapshots")
    op.drop_index("ix_portfolios_owner_id", table_name="portfolios")
    op.drop_table("portfolios")
    op.drop_table("assets")
    op.drop_table("users")
