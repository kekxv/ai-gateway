"""add public registration setting

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-28 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "registration_locks",
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "registration_locks",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("registration_locks", "updated_at")
    op.drop_column("registration_locks", "enabled")
