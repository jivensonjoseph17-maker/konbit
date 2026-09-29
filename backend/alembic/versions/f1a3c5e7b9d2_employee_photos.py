"""Foto pwofil anplwaye: tab employee_photos

Revision ID: f1a3c5e7b9d2
Revises: e9f4a2b6d1c3
Create Date: 2026-09-28

Yon foto pa anplwaye (employee_id se kle prensipal la). `public_key` se
kle aleyatwa ki nan lyen piblik la; li chanje chak fwa foto a chanje.
Gade routers/employee_photos.py.
"""

import sqlalchemy as sa
from alembic import op

revision = "f1a3c5e7b9d2"
down_revision = "e9f4a2b6d1c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employee_photos",
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.String(length=40), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("employee_id"),
    )
    op.create_index("ix_employee_photos_organization_id", "employee_photos", ["organization_id"])
    op.create_index("ix_employee_photos_public_key", "employee_photos", ["public_key"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_employee_photos_public_key", table_name="employee_photos")
    op.drop_index("ix_employee_photos_organization_id", table_name="employee_photos")
    op.drop_table("employee_photos")
