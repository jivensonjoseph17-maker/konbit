"""Fòse chanjman modpas tanporè a

Revision ID: e5b9d3f7a2c4
Revises: d4a8c2e6f1b3
Create Date: 2026-09-27

users.must_change_password: True lè HR kreye yon kont oswa jenere yon
nouvo modpas. Moun nan dwe chwazi pwòp modpas li anvan li fè anyen.
Kont ki deja egziste yo rete False: pa gen moun ki bloke apre migrasyon an.
"""

import sqlalchemy as sa
from alembic import op

revision = "e5b9d3f7a2c4"
down_revision = "d4a8c2e6f1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default=sa.false(),
        ))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("must_change_password")
