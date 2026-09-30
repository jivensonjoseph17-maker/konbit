"""
Tès pati B: mwen bliye modpas mwen, verifye imel (app/mailer.py mòd "memory").
Imel yo nan mailer.OUTBOX; nou li lyen an apre "#".
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import SessionLocal
from app.mailer import OUTBOX
from app.models import AuthAttempt, EmailToken

NEW_PASSWORD = "NouvoModpas2026x"


def _mails_to(email):
    return [m for m in OUTBOX if m.to == email]


def _token_from(mail):
    match = re.search(r"#([A-Za-z0-9_-]{20,})", mail.text)
    assert match, mail.text
    return match.group(1)


def _clean_reset_attempts():
    with SessionLocal() as db:
        db.query(AuthAttempt).filter(AuthAttempt.kind == "reset").delete()
        db.commit()


def _account(make_employee, headers):
    email = f"imel-{uuid.uuid4().hex[:8]}@konbit-test.ht"
    r = make_employee(headers, personal_email=email, create_login=True)
    return r["login_email"], r["temporary_password"]


def _signup(client):
    unique = uuid.uuid4().hex[:8]
    email = f"admin-imel-{unique}@konbit-test.ht"
    r = client.post("/api/auth/signup", json={
        "organization": {"name": f"Imel {unique}", "slug": f"imel-{unique}",
                         "country": "HT", "default_currency": "HTG"},
        "admin_full_name": "Admin Imel",
        "admin_email": email,
        "admin_password": "TestPassw0rd2026",
    })
    assert r.status_code == 201, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------------------
# MWEN BLIYE MODPAS MWEN
# ---------------------------------------------------------------------------

def test_forgot_unknown_email_same_answer_and_no_mail(client, org_admin, make_employee):
    _clean_reset_attempts()
    email, _ = _account(make_employee, org_admin["headers"])
    ghost = f"fantom-{uuid.uuid4().hex[:6]}@konbit-test.ht"

    a = client.post("/api/auth/forgot-password", json={"email": email})
    b = client.post("/api/auth/forgot-password", json={"email": ghost})
    assert a.status_code == b.status_code == 200
    assert a.json()["detail"] == b.json()["detail"]
    assert _mails_to(email) and not _mails_to(ghost)


def test_reset_password_full_flow(client, org_admin, make_employee):
    _clean_reset_attempts()
    email, temp = _account(make_employee, org_admin["headers"])
    old = client.post("/api/auth/login", json={"email": email, "password": temp}).json()

    assert client.post("/api/auth/forgot-password", json={"email": email.upper()}).status_code == 200
    token = _token_from(_mails_to(email)[-1])

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert r.status_code == 200, r.text

    assert client.post("/api/auth/login", json={"email": email, "password": NEW_PASSWORD}).status_code == 200
    assert client.post("/api/auth/login", json={"email": email, "password": temp}).status_code == 401
    # Tout ansyen sesyon yo anile
    old_h = {"Authorization": f"Bearer {old['access_token']}"}
    assert client.get("/api/auth/identity", headers=old_h).status_code == 401
    # Lyen an sèvi yon sèl fwa
    again = client.post("/api/auth/reset-password", json={"token": token, "new_password": "LotModpas2026x"})
    assert again.status_code == 400


def test_expired_link_is_refused(client, org_admin, make_employee):
    _clean_reset_attempts()
    email, _ = _account(make_employee, org_admin["headers"])
    client.post("/api/auth/forgot-password", json={"email": email})
    token = _token_from(_mails_to(email)[-1])

    with SessionLocal() as db:
        db.query(EmailToken).filter(EmailToken.used_at.is_(None)).update(
            {EmailToken.expires_at: datetime.now(timezone.utc) - timedelta(minutes=1)},
            synchronize_session=False,
        )
        db.commit()

    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert r.status_code == 400


def test_weak_password_does_not_burn_the_link(client, org_admin, make_employee):
    _clean_reset_attempts()
    email, _ = _account(make_employee, org_admin["headers"])
    client.post("/api/auth/forgot-password", json={"email": email})
    token = _token_from(_mails_to(email)[-1])

    weak = client.post("/api/auth/reset-password", json={"token": token, "new_password": "sanchifmodpas"})
    assert weak.status_code == 422
    ok = client.post("/api/auth/reset-password", json={"token": token, "new_password": NEW_PASSWORD})
    assert ok.status_code == 200, ok.text


def test_forgot_limit_per_email(client, org_admin, make_employee, monkeypatch):
    _clean_reset_attempts()
    monkeypatch.setattr(settings, "reset_max_per_email_hour", 2)
    email, _ = _account(make_employee, org_admin["headers"])
    for _ in range(3):
        assert client.post("/api/auth/forgot-password", json={"email": email}).status_code == 200
    assert len(_mails_to(email)) == 2          # 3yèm lan: menm repons, men pa gen imel


# ---------------------------------------------------------------------------
# VERIFYE IMEL
# ---------------------------------------------------------------------------

def test_signup_sends_verification_link(client):
    _clean_reset_attempts()
    email, h = _signup(client)
    assert client.get("/api/auth/identity", headers=h).json()["user"]["email_verified"] is False

    token = _token_from(_mails_to(email)[-1])
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/identity", headers=h).json()["user"]["email_verified"] is True

    # Deja verifye: pa gen nouvo imel
    before = len(_mails_to(email))
    assert client.post("/api/auth/resend-verification", headers=h).status_code == 200
    assert len(_mails_to(email)) == before


def test_resend_verification_replaces_old_link(client):
    _clean_reset_attempts()
    email, h = _signup(client)
    first = _token_from(_mails_to(email)[-1])

    assert client.post("/api/auth/resend-verification", headers=h).status_code == 200
    second = _token_from(_mails_to(email)[-1])
    assert second != first

    assert client.post("/api/auth/verify-email", json={"token": first}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200