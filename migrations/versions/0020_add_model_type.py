"""add model type

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-13 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "models",
        sa.Column(
            "model_type",
            sa.Enum(
                "text", "image", "text_to_image", "audio", "video", "embedding", name="model_type"
            ),
            nullable=False,
            server_default=sa.text("'text'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("models", "model_type")
