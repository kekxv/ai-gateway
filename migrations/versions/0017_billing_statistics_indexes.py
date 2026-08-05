"""add request log indexes for billing statistics

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-05 00:00:00.000000

"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_request_logs_created_at", "request_logs", ["created_at"])
    op.create_index(
        "ix_request_logs_model_created_at",
        "request_logs",
        ["model_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_request_logs_model_created_at", table_name="request_logs")
    op.drop_index("ix_request_logs_created_at", table_name="request_logs")
