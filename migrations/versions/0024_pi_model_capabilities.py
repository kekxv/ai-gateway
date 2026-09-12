"""add optional Pi model capabilities"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("models", sa.Column("pi_context_window", sa.Integer(), nullable=True))
    op.add_column("models", sa.Column("pi_max_tokens", sa.Integer(), nullable=True))
    op.add_column("models", sa.Column("pi_reasoning", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("models", "pi_reasoning")
    op.drop_column("models", "pi_max_tokens")
    op.drop_column("models", "pi_context_window")
