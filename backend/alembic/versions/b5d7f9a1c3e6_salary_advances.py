"""avans sou salè: salary_advances, salary_advance_repayments, payslips.advance_amount

Revision ID: b5d7f9a1c3e6
Revises: a2c4e6f8b1d3
"""
from alembic import op
import sqlalchemy as sa

revision = "b5d7f9a1c3e6"
down_revision = "a2c4e6f8b1d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "salary_advances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("installments", sa.Integer(), nullable=False),
        sa.Column("installment_amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.Text()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_salary_advances_id", "salary_advances", ["id"])
    op.create_index("ix_salary_advances_organization_id", "salary_advances", ["organization_id"])
    op.create_index("ix_salary_advances_employee_id", "salary_advances", ["employee_id"])

    op.create_table(
        "salary_advance_repayments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("advance_id", sa.Integer(), sa.ForeignKey("salary_advances.id"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("payslip_id", sa.Integer(), sa.ForeignKey("payslips.id"), nullable=False),
        sa.Column("pay_period_id", sa.Integer(), sa.ForeignKey("pay_periods.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("advance_id", "payslip_id", name="uq_advance_repayment_slip"),
    )
    op.create_index("ix_salary_advance_repayments_id", "salary_advance_repayments", ["id"])
    op.create_index("ix_salary_advance_repayments_organization_id", "salary_advance_repayments", ["organization_id"])
    op.create_index("ix_salary_advance_repayments_advance_id", "salary_advance_repayments", ["advance_id"])
    op.create_index("ix_salary_advance_repayments_employee_id", "salary_advance_repayments", ["employee_id"])
    op.create_index("ix_salary_advance_repayments_payslip_id", "salary_advance_repayments", ["payslip_id"])

    op.add_column(
        "payslips",
        sa.Column("advance_amount", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    with op.batch_alter_table("payslips") as batch:
        batch.drop_column("advance_amount")
    op.drop_table("salary_advance_repayments")
    op.drop_table("salary_advances")