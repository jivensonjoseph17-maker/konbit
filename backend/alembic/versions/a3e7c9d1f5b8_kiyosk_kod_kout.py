"""Kiyòsk: kòd kout aktivasyon (6 karaktè, 10 minit)

Revision ID: a3e7c9d1f5b8
Revises: f1c7a9e3b5d2
Create Date: 2026-09-27

kiosk_pairings: admin lan jenere yon kòd kout, tablèt la tape l epi l
resevwa pwòp token pa l. Kòd la estoke an sha256 sèlman, li ekspire
apre 10 minit, epi li mache yon sèl fwa (used_at).
"""

import sqlalchemy as sa
from alembic import op

revision = "a3e7c9d1f5b8"
down_revision = "f1c7a9e3b5d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kiosk_pairings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["kiosk_devices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kiosk_pairings_id", "kiosk_pairings", ["id"], unique=False)
    op.create_index("ix_kiosk_pairings_organization_id", "kiosk_pairings",
                    ["organization_id"], unique=False)
    op.create_index("ix_kiosk_pairings_code_hash", "kiosk_pairings",
                    ["code_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_kiosk_pairings_code_hash", table_name="kiosk_pairings")
    op.drop_index("ix_kiosk_pairings_organization_id", table_name="kiosk_pairings")
    op.drop_index("ix_kiosk_pairings_id", table_name="kiosk_pairings")
    op.drop_table("kiosk_pairings")
