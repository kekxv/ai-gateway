"""add cache token pricing and usage fields

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-27 06:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column_name in (
        "cache_read_price_per_million",
        "cache_write_price_per_million",
    ):
        op.add_column(
            "models",
            sa.Column(
                column_name,
                sa.Numeric(20, 8),
                server_default=sa.text("0.00000000"),
                nullable=False,
            ),
        )
    for column_name in ("cache_read_tokens", "cache_write_tokens"):
        op.add_column(
            "request_logs",
            sa.Column(
                column_name,
                sa.Integer(),
                server_default=sa.text("0"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("request_logs", "cache_write_tokens")
    op.drop_column("request_logs", "cache_read_tokens")
    op.drop_column("models", "cache_write_price_per_million")
    op.drop_column("models", "cache_read_price_per_million")
