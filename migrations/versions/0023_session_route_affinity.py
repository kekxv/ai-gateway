"""add session route affinity

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-22 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_route_affinities",
        sa.Column(
            "api_key_id",
            sa.Integer(),
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("affinity_hash", mysql.BINARY(32), primary_key=True),
        sa.Column(
            "provider_id",
            sa.Integer(),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
    )
    op.create_index(
        "ix_session_route_affinities_expires_at",
        "session_route_affinities",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_session_route_affinities_expires_at",
        table_name="session_route_affinities",
    )
    op.drop_table("session_route_affinities")
