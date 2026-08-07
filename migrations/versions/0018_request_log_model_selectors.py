"""add request log model selectors

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-07 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "request_logs",
        sa.Column("requested_model", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "request_logs",
        sa.Column("resolved_model", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_request_logs_requested_model_created_at",
        "request_logs",
        ["requested_model", "created_at"],
    )
    op.create_index(
        "ix_request_logs_resolved_model_created_at",
        "request_logs",
        ["resolved_model", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_request_logs_resolved_model_created_at", table_name="request_logs")
    op.drop_index("ix_request_logs_requested_model_created_at", table_name="request_logs")
    op.drop_column("request_logs", "resolved_model")
    op.drop_column("request_logs", "requested_model")
