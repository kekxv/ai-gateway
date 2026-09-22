"""add provider upstream balance query

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-22 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGBLOB

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column(
            "balance_query_type",
            sa.Enum(
                "new_api",
                "deepseek",
                "openrouter",
                "custom",
                name="balance_query_type",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "providers",
        sa.Column("balance_query_config_encrypted", LONGBLOB(), nullable=True),
    )
    op.add_column(
        "providers",
        sa.Column(
            "balance_auto_sync",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "providers",
        sa.Column(
            "balance_sync_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3600"),
        ),
    )
    op.add_column(
        "providers",
        sa.Column("balance_amount", sa.Numeric(20, 8), nullable=True),
    )
    op.add_column("providers", sa.Column("balance_currency", sa.String(16), nullable=True))
    op.add_column(
        "providers",
        sa.Column("balance_used", sa.Numeric(20, 8), nullable=True),
    )
    op.add_column("providers", sa.Column("balance_is_available", sa.Boolean(), nullable=True))
    op.add_column("providers", sa.Column("last_balance_sync_at", sa.DateTime(), nullable=True))
    op.add_column("providers", sa.Column("balance_updated_at", sa.DateTime(), nullable=True))
    op.add_column("providers", sa.Column("balance_error", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("providers", "balance_error")
    op.drop_column("providers", "balance_updated_at")
    op.drop_column("providers", "last_balance_sync_at")
    op.drop_column("providers", "balance_is_available")
    op.drop_column("providers", "balance_used")
    op.drop_column("providers", "balance_currency")
    op.drop_column("providers", "balance_amount")
    op.drop_column("providers", "balance_sync_interval_seconds")
    op.drop_column("providers", "balance_auto_sync")
    op.drop_column("providers", "balance_query_config_encrypted")
    op.drop_column("providers", "balance_query_type")
