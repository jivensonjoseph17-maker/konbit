"""pwoteksyon koneksyon: users.token_version, auth_attempts

Revision ID: d7f9b1c3e5a8
Revises: b5d7f9a1c3e6
"""
from alembic import op
import sqlalchemy as sa

revision = "d7f9b1c3e5a8"
down_revision = "b5d7f9a1c3e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("email", sa.String(255)),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_attempts_id", "auth_attempts", ["id"])
    op.create_index("ix_auth_attempts_ip_address", "auth_attempts", ["ip_address"])
    op.create_index("ix_auth_attempts_email", "auth_attempts", ["email"])
    op.create_index("ix_auth_attempts_created_at", "auth_attempts", ["created_at"])


def downgrade():
    op.drop_table("auth_attempts")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("token_version")