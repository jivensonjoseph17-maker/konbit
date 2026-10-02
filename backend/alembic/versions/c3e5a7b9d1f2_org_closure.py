"""fèmti biznis: organizations.closure_requested_at, closed_by_id

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "c3e5a7b9d1f2"
down_revision = "b2d4f6a8c0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("closure_requested_at", sa.DateTime(timezone=True)))
    # Pa gen ForeignKey: menm rezon ak payroll_ack_by_id (sik organizations ↔ users).
    op.add_column("organizations", sa.Column("closed_by_id", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("closed_by_id")
        batch.drop_column("closure_requested_at")
