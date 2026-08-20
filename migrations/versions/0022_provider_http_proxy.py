"""add provider HTTP proxy configuration

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-20 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGBLOB

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column("proxy_config_encrypted", LONGBLOB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("providers", "proxy_config_encrypted")
