"""Logo biznis la kòm fichye: tab organization_logos

Revision ID: c7d2e9a4b1f6
Revises: b4f8d2a6c9e1
Create Date: 2026-09-27

Yon sèl liy pa biznis (organization_id se kle prensipal la). Imaj la se
yon PNG ke routers/org_logo.py deja netwaye (maks 512 px).
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d2e9a4b1f6"
down_revision = "b4f8d2a6c9e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_logos",
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(length=30), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("organization_id"),
    )


def downgrade() -> None:
    op.drop_table("organization_logos")
