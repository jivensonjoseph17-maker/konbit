"""verifikasyon an 2 etap: users.totp_*, recovery_codes

Revision ID: f9b1d3e5a7c0
Revises: e8a0c2d4f6b9
"""
from alembic import op
import sqlalchemy as sa

revision = "f9b1d3e5a7c0"
down_revision = "e8a0c2d4f6b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("totp_secret", sa.String(64)))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("totp_last_step", sa.Integer()))

    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_codes_id", "recovery_codes", ["id"])
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])
    op.create_index("ix_recovery_codes_code_hash", "recovery_codes", ["code_hash"])


def downgrade():
    op.drop_table("recovery_codes")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("totp_last_step")
        batch.drop_column("totp_enabled")
        batch.drop_column("totp_secret")