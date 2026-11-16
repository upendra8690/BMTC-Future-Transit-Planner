"""Fares: the fare_attributes and fare_rules tables for the optional GTFS fare files.

Only two tables are added. No existing table or row is changed, so every database at 0001 keeps its records.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: str | Sequence[str] | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'fare_attributes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('import_id', sa.Integer(), nullable=False),
        sa.Column('fare_id', sa.String(length=100), nullable=False),
        sa.Column('price', sa.String(length=20), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('payment_method', sa.Integer(), nullable=False),
        sa.Column('transfers', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['import_id'], ['gtfs_imports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fare_attributes_import_id'), 'fare_attributes', ['import_id'], unique=False)
    op.create_index('ix_fare_attributes_import_fare', 'fare_attributes', ['import_id', 'fare_id'], unique=False)

    op.create_table(
        'fare_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('import_id', sa.Integer(), nullable=False),
        sa.Column('fare_id', sa.String(length=100), nullable=False),
        sa.Column('route_id', sa.String(length=100), nullable=True),
        sa.Column('origin_id', sa.String(length=100), nullable=True),
        sa.Column('destination_id', sa.String(length=100), nullable=True),
        sa.Column('contains_id', sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(['import_id'], ['gtfs_imports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fare_rules_import_id'), 'fare_rules', ['import_id'], unique=False)
    op.create_index('ix_fare_rules_import_route', 'fare_rules', ['import_id', 'route_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_fare_rules_import_route', table_name='fare_rules')
    op.drop_index(op.f('ix_fare_rules_import_id'), table_name='fare_rules')
    op.drop_table('fare_rules')
    op.drop_index('ix_fare_attributes_import_fare', table_name='fare_attributes')
    op.drop_index(op.f('ix_fare_attributes_import_id'), table_name='fare_attributes')
    op.drop_table('fare_attributes')
