"""Paramèt biznis: frekans pewòl

Revision ID: b4f8d2a6c9e1
Revises: a3e7c9d1f5b8
Create Date: 2026-09-27

organizations.pay_frequency: "weekly", "biweekly", "semimonthly" oswa
"monthly" (pa defo). Asistan pewòl la ap sèvi avè l pou pwopoze peryòd yo.
"""

import sqlalchemy as sa
from alembic import op

revision = "b4f8d2a6c9e1"
down_revision = "a3e7c9d1f5b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "pay_frequency", sa.String(length=12), nullable=False, server_default="monthly",
        ))


def downgrade() -> None:
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("pay_frequency")
