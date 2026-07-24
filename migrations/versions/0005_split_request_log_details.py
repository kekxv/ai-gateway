"""split request log details into separate table for independent cleanup

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-24 08:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Split request_detail_gzip and response_detail_gzip into separate table."""
    # 1. 创建新表
    op.create_table(
        "request_log_details",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("request_detail_gzip", mysql.LONGBLOB(), nullable=True),
        sa.Column("response_detail_gzip", mysql.LONGBLOB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["id"], ["request_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_request_log_details_created_at",
        "request_log_details",
        ["created_at"],
    )

    # 2. 数据迁移：将现有数据复制到新表
    op.execute(
        """
        INSERT INTO request_log_details (id, request_detail_gzip, response_detail_gzip, created_at)
        SELECT id, request_detail_gzip, response_detail_gzip, created_at
        FROM request_logs
        WHERE request_detail_gzip IS NOT NULL OR response_detail_gzip IS NOT NULL
        """
    )

    # 3. 删除旧字段
    op.drop_column("request_logs", "request_detail_gzip")
    op.drop_column("request_logs", "response_detail_gzip")


def downgrade() -> None:
    """Merge request_log_details back into request_logs."""
    # 1. 恢复旧字段
    op.add_column(
        "request_logs",
        sa.Column("response_detail_gzip", mysql.LONGBLOB(), nullable=True),
    )
    op.add_column(
        "request_logs",
        sa.Column("request_detail_gzip", mysql.LONGBLOB(), nullable=True),
    )

    # 2. 数据回迁
    op.execute(
        """
        UPDATE request_logs rl
        INNER JOIN request_log_details rld ON rl.id = rld.id
        SET rl.request_detail_gzip = rld.request_detail_gzip,
            rl.response_detail_gzip = rld.response_detail_gzip
        """
    )

    # 3. 删除新表
    op.drop_index("ix_request_log_details_created_at", table_name="request_log_details")
    op.drop_table("request_log_details")
