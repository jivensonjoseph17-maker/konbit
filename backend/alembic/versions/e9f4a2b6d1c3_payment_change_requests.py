"""Demann chanjman peman (kont labank / MonCash / NatCash)

Revision ID: e9f4a2b6d1c3
Revises: d8e3f1a5c2b7
Create Date: 2026-09-28

Metòd ak estati yo se String (pa Enum PostgreSQL): konsa nou pa bezwen
kreye oswa pataje tip enum ak lòt tab yo. Pydantic valide valè yo.
Gade routers/payment_changes.py.
"""

import sqlalchemy as sa
from alembic import op

revision = "e9f4a2b6d1c3"
down_revision = "d8e3f1a5c2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_change_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("bank_name", sa.String(length=150), nullable=True),
        sa.Column("account_number", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="pending"),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_change_requests_organization_id",
                    "payment_change_requests", ["organization_id"])
    op.create_index("ix_payment_change_requests_employee_id",
                    "payment_change_requests", ["employee_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_change_requests_employee_id", table_name="payment_change_requests")
    op.drop_index("ix_payment_change_requests_organization_id", table_name="payment_change_requests")
    op.drop_table("payment_change_requests")
