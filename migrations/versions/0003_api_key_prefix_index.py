"""index API key prefixes

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-21 06:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the prefix lookup index used during API key authentication."""
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"], unique=False)


def downgrade() -> None:
    """Remove the API key prefix lookup index."""
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
