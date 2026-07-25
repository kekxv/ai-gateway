"""add config audit logs table

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'config_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=False),
        sa.Column('old_value', sa.String(100), nullable=True),
        sa.Column('new_value', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_config_audit_logs_user_id', 'config_audit_logs', ['user_id'])
    op.create_index('ix_config_audit_logs_resource', 'config_audit_logs', ['resource_type', 'resource_id'])
    op.create_index('ix_config_audit_logs_created_at', 'config_audit_logs', ['created_at'])


def downgrade() -> None:
    op.drop_table('config_audit_logs')
