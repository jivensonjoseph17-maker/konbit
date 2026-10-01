"""
Tès chifraj done sansib (app/crypto.py).
Nou li kolòn yo DIRÈK nan baz done a (SQL) pou verifye yo pa an klè.
"""
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.crypto import PREFIX, build_cipher, decrypt_value, encrypt_value
from app.database import engine


def _raw(table, column, row_id):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT {column} FROM {table} WHERE id = :i"), {"i": row_id}).scalar()


def test_roundtrip_with_a_different_result_each_time():
    a, b = encrypt_value("123456789"), encrypt_value("123456789")
    assert a.startswith(PREFIX) and a != b
    assert decrypt_value(a) == decrypt_value(b) == "123456789"


def test_old_plain_values_are_still_readable():
    assert decrypt_value("123456789") == "123456789"
    assert decrypt_value(None) is None
    assert encrypt_value("") == ""


def test_text_that_looks_encrypted_is_still_encrypted():
    tricky = "enc:v1:pa-chifre"
    assert decrypt_value(encrypt_value(tricky)) == tricky


def test_key_rotation_reads_old_values():
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    token = build_cipher(old, "x" * 40, False).encrypt(b"4321")
    assert build_cipher(f"{new},{old}", "x" * 40, False).decrypt(token) == b"4321"


def test_production_requires_a_key():
    with pytest.raises(RuntimeError):
        build_cipher("", "x" * 40, True)


def test_employee_sensitive_fields_are_encrypted_at_rest(client, org_admin, make_employee):
    h = org_admin["headers"]
    r = make_employee(h, national_id="003-456-789-0", bank_name="BNC",
                      bank_account_number="1234567890", preferred_payment_method="direct_deposit",
                      mobile_money_number="+50937001122")
    emp_id = r["employee"]["id"]

    for column, plain in (("national_id", "003-456-789-0"),
                          ("bank_account_number", "1234567890"),
                          ("mobile_money_number", "+50937001122")):
        raw = _raw("employees", column, emp_id)
        assert raw.startswith(PREFIX) and plain not in raw, column

    # API a toujou wè valè yo an klè
    sensitive = client.get(f"/api/employees/{emp_id}/sensitive", headers=h).json()
    assert sensitive["national_id"] == "003-456-789-0"
    assert sensitive["bank_account_number"] == "1234567890"
    emp = client.get(f"/api/employees/{emp_id}", headers=h).json()
    assert emp["mobile_money_number"] == "+50937001122"
    assert emp["has_bank_account"] is True


def test_totp_secret_is_encrypted_at_rest(client, make_org):
    org = make_org()
    setup = client.post("/api/auth/mfa/setup", json={"password": org["password"]}, headers=org["headers"])
    assert setup.status_code == 200, setup.text
    user_id = client.get("/api/auth/identity", headers=org["headers"]).json()["user"]["id"]

    raw = _raw("users", "totp_secret", user_id)
    assert raw.startswith(PREFIX) and setup.json()["secret"] not in raw