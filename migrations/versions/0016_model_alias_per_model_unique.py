"""enforce unique aliases per model

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-05 00:00:00.000000

"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_model_aliases_model_alias",
        "model_aliases",
        ["model_id", "alias"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_model_aliases_model_alias",
        "model_aliases",
        type_="unique",
    )
