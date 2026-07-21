"""add pending TOTP secret

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21 04:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add storage for an unconfirmed initial or replacement TOTP secret."""
    op.add_column(
        "users",
        sa.Column("pending_totp_secret_encrypted", mysql.LONGBLOB(), nullable=True),
    )


def downgrade() -> None:
    """Remove storage for an unconfirmed TOTP secret."""
    op.drop_column("users", "pending_totp_secret_encrypted")
