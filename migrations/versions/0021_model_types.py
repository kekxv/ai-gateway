"""add model types

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-14 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("models", sa.Column("model_types", sa.JSON(), nullable=True))
    op.execute("UPDATE models SET model_types = JSON_ARRAY(model_type)")
    op.alter_column(
        "models",
        "model_types",
        existing_type=sa.JSON(),
        nullable=False,
        server_default=sa.text("(JSON_ARRAY(model_type))"),
    )


def downgrade() -> None:
    op.execute("UPDATE models SET model_type = JSON_UNQUOTE(JSON_EXTRACT(model_types, '$[0]'))")
    op.drop_column("models", "model_types")
