"""add tiered public and cost pricing

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-30 07:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop check constraint before renaming column (MySQL requirement)
    op.drop_constraint("ck_providers_price_multiplier_range", "providers", type_="check")
    op.alter_column(
        "providers",
        "price_multiplier",
        new_column_name="cost_multiplier",
        existing_type=sa.Numeric(precision=4, scale=2),
        existing_nullable=False,
        existing_server_default=sa.text("1.00"),
    )
    # Recreate check constraint with new column name
    op.create_check_constraint(
        "ck_providers_cost_multiplier_range",
        "providers",
        "cost_multiplier >= 0.10 AND cost_multiplier <= 10.00",
    )
    op.add_column(
        "providers",
        sa.Column(
            "public_multiplier",
            sa.Numeric(precision=4, scale=2),
            nullable=False,
            server_default=sa.text("1.00"),
        ),
    )
    # Add check constraint for public_multiplier
    op.create_check_constraint(
        "ck_providers_public_multiplier_range",
        "providers",
        "public_multiplier >= 0.10 AND public_multiplier <= 10.00",
    )
    op.add_column(
        "request_logs",
        sa.Column(
            "cost_amount",
            sa.Numeric(precision=20, scale=8),
            nullable=False,
            server_default=sa.text("0.00000000"),
        ),
    )
    op.create_table(
        "model_price_tiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("max_input_tokens", sa.BigInteger(), nullable=True),
        sa.Column("input_price_per_million", sa.Numeric(20, 8), nullable=False),
        sa.Column("output_price_per_million", sa.Numeric(20, 8), nullable=False),
        sa.Column("cache_read_price_per_million", sa.Numeric(20, 8), nullable=False),
        sa.Column("cache_write_price_per_million", sa.Numeric(20, 8), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_price_tiers_model_max_input",
        "model_price_tiers",
        ["model_id", "max_input_tokens"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_price_tiers_model_max_input",
        table_name="model_price_tiers",
    )
    op.drop_table("model_price_tiers")
    op.drop_column("request_logs", "cost_amount")
    # Drop check constraints before dropping/renaming columns
    op.drop_constraint("ck_providers_public_multiplier_range", "providers", type_="check")
    op.drop_constraint("ck_providers_cost_multiplier_range", "providers", type_="check")
    op.drop_column("providers", "public_multiplier")
    op.alter_column(
        "providers",
        "cost_multiplier",
        new_column_name="price_multiplier",
        existing_type=sa.Numeric(precision=4, scale=2),
        existing_nullable=False,
        existing_server_default=sa.text("1.00"),
    )
    # Recreate original check constraint
    op.create_check_constraint(
        "ck_providers_price_multiplier_range",
        "providers",
        "price_multiplier >= 0.10 AND price_multiplier <= 10.00",
    )
