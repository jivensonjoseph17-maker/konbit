"""Pozisyon Direksyon + anplwaye pa sou pewòl

Revision ID: d4a8c2e6f1b3
Revises: b3c9e1f4a2d7
Create Date: 2026-09-26

- positions.is_leadership : pozisyon an parèt nan gwoup "Direksyon" anlè òganigram lan.
- employees.on_payroll    : False = moun nan nan òganigram lan, men pewòl la
                            pa kalkile fich pou li (pwopriyetè, fondatè...).

Tout ranje ki deja egziste yo resevwa valè pa defo a (is_leadership=False,
on_payroll=True): anyen pa chanje pou biznis ki deja la.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4a8c2e6f1b3"
down_revision = "b3c9e1f4a2d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "is_leadership", sa.Boolean(), nullable=False, server_default=sa.false(),
        ))
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "on_payroll", sa.Boolean(), nullable=False, server_default=sa.true(),
        ))


def downgrade() -> None:
    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_column("on_payroll")
    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.drop_column("is_leadership")
