"""Require every portfolio to have an owner.

Revision ID: 20260722_0002
Revises: 20260722_0001
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_0002"
down_revision: str | None = "20260722_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM portfolios WHERE owner_id IS NULL) THEN
                RAISE EXCEPTION
                    'cannot require portfolio ownership while unowned rows exist';
            END IF;
        END
        $$
        """
    )
    op.alter_column("portfolios", "owner_id", nullable=False)


def downgrade() -> None:
    op.alter_column("portfolios", "owner_id", nullable=True)
