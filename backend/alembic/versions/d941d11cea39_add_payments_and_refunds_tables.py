"""add payments and refunds tables

Revision ID: d941d11cea39
Revises: 1ca1c18ce823
Create Date: 2026-09-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd941d11cea39'
down_revision: Union[str, Sequence[str], None] = '1ca1c18ce823'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('payments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('reference', sa.String(length=10), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('booking_id', sa.Uuid(), nullable=True),
    sa.Column('confirmation_code', sa.String(length=10), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=False),
    sa.Column('base_fare', sa.Float(), nullable=False),
    sa.Column('taxes_fees', sa.Float(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('method', sa.String(length=50), nullable=False),
    sa.Column('is_refundable', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_payments_booking_id'), 'payments', ['booking_id'], unique=False)
    op.create_index(op.f('ix_payments_confirmation_code'), 'payments', ['confirmation_code'], unique=False)
    op.create_index(op.f('ix_payments_reference'), 'payments', ['reference'], unique=True)
    op.create_index(op.f('ix_payments_user_id'), 'payments', ['user_id'], unique=False)
    op.create_table('refunds',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('refund_number', sa.String(length=10), nullable=False),
    sa.Column('payment_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('amount', sa.Float(), nullable=False),
    sa.Column('refund_to', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_refunds_payment_id'), 'refunds', ['payment_id'], unique=False)
    op.create_index(op.f('ix_refunds_refund_number'), 'refunds', ['refund_number'], unique=True)
    op.create_index(op.f('ix_refunds_user_id'), 'refunds', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_refunds_user_id'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_refund_number'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_payment_id'), table_name='refunds')
    op.drop_table('refunds')
    op.drop_index(op.f('ix_payments_user_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_reference'), table_name='payments')
    op.drop_index(op.f('ix_payments_confirmation_code'), table_name='payments')
    op.drop_index(op.f('ix_payments_booking_id'), table_name='payments')
    op.drop_table('payments')
