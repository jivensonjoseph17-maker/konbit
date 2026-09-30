"""lyen pa imel: email_tokens

Revision ID: e8a0c2d4f6b9
Revises: d7f9b1c3e5a8
"""
from alembic import op
import sqlalchemy as sa

revision = "e8a0c2d4f6b9"
down_revision = "d7f9b1c3e5a8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(10), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_tokens_id", "email_tokens", ["id"])
    op.create_index("ix_email_tokens_user_id", "email_tokens", ["user_id"])
    op.create_index("ix_email_tokens_token_hash", "email_tokens", ["token_hash"], unique=True)


def downgrade():
    op.drop_table("email_tokens")
    