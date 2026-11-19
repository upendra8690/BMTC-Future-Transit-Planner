"""This app's own transaction id for each payment attempt.

One nullable column with a unique index on payments; no existing row changes.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-20 00:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: str | Sequence[str] | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('transaction_id', sa.String(length=40), nullable=True))
        batch_op.create_index(batch_op.f('ix_payments_transaction_id'), ['transaction_id'], unique=True)



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payments_transaction_id'))
        batch_op.drop_column('transaction_id')

