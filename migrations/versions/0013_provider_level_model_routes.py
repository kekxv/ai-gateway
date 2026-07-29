"""make model routes provider-level

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-29 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _provider_protocol_foreign_key_name() -> str:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys("model_routes"):
        if foreign_key.get("constrained_columns") == ["provider_protocol_id"]:
            name = foreign_key.get("name")
            if isinstance(name, str):
                return name
    raise RuntimeError("model_routes.provider_protocol_id foreign key was not found")


def upgrade() -> None:
    op.execute(
        """
        CREATE TEMPORARY TABLE model_route_keeper_map AS
        SELECT routes.id AS old_id, keepers.keeper_id
        FROM model_routes AS routes
        JOIN (
            SELECT model_id, provider_id, MIN(id) AS keeper_id
            FROM model_routes
            GROUP BY model_id, provider_id
        ) AS keepers
          ON keepers.model_id = routes.model_id
         AND keepers.provider_id = routes.provider_id
        """
    )
    op.execute(
        """
        UPDATE request_logs
        JOIN model_route_keeper_map
          ON model_route_keeper_map.old_id = request_logs.model_route_id
        SET request_logs.model_route_id = model_route_keeper_map.keeper_id
        WHERE model_route_keeper_map.old_id <> model_route_keeper_map.keeper_id
        """
    )
    op.execute(
        """
        DELETE model_routes
        FROM model_routes
        JOIN model_route_keeper_map
          ON model_route_keeper_map.old_id = model_routes.id
        WHERE model_route_keeper_map.old_id <> model_route_keeper_map.keeper_id
        """
    )
    op.execute("DROP TEMPORARY TABLE model_route_keeper_map")

    op.drop_constraint(
        _provider_protocol_foreign_key_name(),
        "model_routes",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_model_routes_model_provider_protocol",
        "model_routes",
        type_="unique",
    )
    op.drop_column("model_routes", "provider_protocol_id")
    op.create_unique_constraint(
        "uq_model_routes_model_provider",
        "model_routes",
        ["model_id", "provider_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_model_routes_model_provider",
        "model_routes",
        type_="unique",
    )
    op.add_column(
        "model_routes",
        sa.Column("provider_protocol_id", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE model_routes
        SET provider_protocol_id = (
            SELECT MIN(provider_protocols.id)
            FROM provider_protocols
            WHERE provider_protocols.provider_id = model_routes.provider_id
        )
        """
    )
    op.alter_column(
        "model_routes",
        "provider_protocol_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_model_routes_provider_protocol_id_provider_protocols",
        "model_routes",
        "provider_protocols",
        ["provider_protocol_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_model_routes_model_provider_protocol",
        "model_routes",
        ["model_id", "provider_id", "provider_protocol_id"],
    )
