"""Orders, payments, issued tickets, refunds and processed payment notifications.

Integration-ready tables for tickets and payments. They stay empty until an authorised ticketing provider and an
authorised payment provider are connected (app/services/commerce.py). No existing table or row changes.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-20 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: str | Sequence[str] | None = '0005'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('payment_notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('event_id', sa.String(length=100), nullable=False),
    sa.Column('received_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider', 'event_id', name='uq_payment_notifications_event')
    )
    op.create_table('orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('product', sa.String(length=20), nullable=False),
    sa.Column('ticket_provider', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('amount_paise', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('details', sa.Text(), nullable=False),
    sa.Column('quote', sa.Text(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'idempotency_key', name='uq_orders_user_key')
    )
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_orders_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_orders_user_id'), ['user_id'], unique=False)

    op.create_table('payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('provider_ref', sa.String(length=100), nullable=False),
    sa.Column('method', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('amount_paise', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_ref')
    )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payments_order_id'), ['order_id'], unique=False)

    op.create_table('travel_tickets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('provider_ticket_id', sa.String(length=100), nullable=False),
    sa.Column('product', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('valid_from', sa.DateTime(), nullable=True),
    sa.Column('valid_until', sa.DateTime(), nullable=True),
    sa.Column('qr_payload', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('travel_tickets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_travel_tickets_order_id'), ['order_id'], unique=False)

    op.create_table('refunds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('payment_id', sa.Integer(), nullable=False),
    sa.Column('provider_ref', sa.String(length=100), nullable=False),
    sa.Column('amount_paise', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_ref')
    )
    with op.batch_alter_table('refunds', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refunds_payment_id'), ['payment_id'], unique=False)



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('refunds', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refunds_payment_id'))

    op.drop_table('refunds')
    with op.batch_alter_table('travel_tickets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_travel_tickets_order_id'))

    op.drop_table('travel_tickets')
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_order_id'))

    op.drop_table('payments')
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_orders_user_id'))
        batch_op.drop_index(batch_op.f('ix_orders_status'))

    op.drop_table('orders')
    op.drop_table('payment_notifications')
