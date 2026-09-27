"""Kiyòsk: mòd pwentaj, kòd anplwaye, tablèt

Revision ID: f1c7a9e3b5d2
Revises: e5b9d3f7a2c4
Create Date: 2026-09-27

organizations.clock_mode: "phone" (pa defo), "kiosk" oswa "both".
employees.kiosk_*: kòd pèsonèl ache (PBKDF2) + konte move esè + blokaj.
kiosk_devices: tablèt admin aktive yo; token an estoke an sha256 sèlman.
Biznis ki deja egziste yo rete an mòd "phone": anyen pa chanje pou yo.
"""

import sqlalchemy as sa
from alembic import op

revision = "f1c7a9e3b5d2"
down_revision = "e5b9d3f7a2c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "clock_mode", sa.String(length=10), nullable=False, server_default="phone",
        ))

    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kiosk_pin_hash", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("kiosk_pin_set_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column(
            "kiosk_failed_count", sa.Integer(), nullable=False, server_default="0",
        ))
        batch_op.add_column(sa.Column("kiosk_locked_until", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "kiosk_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kiosk_devices_id", "kiosk_devices", ["id"], unique=False)
    op.create_index("ix_kiosk_devices_organization_id", "kiosk_devices",
                    ["organization_id"], unique=False)
    op.create_index("ix_kiosk_devices_token_hash", "kiosk_devices",
                    ["token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_kiosk_devices_token_hash", table_name="kiosk_devices")
    op.drop_index("ix_kiosk_devices_organization_id", table_name="kiosk_devices")
    op.drop_index("ix_kiosk_devices_id", table_name="kiosk_devices")
    op.drop_table("kiosk_devices")

    with op.batch_alter_table("employees", schema=None) as batch_op:
        batch_op.drop_column("kiosk_locked_until")
        batch_op.drop_column("kiosk_failed_count")
        batch_op.drop_column("kiosk_pin_set_at")
        batch_op.drop_column("kiosk_pin_hash")

    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_column("clock_mode")
