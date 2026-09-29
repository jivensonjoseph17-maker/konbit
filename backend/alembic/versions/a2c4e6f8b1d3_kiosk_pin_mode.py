"""Kiyòsk: mòd kòd (nimewo + kòd / kòd sèlman) ak kle rechèch kòd yo

Revision ID: a2c4e6f8b1d3
Revises: f1a3c5e7b9d2
Create Date: 2026-09-28

organizations.kiosk_pin_mode: "number_pin" (pa defo) oswa "pin_only".
employees.kiosk_pin_lookup: HMAC(kle sekrè, "org:kòd") pou jwenn moun nan
an mòd "kòd sèlman" san teste chak kòd PBKDF2. Gade routers/kiosk.py.
"""

import sqlalchemy as sa
from alembic import op

revision = "a2c4e6f8b1d3"
down_revision = "f1a3c5e7b9d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column(
        "kiosk_pin_mode", sa.String(length=12), nullable=False, server_default="number_pin"))
    op.add_column("employees", sa.Column("kiosk_pin_lookup", sa.String(length=64), nullable=True))
    op.create_index("ix_employees_kiosk_pin_lookup", "employees", ["kiosk_pin_lookup"])


def downgrade() -> None:
    op.drop_index("ix_employees_kiosk_pin_lookup", table_name="employees")
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("kiosk_pin_lookup")
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("kiosk_pin_mode")
