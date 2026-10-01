"""legal: users.terms_version/terms_accepted_at, organizations.payroll_ack_*

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
"""
from alembic import op
import sqlalchemy as sa

revision = "b2d4f6a8c0e1"
down_revision = "a1c3e5f7b9d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("terms_version", sa.String(20)))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("organizations", sa.Column("payroll_ack_at", sa.DateTime(timezone=True)))
    op.add_column("organizations", sa.Column("payroll_ack_by_id", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("payroll_ack_by_id")
        batch.drop_column("payroll_ack_at")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("terms_accepted_at")
        batch.drop_column("terms_version")