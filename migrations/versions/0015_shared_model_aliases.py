"""allow model aliases to be shared

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-04 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def _model_alias_unique_constraint_name() -> str:
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("model_aliases"):
        if constraint.get("column_names") == ["alias"]:
            name = constraint.get("name")
            if isinstance(name, str):
                return name
    raise RuntimeError("model_aliases.alias unique constraint was not found")


def upgrade() -> None:
    op.drop_constraint(
        _model_alias_unique_constraint_name(),
        "model_aliases",
        type_="unique",
    )
    op.create_index("ix_model_aliases_alias", "model_aliases", ["alias"])


def downgrade() -> None:
    has_shared_aliases = op.get_bind().execute(
        sa.text(
            "SELECT 1 FROM model_aliases "
            "GROUP BY alias HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).scalar()
    if has_shared_aliases is not None:
        raise RuntimeError("Cannot downgrade shared aliases to globally unique aliases")
    op.drop_index("ix_model_aliases_alias", table_name="model_aliases")
    op.create_unique_constraint("uq_model_aliases_alias", "model_aliases", ["alias"])
