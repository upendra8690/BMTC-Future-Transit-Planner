"""Upcoming-transport announcements and their change history, editable by administrators.

Only two tables are added. No existing table or row is changed. The entries are seeded on first use from the
application's checked list (registry.UPCOMING), not by this migration.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: str | Sequence[str] | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'transport_announcements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('transport_type', sa.String(length=40), nullable=False),
        sa.Column('location', sa.String(length=300), nullable=False),
        sa.Column('announcement', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=40), nullable=False),
        sa.Column('source_kind', sa.String(length=20), nullable=False),
        sa.Column('announced_on', sa.String(length=10), nullable=True),
        sa.Column('expected_start', sa.String(length=10), nullable=True),
        sa.Column('opened_on', sa.String(length=10), nullable=True),
        sa.Column('sources_json', sa.Text(), nullable=False),
        sa.Column('verified_on', sa.String(length=10), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_transport_announcements_key'), 'transport_announcements', ['key'], unique=True)

    op.create_table(
        'transport_announcement_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('announcement_id', sa.Integer(), nullable=False),
        sa.Column('changed_at', sa.DateTime(), nullable=False),
        sa.Column('actor', sa.String(length=100), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('changes_json', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['announcement_id'], ['transport_announcements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_transport_announcement_changes_announcement_id'), 'transport_announcement_changes',
                    ['announcement_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_transport_announcement_changes_announcement_id'),
                  table_name='transport_announcement_changes')
    op.drop_table('transport_announcement_changes')
    op.drop_index(op.f('ix_transport_announcements_key'), table_name='transport_announcements')
    op.drop_table('transport_announcements')
