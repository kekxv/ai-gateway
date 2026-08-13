"""add configurable time-based model pricing

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-13 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_time_price_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("weekdays", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("input_price_per_million", sa.Numeric(20, 8), nullable=False),
        sa.Column("output_price_per_million", sa.Numeric(20, 8), nullable=False),
        sa.Column("cache_read_price_per_million", sa.Numeric(20, 8), nullable=False),
        sa.Column("cache_write_price_per_million", sa.Numeric(20, 8), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_time_price_rules_model", "model_time_price_rules", ["model_id"])


def downgrade() -> None:
    op.drop_index("ix_model_time_price_rules_model", table_name="model_time_price_rules")
    op.drop_table("model_time_price_rules")
