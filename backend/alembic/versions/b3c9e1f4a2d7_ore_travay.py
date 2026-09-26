"""orè travay pa semèn (shift_templates, shifts)

Revision ID: b3c9e1f4a2d7
Revises: 8d8e33fa5923
Create Date: 2026-09-25 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c9e1f4a2d7'
down_revision: Union[str, None] = '8d8e33fa5923'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shift_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('break_minutes', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_shift_templates_id', 'shift_templates', ['id'])
    op.create_index('ix_shift_templates_organization_id', 'shift_templates', ['organization_id'])

    op.create_table(
        'shifts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('break_minutes', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['template_id'], ['shift_templates.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'work_date', name='uq_shift_emp_date'),
    )
    op.create_index('ix_shifts_id', 'shifts', ['id'])
    op.create_index('ix_shifts_organization_id', 'shifts', ['organization_id'])
    op.create_index('ix_shifts_employee_id', 'shifts', ['employee_id'])
    op.create_index('ix_shifts_work_date', 'shifts', ['work_date'])


def downgrade() -> None:
    op.drop_index('ix_shifts_work_date', table_name='shifts')
    op.drop_index('ix_shifts_employee_id', table_name='shifts')
    op.drop_index('ix_shifts_organization_id', table_name='shifts')
    op.drop_index('ix_shifts_id', table_name='shifts')
    op.drop_table('shifts')
    op.drop_index('ix_shift_templates_organization_id', table_name='shift_templates')
    op.drop_index('ix_shift_templates_id', table_name='shift_templates')
    op.drop_table('shift_templates')