"""chifraj done sansib: NIF/CIN, kont labank, MonCash, demann peman, sekrè 2FA

Revision ID: a1c3e5f7b9d2
Revises: f9b1d3e5a7c0

Kolòn yo pase an Text (yon valè chifre pi long), epi tout valè ki deja la
chifre ak app.crypto (DATA_ENCRYPTION_KEY). downgrade dechifre yo.
"""
from alembic import op
import sqlalchemy as sa

revision = "a1c3e5f7b9d2"
down_revision = "f9b1d3e5a7c0"
branch_labels = None
depends_on = None

# (tab, kolòn, ansyen longè)
TARGETS = [
    ("employees", "national_id", 60),
    ("employees", "bank_account_number", 80),
    ("employees", "mobile_money_number", 50),
    ("payment_change_requests", "account_number", 80),
    ("users", "totp_secret", 64),
]


def _convert(encrypting: bool) -> None:
    from app.crypto import PREFIX, decrypt_value, encrypt_value

    bind = op.get_bind()
    for table, column, _ in TARGETS:
        rows = bind.execute(sa.text(
            f"SELECT id, {column} FROM {table} WHERE {column} IS NOT NULL AND {column} <> ''"
        )).fetchall()
        for row_id, value in rows:
            already = value.startswith(PREFIX)
            if encrypting == already:
                continue
            new_value = encrypt_value(value) if encrypting else decrypt_value(value)
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = :v WHERE id = :i"),
                {"v": new_value, "i": row_id},
            )


def upgrade():
    for table in ("employees", "payment_change_requests", "users"):
        with op.batch_alter_table(table) as batch:
            for t, column, length in TARGETS:
                if t == table:
                    batch.alter_column(column, type_=sa.Text(), existing_type=sa.String(length))
    _convert(encrypting=True)


def downgrade():
    _convert(encrypting=False)
    for table in ("employees", "payment_change_requests", "users"):
        with op.batch_alter_table(table) as batch:
            for t, column, length in TARGETS:
                if t == table:
                    batch.alter_column(column, type_=sa.String(length), existing_type=sa.Text())