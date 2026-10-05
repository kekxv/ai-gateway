"""add System One protocol"""

from collections.abc import Sequence

from alembic import op

revision = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        for table, columns in (
            ("provider_protocols", ("protocol",)),
            ("request_logs", ("inbound_protocol", "outbound_protocol")),
        ):
            for column in columns:
                nullable = "NULL" if column == "outbound_protocol" else "NOT NULL"
                enum_values = "'openai','claude','gemini','systemone'"
                op.execute(
                    f"ALTER TABLE {table} MODIFY COLUMN {column} ENUM({enum_values}) {nullable}"
                )


def downgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        for table, columns in (
            ("provider_protocols", ("protocol",)),
            ("request_logs", ("inbound_protocol", "outbound_protocol")),
        ):
            for column in columns:
                nullable = "NULL" if column == "outbound_protocol" else "NOT NULL"
                enum_values = "'openai','claude','gemini'"
                op.execute(
                    f"ALTER TABLE {table} MODIFY COLUMN {column} ENUM({enum_values}) {nullable}"
                )
