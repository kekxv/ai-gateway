"""add price multiplier fields

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-25 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add price_multiplier column to providers table
    op.add_column(
        "providers",
        sa.Column("price_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.00"),
    )

    # Add price_multiplier column to models table
    op.add_column(
        "models",
        sa.Column("price_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.00"),
    )

    # Add CHECK constraint for providers
    op.create_check_constraint(
        "ck_providers_price_multiplier_range",
        "providers",
        "price_multiplier >= 0.10 AND price_multiplier <= 10.00",
    )

    # Add CHECK constraint for models
    op.create_check_constraint(
        "ck_models_price_multiplier_range",
        "models",
        "price_multiplier >= 0.10 AND price_multiplier <= 10.00",
    )


def downgrade() -> None:
    # Drop constraints first (in reverse order)
    op.drop_constraint("ck_models_price_multiplier_range", "models", type_="check")
    op.drop_constraint("ck_providers_price_multiplier_range", "providers", type_="check")

    # Drop columns (in reverse order)
    op.drop_column("models", "price_multiplier")
    op.drop_column("providers", "price_multiplier")
