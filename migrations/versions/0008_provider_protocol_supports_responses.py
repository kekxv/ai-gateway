"""add provider protocol responses capability

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27 04:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_protocols",
        sa.Column(
            "supports_responses",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_protocols", "supports_responses")
