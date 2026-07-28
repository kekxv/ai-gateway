"""add token revocation timestamp

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-28 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tokens_invalidated_before", mysql.DATETIME(fsp=6), nullable=True),
    )
    op.create_table(
        "auth_rate_limits",
        sa.Column("client_key", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("client_key"),
    )


def downgrade() -> None:
    op.drop_table("auth_rate_limits")
    op.drop_column("users", "tokens_invalidated_before")
