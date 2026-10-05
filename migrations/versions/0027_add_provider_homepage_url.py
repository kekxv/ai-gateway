"""add explicit provider homepage URL"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("providers", sa.Column("homepage_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("providers", "homepage_url")
