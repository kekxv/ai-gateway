"""track whether model routes were created manually or by discovery

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-21 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the route provenance used by automatic model discovery."""
    op.add_column(
        "model_routes",
        sa.Column(
            "source",
            sa.Enum("manual", "discovered", name="route_source"),
            server_default="manual",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove model route provenance."""
    op.drop_column("model_routes", "source")
